from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, Iterator, Literal
from uuid import uuid4

import httpx
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.admin_llm_config import load_runtime_llm_config, mask_api_key, normalize_api_base, save_runtime_llm_config
from app.config import load_and_validate_config
from app.graph_build import run_graph_build
from app.library import load_papers, run_import_workflow
from app.llm_routing import build_stage_policy, get_last_stage_failure
from app.pipeline_runtime_config import (
    default_marker_llm,
    default_marker_tuning,
    load_pipeline_runtime_config,
    mask_marker_llm_secrets,
    resolve_effective_marker_llm,
    save_pipeline_runtime_config,
    validate_marker_llm_payload,
    validate_marker_tuning_payload,
    resolve_effective_marker_tuning,
)
from app.paths import CONFIGS_DIR, DATA_DIR, RUNS_DIR
from app.index_vec import load_vec_index
from app.qa import parse_args, run_qa

app = FastAPI(title="RAG GPT Kernel API", version="0.1.0")

_raw_cors_origins = os.getenv("KERNEL_CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_cors_origins = [item.strip() for item in _raw_cors_origins.split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
ADMIN_UPSTREAM_TIMEOUT_SEC = max(1.0, float(os.getenv("KERNEL_ADMIN_UPSTREAM_TIMEOUT_SEC", "10")))


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class KernelChatRequest(BaseModel):
    sessionId: str = Field(min_length=1)
    mode: Literal["local", "web", "hybrid"] = "local"
    query: str = Field(min_length=1)
    history: list[HistoryMessage] = Field(default_factory=list)
    traceId: str | None = None


class SourceItem(BaseModel):
    source_type: Literal["local", "web", "graph"]
    source_id: str
    title: str
    snippet: str
    locator: str
    score: float


class KernelChatResponse(BaseModel):
    traceId: str
    answer: str
    sources: list[SourceItem]


class AdminDetectModelsRequest(BaseModel):
    api_base: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class AdminModelInfo(BaseModel):
    id: str
    owned_by: str | None = None


class AdminDetectModelsResponse(BaseModel):
    models: list[AdminModelInfo]
    raw_count: int


class AdminStageConfigRequest(BaseModel):
    provider: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None


class AdminSaveLLMConfigRequest(BaseModel):
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    answer: AdminStageConfigRequest | None = None
    embedding: AdminStageConfigRequest | None = None
    rerank: AdminStageConfigRequest | None = None
    rewrite: AdminStageConfigRequest | None = None
    graph_entity: AdminStageConfigRequest | None = None
    # Legacy flat stage fields kept for backward compatibility.
    answer_provider: str | None = None
    answer_api_base: str | None = None
    answer_api_key: str | None = None
    answer_model: str | None = None
    embedding_provider: str | None = None
    embedding_api_base: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    rerank_provider: str | None = None
    rerank_api_base: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str | None = None
    rewrite_provider: str | None = None
    rewrite_api_base: str | None = None
    rewrite_api_key: str | None = None
    rewrite_model: str | None = None
    graph_entity_provider: str | None = None
    graph_entity_api_base: str | None = None
    graph_entity_api_key: str | None = None
    graph_entity_model: str | None = None


class MarkerTuningPayload(BaseModel):
    recognition_batch_size: int = Field(default=2)
    detector_batch_size: int = Field(default=2)
    layout_batch_size: int = Field(default=2)
    ocr_error_batch_size: int = Field(default=1)
    table_rec_batch_size: int = Field(default=1)
    model_dtype: str = Field(default="float16")


class MarkerLLMPayload(BaseModel):
    use_llm: bool = False
    llm_service: str = ""
    gemini_api_key: str = ""
    vertex_project_id: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    claude_api_key: str = ""
    claude_model_name: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    azure_endpoint: str = ""
    azure_api_key: str = ""
    deployment_name: str = ""


class AdminSavePipelineConfigRequest(BaseModel):
    marker_tuning: MarkerTuningPayload
    marker_llm: MarkerLLMPayload = Field(default_factory=MarkerLLMPayload)


TaskState = Literal["idle", "queued", "running", "succeeded", "failed", "cancelled"]
TaskKind = Literal["graph_build", "library_import"]


class GraphBuildTaskStartRequest(BaseModel):
    input_path: str = str(DATA_DIR / "processed" / "chunks_clean.jsonl")
    output_path: str = str(DATA_DIR / "processed" / "graph.json")
    threshold: int = 1
    top_m: int = 30
    include_front_matter: bool = False
    force_new: bool = False
    llm_max_concurrency: int | None = Field(default=None, ge=1, le=32)


class TaskErrorInfo(BaseModel):
    stage: str
    message: str
    recovery: str


class TaskProgressInfo(BaseModel):
    stage: str
    processed: int = 0
    total: int = 0
    elapsed_ms: int = 0
    message: str = ""


class TaskStatusResponse(BaseModel):
    task_id: str
    task_kind: TaskKind
    state: TaskState
    created_at: str
    updated_at: str
    accepted: bool = True
    progress: TaskProgressInfo | None = None
    error: TaskErrorInfo | None = None
    result: dict[str, Any] | None = None


_TASKS_LOCK = threading.Lock()
_TASKS: dict[str, TaskStatusResponse] = {}
_TASK_CANCEL_EVENTS: dict[str, threading.Event] = {}
_PIPELINE_STATUS_PATH = DATA_DIR / "processed" / "pipeline_status_latest.json"
_ARTIFACT_INDEX = (
    ("indexes:bmp25", DATA_DIR / "indexes" / "bm25_index.json", "bm25-index", "index"),
    ("indexes:vec", DATA_DIR / "indexes" / "vec_index.json", "vector-index", "index"),
    ("indexes:embed", DATA_DIR / "indexes" / "vec_index_embed.json", "embedding-index", "index"),
    ("processed:chunks", DATA_DIR / "processed" / "chunks.jsonl", "chunks", "import"),
    ("processed:chunks_clean", DATA_DIR / "processed" / "chunks_clean.jsonl", "clean-chunks", "clean"),
    ("processed:papers", DATA_DIR / "processed" / "papers.json", "papers-catalog", "import"),
    ("processed:paper_summary", DATA_DIR / "processed" / "paper_summary.json", "paper-summary", "clean"),
    ("processed:graph", DATA_DIR / "processed" / "graph.json", "graph", "graph_build"),
)


class TaskCancelResponse(BaseModel):
    task_id: str
    task_kind: TaskKind
    state: TaskState
    cancelled: bool
    updated_at: str
    message: str


class ImportLatestResultResponse(BaseModel):
    added: int = 0
    skipped: int = 0
    failed: int = 0
    total_papers: int = 0
    failure_reasons: list[str] = Field(default_factory=list)
    pipeline_stages: list["PipelineStageStatus"] = Field(default_factory=list)
    report_path: str | None = None
    updated_at: str | None = None
    degraded: bool = False
    fallback_reason: str | None = None
    fallback_path: str | None = None
    confidence_note: str | None = None
    artifact_summary: dict[str, Any] = Field(default_factory=dict)
    parser_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    stage_updated_at: dict[str, str] = Field(default_factory=dict)


class LibraryImportResponse(BaseModel):
    ok: bool
    success_count: int = 0
    failed_count: int = 0
    failure_reasons: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    message: str = ""
    import_summary: dict[str, Any] = Field(default_factory=dict)
    import_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    index_stage: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    task_kind: TaskKind | None = None
    task_state: TaskState | None = None
    accepted: bool | None = None


class ImportHistoryEntryResponse(BaseModel):
    run_id: str
    updated_at: str
    added: int = 0
    skipped: int = 0
    failed: int = 0
    total_candidates: int = 0
    report_path: str


class LibraryImportFromDirRequest(BaseModel):
    source_dir: str = Field(min_length=1)
    topic: str = ""


class PipelineStageStatus(BaseModel):
    stage: Literal["import", "clean", "index", "graph_build"]
    state: str
    updated_at: str | None = None
    message: str | None = None
    detail: str | None = None


class MarkerArtifactActionResponse(BaseModel):
    kind: Literal["copy_path", "rebuild", "delete"]
    enabled: bool = True
    label: str
    confirm_title: str | None = None
    confirm_message: str | None = None


class MarkerArtifactEntryResponse(BaseModel):
    key: str
    group: Literal["indexes", "processed"]
    path: str
    file_name: str
    artifact_type: str
    related_stage: Literal["import", "clean", "index", "graph_build"]
    exists: bool
    status: Literal["healthy", "missing", "stale"]
    size_bytes: int | None = None
    updated_at: str | None = None
    health_message: str | None = None
    actions: list[MarkerArtifactActionResponse] = Field(default_factory=list)


class MarkerArtifactDeleteRequest(BaseModel):
    key: str = Field(min_length=1)


class _TaskCancelledError(RuntimeError):
    pass


def _map_kernel_mode_to_qa_mode(mode: str) -> str:
    # Current Python backend only supports local retrieval; Web/Hybrid are routed in gateway later.
    return "hybrid"


def _parse_source_type(raw: str) -> Literal["local", "web", "graph"]:
    value = (raw or "").strip().lower()
    if value == "graph_expand":
        return "graph"
    if value in {"web", "graph", "local"}:
        return value  # type: ignore[return-value]
    return "local"


def _build_sources_from_qa_report(qa_report: dict[str, Any]) -> list[SourceItem]:
    grouped = qa_report.get("evidence_grouped", [])
    if not isinstance(grouped, list):
        return []

    normalized: list[SourceItem] = []
    seen = set()
    for group in grouped:
        if not isinstance(group, dict):
            continue
        paper_title = str(group.get("paper_title") or group.get("paper_id") or "Untitled source")
        evidence_rows = group.get("evidence", [])
        if not isinstance(evidence_rows, list):
            continue

        for row in evidence_rows:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("chunk_id") or "").strip()
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            score = row.get("score_rerank", row.get("score_retrieval", 0.0))
            normalized.append(
                SourceItem(
                    source_type=_parse_source_type(str(row.get("source", ""))),
                    source_id=source_id,
                    title=paper_title,
                    snippet=str(row.get("quote", "")).strip(),
                    locator=str(row.get("section_page", source_id)).strip() or source_id,
                    score=float(score) if isinstance(score, (int, float)) else 0.0,
                )
            )
    return normalized


def _build_qa_args(payload: KernelChatRequest, run_id: str, on_stream_delta: Callable[[str], None] | None) -> argparse.Namespace:
    qa_mode = _map_kernel_mode_to_qa_mode(payload.mode)
    args = parse_args(
        [
            "--q",
            payload.query,
            "--mode",
            qa_mode,
            "--chunks",
            str(DATA_DIR / "processed" / "chunks_clean.jsonl"),
            "--bm25-index",
            str(DATA_DIR / "indexes" / "bm25_index.json"),
            "--vec-index",
            str(DATA_DIR / "indexes" / "vec_index.json"),
            "--embed-index",
            str(DATA_DIR / "indexes" / "vec_index_embed.json"),
            "--config",
            str(CONFIGS_DIR / "default.yaml"),
            "--session-id",
            payload.sessionId,
            "--session-store",
            str(DATA_DIR / "session_store.json"),
            "--run-id",
            run_id,
        ]
    )
    if on_stream_delta is not None:
        setattr(args, "on_stream_delta", on_stream_delta)
    return args


def _load_qa_report(run_id: str) -> dict[str, Any]:
    report_path = Path(RUNS_DIR) / run_id / "qa_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"qa_report not found: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def _run_qa_once(payload: KernelChatRequest, on_stream_delta: Callable[[str], None] | None = None) -> KernelChatResponse:
    run_id = f"kernel_api_{uuid4().hex}"
    args = _build_qa_args(payload, run_id, on_stream_delta)
    code = run_qa(args)
    if code != 0:
        raise RuntimeError(f"run_qa exited with code {code}")

    qa_report = _load_qa_report(run_id)
    answer = str(qa_report.get("answer", "")).strip()
    if not answer:
        answer = "No answer generated by QA pipeline."

    sources = _build_sources_from_qa_report(qa_report)
    trace_id = payload.traceId or f"trace_{run_id}"
    return KernelChatResponse(traceId=trace_id, answer=answer, sources=sources)


def _normalize_admin_api_base(value: str) -> str:
    try:
        return normalize_api_base(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAMS", "message": str(exc)}) from exc


def _extract_models_from_payload(payload: Any) -> tuple[list[AdminModelInfo], int]:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_INVALID_RESPONSE", "message": "upstream payload must be a JSON object"},
        )
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_INVALID_RESPONSE", "message": "upstream payload.data must be a list"},
        )
    result: list[AdminModelInfo] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", "")).strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        owner = str(item.get("owned_by", "")).strip() or None
        result.append(AdminModelInfo(id=model_id, owned_by=owner))
    return result, len(rows)


def _build_stage_payload(
    *,
    stage_name: str,
    stage_payload: AdminStageConfigRequest | None,
    provider: str | None,
    api_base: str | None,
    api_key: str | None,
    model: str | None,
    default_provider: str,
) -> dict[str, str] | None:
    has_nested = stage_payload is not None and any(
        (
            stage_payload.provider is not None,
            stage_payload.api_base is not None,
            stage_payload.api_key is not None,
            stage_payload.model is not None,
        )
    )
    has_flat = any((provider is not None, api_base is not None, api_key is not None, model is not None))
    if not has_nested and not has_flat:
        return None

    selected_provider = str(provider or "").strip()
    selected_api_base = str(api_base or "").strip()
    selected_api_key = str(api_key or "").strip()
    selected_model = str(model or "").strip()
    if has_nested and stage_payload is not None:
        selected_provider = str(stage_payload.provider or "").strip() or selected_provider
        selected_api_base = str(stage_payload.api_base or "").strip() or selected_api_base
        selected_api_key = str(stage_payload.api_key or "").strip() or selected_api_key
        selected_model = str(stage_payload.model or "").strip() or selected_model

    if not selected_api_base:
        raise ValueError(f"{stage_name}.api_base is required")
    if not selected_api_key:
        raise ValueError(f"{stage_name}.api_key is required")
    if not selected_model:
        raise ValueError(f"{stage_name}.model is required")
    return {
        "provider": selected_provider or default_provider,
        "api_base": _normalize_admin_api_base(selected_api_base),
        "api_key": selected_api_key,
        "model": selected_model,
    }


def _extract_stage_from_error_message(message: str) -> str | None:
    normalized = str(message or "").strip().lower()
    for stage in ("answer", "embedding", "rerank", "rewrite", "graph_entity"):
        if normalized.startswith(f"{stage}."):
            return stage
    return None


def _runtime_stage_entry(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"provider": "", "model": "", "configured": False}
    provider = str(raw.get("provider", "")).strip()
    model = str(raw.get("model", "")).strip()
    return {"provider": provider, "model": model, "configured": bool(provider and model)}


def _mask_value(field: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "key" in field or "token" in field:
        return mask_marker_llm_secrets({field: text}).get(field, "")
    return text


def _marker_llm_runtime_entry(raw: Any, effective_source: dict[str, str] | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    use_llm = bool(raw.get("use_llm"))
    llm_service = str(raw.get("llm_service", "")).strip()
    required_errors: list[str] = []
    try:
        _, field_errors = validate_marker_llm_payload(raw)
        required_errors = [f"{field}: {message}" for field, message in field_errors.items()]
    except ValueError as exc:
        required_errors = [str(exc)]

    summary_fields = []
    for field in (
        "vertex_project_id",
        "ollama_base_url",
        "ollama_model",
        "claude_model_name",
        "openai_model",
        "openai_base_url",
        "azure_endpoint",
        "deployment_name",
    ):
        value = _mask_value(field, raw.get(field))
        if value:
            summary_fields.append({"field": field, "value": value, "source": (effective_source or {}).get(field, "default")})

    configured = use_llm and not required_errors and bool(llm_service)
    status = "disabled"
    if use_llm:
        status = "ready" if configured else "degraded"
    return {
        "use_llm": use_llm,
        "llm_service": llm_service,
        "configured": configured,
        "status": status,
        "required_errors": required_errors,
        "summary_fields": summary_fields,
        "effective_source": effective_source or {},
    }


def _parse_iso_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _collect_stage_updated_at(
    *,
    report: dict[str, Any] | None = None,
    latest_updated_at: str | None = None,
    latest_pipeline: dict[str, Any] | None = None,
) -> dict[str, str]:
    stage_updated_at: dict[str, str] = {}
    if isinstance(report, dict):
        for stage in ("import", "clean", "index", "graph_build"):
            payload = report.get(f"{stage}_stage")
            if isinstance(payload, dict):
                updated_at = str(payload.get("updated_at", "")).strip()
                if updated_at:
                    stage_updated_at[stage] = updated_at
    if isinstance(latest_pipeline, dict):
        payload = latest_pipeline.get("stage_updated_at")
        if isinstance(payload, dict):
            for stage in ("import", "clean", "index", "graph_build"):
                updated_at = str(payload.get(stage, "")).strip()
                if updated_at:
                    stage_updated_at[stage] = updated_at
    if latest_updated_at:
        for stage in ("import", "clean", "index"):
            stage_updated_at.setdefault(stage, latest_updated_at)
    return stage_updated_at


def _artifact_status_from_path(
    path: Path,
    *,
    related_stage: str,
    stage_updated_at: dict[str, str] | None = None,
) -> tuple[str, str | None, int | None, str | None]:
    if not path.exists():
        return "missing", "文件不存在", None, None
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    size_bytes = int(path.stat().st_size)
    anchor_dt = _parse_iso_utc((stage_updated_at or {}).get(related_stage))
    file_dt = _parse_iso_utc(updated_at)
    if anchor_dt is not None and file_dt is not None and file_dt < anchor_dt:
        return "stale", "产物早于最近一次运行，建议检查是否需要重建", size_bytes, updated_at
    return "healthy", "产物可用", size_bytes, updated_at


def _build_marker_artifacts(*, latest_updated_at: str | None = None, stage_updated_at: dict[str, str] | None = None) -> list[MarkerArtifactEntryResponse]:
    artifacts: list[MarkerArtifactEntryResponse] = []
    effective_stage_updated_at = stage_updated_at or _collect_stage_updated_at(latest_updated_at=latest_updated_at)
    for key, path, artifact_type, related_stage in _ARTIFACT_INDEX:
        group = "indexes" if key.startswith("indexes:") else "processed"
        status, health_message, size_bytes, updated_at = _artifact_status_from_path(
            path,
            related_stage=related_stage,
            stage_updated_at=effective_stage_updated_at,
        )
        artifacts.append(
            MarkerArtifactEntryResponse(
                key=key,
                group=group,  # type: ignore[arg-type]
                path=str(path),
                file_name=path.name,
                artifact_type=artifact_type,
                related_stage=related_stage,  # type: ignore[arg-type]
                exists=path.exists(),
                status=status,  # type: ignore[arg-type]
                size_bytes=size_bytes,
                updated_at=updated_at,
                health_message=health_message,
                actions=[
                    MarkerArtifactActionResponse(kind="copy_path", label="复制路径"),
                    MarkerArtifactActionResponse(kind="rebuild", label="重建入口"),
                    MarkerArtifactActionResponse(
                        kind="delete",
                        label="删除产物",
                        confirm_title=f"删除 {path.name}",
                        confirm_message=f"删除后会影响 {related_stage} 阶段，可能需要重新导入或重建。确认继续吗？",
                    ),
                ],
            )
        )
    return artifacts


def _summarize_marker_artifacts(artifacts: list[MarkerArtifactEntryResponse]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {"indexes": [], "processed": []}
    counts = {"healthy": 0, "missing": 0, "stale": 0}
    for artifact in artifacts:
        groups[artifact.group].append(artifact.model_dump())
        counts[artifact.status] = counts.get(artifact.status, 0) + 1
    return {"counts": counts, "groups": groups}


def _extract_ingest_degradation(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("parser_observability")
    if not isinstance(rows, list):
        rows = []
    fallback_rows = [row for row in rows if isinstance(row, dict) and bool(row.get("parser_fallback"))]
    if not fallback_rows:
        return {
            "degraded": False,
            "fallback_reason": None,
            "fallback_path": None,
            "confidence_note": "最近一次导入未检测到 Marker 降级路径。",
        }
    first = fallback_rows[0]
    reason = str(first.get("parser_fallback_reason", "")).strip() or "marker parser fallback"
    stage = str(first.get("parser_fallback_stage", "")).strip() or "unknown"
    return {
        "degraded": True,
        "fallback_reason": reason,
        "fallback_path": f"marker -> legacy ({stage})",
        "confidence_note": "当前结果来自降级导入路径，建议检查 Marker LLM/解析配置后重跑以恢复最佳结构化质量。",
    }


def _extract_parser_diagnostics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("parser_observability")
    if not isinstance(rows, list):
        return []
    diagnostics: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        marker_timing = row.get("marker_timing")
        if not isinstance(marker_timing, dict):
            marker_timing = {}
        diagnostics.append(
            {
                "paper_id": str(row.get("paper_id", "")).strip(),
                "source_uri": str(row.get("source_uri", "")).strip(),
                "parser_engine": str(row.get("parser_engine", "")).strip() or "legacy",
                "parser_fallback": bool(row.get("parser_fallback")),
                "parser_fallback_stage": str(row.get("parser_fallback_stage", "")).strip() or None,
                "parser_fallback_reason": str(row.get("parser_fallback_reason", "")).strip() or None,
                "marker_attempt_duration_sec": round(float(marker_timing.get("attempt_duration_sec", 0.0) or 0.0), 3),
                "marker_stage_timings": marker_timing.get("stage_timings", {}) if isinstance(marker_timing.get("stage_timings"), dict) else {},
            }
        )
    diagnostics.sort(key=lambda item: float(item.get("marker_attempt_duration_sec", 0.0) or 0.0), reverse=True)
    return diagnostics[:10]


def _build_runtime_status(
    *,
    llm: dict[str, Any],
    marker_source: dict[str, str],
    marker_warnings: list[str],
    marker_llm: dict[str, Any],
    artifact_summary: dict[str, Any],
    ingest_degradation: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    answer = llm.get("answer", {})
    if not isinstance(answer, dict) or not bool(answer.get("configured")):
        reasons.append("answer stage is not configured")
        return "BLOCKED", reasons

    for stage in ("rerank", "rewrite"):
        stage_payload = llm.get(stage, {})
        if not isinstance(stage_payload, dict) or not bool(stage_payload.get("configured")):
            reasons.append(f"{stage} stage is not configured")

    default_fallback_fields = sorted([field for field, source in marker_source.items() if source == "default"])
    if default_fallback_fields:
        reasons.append(f"marker tuning fallback to default: {', '.join(default_fallback_fields)}")
    if bool(marker_llm.get("use_llm")) and not bool(marker_llm.get("configured")):
        reasons.append("marker llm service is enabled but configuration is incomplete")
    if bool(ingest_degradation.get("degraded")):
        reasons.append(str(ingest_degradation.get("fallback_reason") or "marker ingest degraded"))
    artifact_counts = artifact_summary.get("counts", {}) if isinstance(artifact_summary, dict) else {}
    missing = int(artifact_counts.get("missing", 0) or 0)
    stale = int(artifact_counts.get("stale", 0) or 0)
    if missing > 0:
        reasons.append(f"{missing} marker artifacts are missing")
    if stale > 0:
        reasons.append(f"{stale} marker artifacts are stale")
    if marker_warnings:
        reasons.extend(marker_warnings)

    if reasons:
        return "DEGRADED", reasons
    return "READY", reasons


@app.post("/api/admin/detect-models", response_model=AdminDetectModelsResponse)
async def detect_models(payload: AdminDetectModelsRequest) -> AdminDetectModelsResponse:
    api_base = _normalize_admin_api_base(payload.api_base)
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAMS", "message": "api_key is required"})

    endpoint = f"{api_base}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=ADMIN_UPSTREAM_TIMEOUT_SEC) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "UPSTREAM_TIMEOUT", "message": f"timed out while requesting {endpoint}"},
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_NETWORK_ERROR", "message": f"failed to reach upstream endpoint: {exc}"},
        ) from exc

    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_FAILED", "message": "authentication failed against upstream models endpoint"},
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "UPSTREAM_HTTP_ERROR",
                "message": f"upstream models endpoint returned status {response.status_code}",
            },
        )
    try:
        upstream_payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "UPSTREAM_INVALID_RESPONSE", "message": "upstream returned invalid JSON payload"},
        ) from exc

    models, raw_count = _extract_models_from_payload(upstream_payload)
    return AdminDetectModelsResponse(models=models, raw_count=raw_count)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _task_snapshot(task: TaskStatusResponse) -> TaskStatusResponse:
    # Pydantic model copy to avoid mutating shared state outside lock.
    return TaskStatusResponse.model_validate(task.model_dump())


def _task_label(task_kind: TaskKind) -> str:
    if task_kind == "library_import":
        return "论文导入"
    return "图构建"


def _find_active_task(task_kind: TaskKind) -> TaskStatusResponse | None:
    with _TASKS_LOCK:
        for task in _TASKS.values():
            if task.task_kind == task_kind and task.state in {"queued", "running"}:
                return _task_snapshot(task)
    return None


def _save_task(task: TaskStatusResponse) -> None:
    with _TASKS_LOCK:
        _TASKS[task.task_id] = task


def _extract_import_failure_reasons(report: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    outcomes = report.get("import_outcomes")
    if isinstance(outcomes, list):
        for row in outcomes:
            if not isinstance(row, dict):
                continue
            if str(row.get("status", "")).strip() != "failed":
                continue
            reason = str(row.get("reason", "")).strip()
            if reason:
                reasons.append(reason)
    if reasons:
        return reasons

    failed_rows = report.get("paper_failures")
    if isinstance(failed_rows, list):
        for reason in failed_rows:
            text = str(reason).strip()
            if text:
                reasons.append(text)
    return reasons


def _latest_task(task_kind: TaskKind) -> TaskStatusResponse | None:
    with _TASKS_LOCK:
        candidates = [task for task in _TASKS.values() if task.task_kind == task_kind]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.updated_at)
    return _task_snapshot(latest)


def _stage_library_import_files(files: list[StarletteUploadFile], task_id: str) -> list[Path]:
    staging_root = DATA_DIR / "raw" / "_api_upload_staging" / task_id
    staging_root.mkdir(parents=True, exist_ok=True)
    upload_paths: list[Path] = []
    try:
        for idx, file in enumerate(files, start=1):
            safe_name = _safe_upload_name(file.filename or "", idx)
            dst = staging_root / f"{idx:03d}-{safe_name}"
            with dst.open("wb") as handle:
                while True:
                    chunk = file.file.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            upload_paths.append(dst)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    return upload_paths


def _start_library_import_task(*, task_id: str, upload_paths: list[Path], topic: str) -> TaskStatusResponse:
    active = _find_active_task("library_import")
    if active is not None:
        active.accepted = False
        return active

    now = _iso_now()
    task = TaskStatusResponse(
        task_id=task_id,
        task_kind="library_import",
        state="queued",
        created_at=now,
        updated_at=now,
        progress=TaskProgressInfo(stage="queued", processed=0, total=6, elapsed_ms=0, message="论文导入任务已排队"),
    )
    _save_task(task)
    cancel_event = threading.Event()
    with _TASKS_LOCK:
        _TASK_CANCEL_EVENTS[task_id] = cancel_event

    def worker() -> None:
        started = time.perf_counter()
        latest_stage = "queued"
        try:
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                local.state = "running"
                local.updated_at = _iso_now()
                local.progress = TaskProgressInfo(
                    stage="running",
                    processed=0,
                    total=6,
                    elapsed_ms=0,
                    message="论文导入任务已启动",
                )
                _TASKS[task_id] = local

            def on_progress(step: int, total: int, message: str) -> None:
                nonlocal latest_stage
                if cancel_event.is_set():
                    raise _TaskCancelledError("task cancelled by user")
                stage_map = {
                    1: "import_validate",
                    2: "import_prepare",
                    3: "import_clean",
                    4: "index_build",
                    5: "topic_assign",
                    6: "done",
                }
                latest_stage = stage_map.get(step, "running")
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                with _TASKS_LOCK:
                    local = _TASKS[task_id]
                    if local.state == "cancelled":
                        raise _TaskCancelledError("task cancelled by user")
                    local.progress = TaskProgressInfo(
                        stage=latest_stage,
                        processed=max(0, int(step)),
                        total=max(1, int(total)),
                        elapsed_ms=max(0, elapsed_ms),
                        message=message,
                    )
                    local.updated_at = _iso_now()
                    _TASKS[task_id] = local

            result = run_import_workflow(uploaded_files=upload_paths, topic=topic, progress_callback=on_progress)
            finished_at = _iso_now()
            _write_latest_pipeline_status(result=result, updated_at=finished_at)
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                is_cancelled = cancel_event.is_set() or local.state == "cancelled"
                local.state = "cancelled" if is_cancelled else ("succeeded" if result.get("ok") else "failed")
                local.updated_at = finished_at
                local.result = {
                    "message": str(result.get("message", "") or ""),
                    "success_count": int(result.get("success_count", 0) or 0),
                    "failed_count": int(result.get("failed_count", 0) or 0),
                }
                if not is_cancelled:
                    local.error = (
                        None
                        if result.get("ok")
                        else TaskErrorInfo(
                            stage=latest_stage or "library_import",
                            message=str(result.get("message", "") or "论文导入失败"),
                            recovery="请检查 PDF 内容、批次大小或稍后分批重试",
                        )
                    )
                if local.progress is None:
                    local.progress = TaskProgressInfo(
                        stage="cancelled" if is_cancelled else ("done" if result.get("ok") else latest_stage),
                        processed=0 if is_cancelled else 6,
                        total=6,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="论文导入已取消" if is_cancelled else str(result.get("message", "") or "论文导入已结束"),
                    )
                elif is_cancelled:
                    local.progress = TaskProgressInfo(
                        stage="cancelled",
                        processed=local.progress.processed,
                        total=local.progress.total,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="论文导入已取消",
                    )
                else:
                    local.progress = TaskProgressInfo(
                        stage="done" if result.get("ok") else latest_stage,
                        processed=6,
                        total=6,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message=str(result.get("message", "") or "论文导入已结束"),
                    )
                _TASKS[task_id] = local
        except _TaskCancelledError:
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                local.state = "cancelled"
                local.updated_at = _iso_now()
                local.progress = TaskProgressInfo(
                    stage="cancelled",
                    processed=local.progress.processed if local.progress else 0,
                    total=local.progress.total if local.progress else 6,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    message="论文导入已取消",
                )
                _TASKS[task_id] = local
        except Exception as exc:  # pragma: no cover - defensive
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                local.state = "failed"
                local.updated_at = _iso_now()
                local.error = TaskErrorInfo(
                    stage=latest_stage or "library_import",
                    message=str(exc),
                    recovery="请检查上传文件、磁盘空间或模型配置后重试",
                )
                local.progress = TaskProgressInfo(
                    stage=latest_stage or "failed",
                    processed=local.progress.processed if local.progress else 0,
                    total=local.progress.total if local.progress else 6,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    message="论文导入失败",
                )
                _TASKS[task_id] = local
        finally:
            shutil.rmtree(DATA_DIR / "raw" / "_api_upload_staging" / task_id, ignore_errors=True)
            with _TASKS_LOCK:
                _TASK_CANCEL_EVENTS.pop(task_id, None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return _task_snapshot(task)


def _resolve_import_stage_state(import_summary: dict[str, Any]) -> str:
    added = max(0, int(import_summary.get("added", 0) or 0))
    skipped = max(0, int(import_summary.get("skipped", 0) or 0))
    failed = max(0, int(import_summary.get("failed", 0) or 0))
    degraded = bool(import_summary.get("degraded"))
    if degraded and (added > 0 or skipped > 0):
        return "failed_with_fallback"
    if added > 0 or skipped > 0:
        return "succeeded"
    if failed > 0:
        return "failed"
    return "unknown"


def _resolve_index_stage_state(index_stage: dict[str, Any]) -> str:
    status = str(index_stage.get("status", "")).strip().lower()
    if status in {"success", "succeeded"}:
        return "succeeded"
    if status in {"degraded", "failed_with_fallback"}:
        return "failed_with_fallback"
    if status in {"running", "queued"}:
        return status
    if status in {"failed", "conflict"}:
        return "failed"
    return "unknown"


def _fallback_index_state() -> str:
    bm25 = DATA_DIR / "indexes" / "bm25_index.json"
    vec = DATA_DIR / "indexes" / "vec_index.json"
    embed = DATA_DIR / "indexes" / "vec_index_embed.json"
    if bm25.exists() and vec.exists() and embed.exists():
        return "succeeded"
    return "unknown"


def _fallback_graph_state() -> tuple[str, str | None, str | None]:
    graph_path = DATA_DIR / "processed" / "graph.json"
    if graph_path.exists():
        updated_at = datetime.fromtimestamp(graph_path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00",
            "Z",
        )
        return "succeeded", updated_at, f"已检测到图文件: {graph_path.name}"
    return "not_started", None, "尚未启动图构建任务"


def _build_pipeline_stages(*, report: dict[str, Any], updated_at: str | None) -> list[PipelineStageStatus]:
    import_summary = report.get("import_summary")
    if not isinstance(import_summary, dict):
        import_summary = {}
    import_state = _resolve_import_stage_state(import_summary) if report else "not_started"
    index_stage = report.get("index_stage")
    index_state = _resolve_index_stage_state(index_stage) if isinstance(index_stage, dict) else _fallback_index_state()

    latest_graph_task = _latest_task("graph_build")
    if latest_graph_task is not None:
        graph_state = latest_graph_task.state
        graph_updated_at = latest_graph_task.updated_at
        graph_message = latest_graph_task.progress.message if latest_graph_task.progress else None
    else:
        graph_state, graph_updated_at, graph_message = _fallback_graph_state()

    degradation = _extract_ingest_degradation(report if isinstance(report, dict) else {})
    detail = str(degradation.get("fallback_reason") or "").strip() or None
    stage_updated_at = _collect_stage_updated_at(report=report, latest_updated_at=updated_at)

    return [
        PipelineStageStatus(stage="import", state=import_state, updated_at=stage_updated_at.get("import"), detail=detail),
        PipelineStageStatus(stage="clean", state=import_state, updated_at=stage_updated_at.get("clean"), detail=detail),
        PipelineStageStatus(stage="index", state=index_state, updated_at=stage_updated_at.get("index")),
        PipelineStageStatus(
            stage="graph_build",
            state=graph_state,
            updated_at=graph_updated_at or stage_updated_at.get("graph_build"),
            message=graph_message,
        ),
    ]


def _write_latest_pipeline_status(*, result: dict[str, Any], updated_at: str) -> None:
    stage_updated_at = _collect_stage_updated_at(report=result, latest_updated_at=updated_at)
    payload = {
        "updated_at": updated_at,
        "import_summary": result.get("import_summary", {}),
        "index_stage": result.get("index_stage", {}),
        "failure_reasons": result.get("failure_reasons", []),
        "fallback_reason": result.get("fallback_reason"),
        "fallback_path": result.get("fallback_path"),
        "confidence_note": result.get("confidence_note"),
        "stage_updated_at": stage_updated_at,
    }
    try:
        _PIPELINE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PIPELINE_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # best effort only
        pass


def _read_latest_pipeline_status() -> dict[str, Any] | None:
    if not _PIPELINE_STATUS_PATH.exists():
        return None
    try:
        payload = json.loads(_PIPELINE_STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _safe_upload_name(raw: str, idx: int) -> str:
    name = Path(raw or f"upload-{idx}.pdf").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    if not cleaned:
        cleaned = f"upload-{idx}.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def _load_latest_import_result() -> ImportLatestResultResponse:
    total_papers = len(load_papers())
    if total_papers == 0:
        return ImportLatestResultResponse(
            total_papers=0,
            added=0,
            skipped=0,
            failed=0,
            failure_reasons=[],
            pipeline_stages=_build_pipeline_stages(report={}, updated_at=None),
            report_path=None,
            updated_at=None,
            artifact_summary=_summarize_marker_artifacts(_build_marker_artifacts()),
            parser_diagnostics=[],
        )
    report_paths = sorted(
        RUNS_DIR.glob("import_*/ingest_report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not report_paths:
        return ImportLatestResultResponse(
            total_papers=total_papers,
            pipeline_stages=_build_pipeline_stages(report={}, updated_at=None),
            artifact_summary=_summarize_marker_artifacts(_build_marker_artifacts()),
            parser_diagnostics=[],
        )

    latest = report_paths[0]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return ImportLatestResultResponse(
            total_papers=total_papers,
            report_path=str(latest),
            pipeline_stages=_build_pipeline_stages(report={}, updated_at=None),
            artifact_summary=_summarize_marker_artifacts(_build_marker_artifacts()),
            parser_diagnostics=[],
        )

    import_summary = payload.get("import_summary")
    if not isinstance(import_summary, dict):
        import_summary = {}
    failure_reasons = _extract_import_failure_reasons(payload)
    updated_at = datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )
    latest_pipeline = _read_latest_pipeline_status()
    if latest_pipeline is not None:
        recent_summary = latest_pipeline.get("import_summary")
        if isinstance(recent_summary, dict):
            import_summary = recent_summary
        recent_index_stage = latest_pipeline.get("index_stage")
        if isinstance(recent_index_stage, dict):
            payload["index_stage"] = recent_index_stage
        recent_failure_reasons = latest_pipeline.get("failure_reasons")
        if isinstance(recent_failure_reasons, list):
            failure_reasons = [str(item) for item in recent_failure_reasons if str(item).strip()]
        recent_updated = latest_pipeline.get("updated_at")
        if isinstance(recent_updated, str) and recent_updated.strip():
            updated_at = recent_updated.strip()
        recent_stage_updated_at = latest_pipeline.get("stage_updated_at")
        if isinstance(recent_stage_updated_at, dict):
            for stage in ("import", "clean", "index", "graph_build"):
                stage_updated = str(recent_stage_updated_at.get(stage, "")).strip()
                if not stage_updated:
                    continue
                payload.setdefault(f"{stage}_stage", {})
                if isinstance(payload.get(f"{stage}_stage"), dict):
                    payload[f"{stage}_stage"]["updated_at"] = stage_updated
        for key in ("fallback_reason", "fallback_path", "confidence_note"):
            if latest_pipeline.get(key) is not None:
                payload[key] = latest_pipeline.get(key)

    stage_updated_at = _collect_stage_updated_at(report=payload, latest_updated_at=updated_at, latest_pipeline=latest_pipeline)
    degradation = _extract_ingest_degradation(payload)
    diagnostics = _extract_parser_diagnostics(payload)
    artifacts = _build_marker_artifacts(latest_updated_at=updated_at, stage_updated_at=stage_updated_at)

    return ImportLatestResultResponse(
        added=max(0, int(import_summary.get("added", 0) or 0)),
        skipped=max(0, int(import_summary.get("skipped", 0) or 0)),
        failed=max(0, int(import_summary.get("failed", 0) or 0)),
        total_papers=total_papers,
        failure_reasons=failure_reasons,
        pipeline_stages=_build_pipeline_stages(report=payload, updated_at=updated_at),
        report_path=str(latest),
        updated_at=updated_at,
        degraded=bool(degradation["degraded"]),
        fallback_reason=degradation["fallback_reason"],
        fallback_path=degradation["fallback_path"],
        confidence_note=degradation["confidence_note"],
        artifact_summary=_summarize_marker_artifacts(artifacts),
        parser_diagnostics=diagnostics,
        stage_updated_at=stage_updated_at,
    )


def _load_import_history(limit: int = 20) -> list[ImportHistoryEntryResponse]:
    safe_limit = max(1, min(100, int(limit)))
    report_paths = sorted(
        RUNS_DIR.glob("import_*/ingest_report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:safe_limit]
    out: list[ImportHistoryEntryResponse] = []
    for path in report_paths:
        run_id = path.parent.name
        updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00",
            "Z",
        )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            out.append(
                ImportHistoryEntryResponse(
                    run_id=run_id,
                    updated_at=updated_at,
                    report_path=str(path),
                )
            )
            continue
        summary = payload.get("import_summary")
        if not isinstance(summary, dict):
            summary = {}
        out.append(
            ImportHistoryEntryResponse(
                run_id=run_id,
                updated_at=updated_at,
                added=max(0, int(summary.get("added", 0) or 0)),
                skipped=max(0, int(summary.get("skipped", 0) or 0)),
                failed=max(0, int(summary.get("failed", 0) or 0)),
                total_candidates=max(0, int(summary.get("total_candidates", 0) or 0)),
                report_path=str(path),
            )
        )
    return out


def _get_task_or_404(task_id: str) -> TaskStatusResponse:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": f"task_id not found: {task_id}"})
    return _task_snapshot(task)


def _stage_health_entry(*, stage: str, provider: str, model: str, reason: str | None = None) -> dict[str, Any]:
    status = "ok" if not reason else "degraded"
    payload: dict[str, Any] = {
        "status": status,
        "provider": provider,
        "model": model,
        "checked_at": _iso_now(),
        "reason": reason,
    }
    return payload


@app.get("/health/deps")
def health_deps() -> dict[str, Any]:
    cfg, warnings = load_and_validate_config(CONFIGS_DIR / "default.yaml")
    _ = warnings

    answer_policy = build_stage_policy(cfg, stage="answer")
    embedding_policy = build_stage_policy(cfg, stage="embedding")
    rerank_policy = build_stage_policy(cfg, stage="rerank")

    answer_reason = None if answer_policy.primary.resolve_api_key() else "missing_api_key"
    embedding_reason = None if embedding_policy.primary.resolve_api_key() else "missing_api_key"
    rerank_reason = None if rerank_policy.primary.resolve_api_key() else "missing_api_key"

    last_embedding_failure = get_last_stage_failure("embedding")
    if last_embedding_failure:
        embedding_reason = str(last_embedding_failure.get("category") or embedding_reason or "other")
    last_rerank_failure = get_last_stage_failure("rerank")
    if last_rerank_failure:
        rerank_reason = str(last_rerank_failure.get("category") or rerank_reason or "other")

    embed_idx_path = DATA_DIR / "indexes" / "vec_index_embed.json"
    if embed_idx_path.exists():
        try:
            embed_index = load_vec_index(embed_idx_path)
            expected_dim = int(os.getenv("RAG_EXPECTED_EMBED_DIM", "0") or 0)
            if expected_dim > 0 and int(embed_index.embedding_dim) != expected_dim:
                embedding_reason = "dimension_mismatch"
        except Exception:
            if not embedding_reason:
                embedding_reason = "index_unavailable"

    embedding_fallback_mode = "tfidf" if embedding_reason in {
        "missing_api_key",
        "auth_failed",
        "timeout",
        "network_error",
        "server_error",
        "dimension_mismatch",
    } else None
    rerank_passthrough_mode = rerank_reason in {"timeout", "network_error", "server_error", "missing_api_key", "auth_failed"}

    response = {
        "answer": _stage_health_entry(
            stage="answer",
            provider=answer_policy.primary.provider,
            model=answer_policy.primary.model,
            reason=answer_reason,
        ),
        "embedding": _stage_health_entry(
            stage="embedding",
            provider=embedding_policy.primary.provider,
            model=embedding_policy.primary.model,
            reason=embedding_reason,
        ),
        "rerank": _stage_health_entry(
            stage="rerank",
            provider=rerank_policy.primary.provider,
            model=rerank_policy.primary.model,
            reason=rerank_reason,
        ),
    }
    response["rerank"]["passthrough_mode"] = bool(rerank_passthrough_mode)
    response["rerank"]["recent_failure_reason"] = rerank_reason if rerank_passthrough_mode else None
    response["rerank"]["used_fallback"] = bool(rerank_passthrough_mode)
    response["embedding"]["fallback_mode"] = embedding_fallback_mode
    response["embedding"]["degraded_to"] = embedding_fallback_mode
    return response


@app.get("/api/admin/llm-config")
def get_admin_llm_config() -> dict[str, Any]:
    cfg, err = load_runtime_llm_config()
    if err:
        raise HTTPException(status_code=500, detail={"code": "CONFIG_INVALID", "message": err})
    if cfg is None:
        return {"configured": False}
    return {
        "configured": True,
        "answer": {
            "provider": cfg.answer.provider,
            "api_base": cfg.answer.api_base,
            "model": cfg.answer.model,
            "api_key_masked": mask_api_key(cfg.answer.api_key),
        },
        "embedding": {
            "provider": cfg.embedding.provider,
            "api_base": cfg.embedding.api_base,
            "model": cfg.embedding.model,
            "api_key_masked": mask_api_key(cfg.embedding.api_key),
        },
        "rerank": {
            "provider": cfg.rerank.provider,
            "api_base": cfg.rerank.api_base,
            "model": cfg.rerank.model,
            "api_key_masked": mask_api_key(cfg.rerank.api_key),
        },
        "rewrite": {
            "provider": cfg.rewrite.provider,
            "api_base": cfg.rewrite.api_base,
            "model": cfg.rewrite.model,
            "api_key_masked": mask_api_key(cfg.rewrite.api_key),
        },
        "graph_entity": {
            "provider": cfg.graph_entity.provider,
            "api_base": cfg.graph_entity.api_base,
            "model": cfg.graph_entity.model,
            "api_key_masked": mask_api_key(cfg.graph_entity.api_key),
        },
        "updated_at": cfg.updated_at,
    }


@app.post("/api/admin/llm-config")
def save_admin_llm_config(payload: AdminSaveLLMConfigRequest) -> dict[str, Any]:
    try:
        answer_stage = _build_stage_payload(
            stage_name="answer",
            stage_payload=payload.answer,
            provider=payload.answer_provider,
            api_base=payload.answer_api_base,
            api_key=payload.answer_api_key,
            model=payload.answer_model,
            default_provider="openai",
        )
        embedding_stage = _build_stage_payload(
            stage_name="embedding",
            stage_payload=payload.embedding,
            provider=payload.embedding_provider,
            api_base=payload.embedding_api_base,
            api_key=payload.embedding_api_key,
            model=payload.embedding_model,
            default_provider="siliconflow",
        )
        rerank_stage = _build_stage_payload(
            stage_name="rerank",
            stage_payload=payload.rerank,
            provider=payload.rerank_provider,
            api_base=payload.rerank_api_base,
            api_key=payload.rerank_api_key,
            model=payload.rerank_model,
            default_provider="siliconflow",
        )
        rewrite_stage = _build_stage_payload(
            stage_name="rewrite",
            stage_payload=payload.rewrite,
            provider=payload.rewrite_provider,
            api_base=payload.rewrite_api_base,
            api_key=payload.rewrite_api_key,
            model=payload.rewrite_model,
            default_provider="siliconflow",
        )
        graph_entity_stage = _build_stage_payload(
            stage_name="graph_entity",
            stage_payload=payload.graph_entity,
            provider=payload.graph_entity_provider,
            api_base=payload.graph_entity_api_base,
            api_key=payload.graph_entity_api_key,
            model=payload.graph_entity_model,
            default_provider="siliconflow",
        )

        if any(stage is not None for stage in (answer_stage, embedding_stage, rerank_stage, rewrite_stage, graph_entity_stage)):
            if any(stage is None for stage in (answer_stage, embedding_stage, rerank_stage, rewrite_stage, graph_entity_stage)):
                raise ValueError("answer/embedding/rerank/rewrite/graph_entity stage payloads are all required")
            saved = save_runtime_llm_config(
                answer=answer_stage,
                embedding=embedding_stage,
                rerank=rerank_stage,
                rewrite=rewrite_stage,
                graph_entity=graph_entity_stage,
            )
        else:
            api_base = _normalize_admin_api_base(str(payload.api_base or ""))
            saved = save_runtime_llm_config(
                api_base=api_base,
                api_key=str(payload.api_key or ""),
                model=str(payload.model or ""),
            )
    except ValueError as exc:
        message = str(exc)
        detail: dict[str, Any] = {"code": "INVALID_PARAMS", "message": message}
        stage = _extract_stage_from_error_message(message)
        if stage:
            detail["stage"] = stage
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail={"code": "CONFIG_SAVE_FAILED", "message": str(exc)}) from exc

    return {
        "ok": True,
        "config": {
            "answer": {
                "provider": saved.answer.provider,
                "api_base": saved.answer.api_base,
                "model": saved.answer.model,
                "api_key_masked": mask_api_key(saved.answer.api_key),
            },
            "embedding": {
                "provider": saved.embedding.provider,
                "api_base": saved.embedding.api_base,
                "model": saved.embedding.model,
                "api_key_masked": mask_api_key(saved.embedding.api_key),
            },
            "rerank": {
                "provider": saved.rerank.provider,
                "api_base": saved.rerank.api_base,
                "model": saved.rerank.model,
                "api_key_masked": mask_api_key(saved.rerank.api_key),
            },
            "rewrite": {
                "provider": saved.rewrite.provider,
                "api_base": saved.rewrite.api_base,
                "model": saved.rewrite.model,
                "api_key_masked": mask_api_key(saved.rewrite.api_key),
            },
            "graph_entity": {
                "provider": saved.graph_entity.provider,
                "api_base": saved.graph_entity.api_base,
                "model": saved.graph_entity.model,
                "api_key_masked": mask_api_key(saved.graph_entity.api_key),
            },
            "updated_at": saved.updated_at,
        },
    }


@app.get("/api/admin/pipeline-config")
def get_admin_pipeline_config() -> dict[str, Any]:
    saved, err = load_pipeline_runtime_config()
    if err:
        raise HTTPException(status_code=500, detail={"code": "CONFIG_INVALID", "message": err})
    effective = resolve_effective_marker_tuning()
    effective_llm = resolve_effective_marker_llm()
    saved_values = asdict(saved.marker_tuning) if saved is not None else asdict(default_marker_tuning())
    saved_marker_llm = asdict(saved.marker_llm) if saved is not None else asdict(default_marker_llm())
    return {
        "configured": saved is not None,
        "saved": {
            "marker_tuning": saved_values,
            "marker_llm": mask_marker_llm_secrets(saved_marker_llm),
        },
        "effective": {
            "marker_tuning": asdict(effective.values),
            "marker_llm": mask_marker_llm_secrets(asdict(effective_llm.values)),
        },
        "effective_source": {"marker_tuning": effective.source, "marker_llm": effective_llm.source},
        "warnings": effective.warnings + effective_llm.warnings,
        "updated_at": saved.updated_at if saved is not None else None,
    }


@app.post("/api/admin/pipeline-config")
def save_admin_pipeline_config(payload: AdminSavePipelineConfigRequest) -> dict[str, Any]:
    marker_payload = payload.marker_tuning.model_dump()
    marker_llm_payload = payload.marker_llm.model_dump()
    _, field_errors = validate_marker_tuning_payload(marker_payload)
    _, marker_llm_errors = validate_marker_llm_payload(marker_llm_payload)
    merged_errors = {**field_errors, **marker_llm_errors}
    if merged_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PARAMS",
                "message": "pipeline runtime validation failed",
                "field_errors": merged_errors,
            },
        )
    try:
        saved = save_pipeline_runtime_config(marker_tuning=marker_payload, marker_llm=marker_llm_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAMS", "message": str(exc)}) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail={"code": "CONFIG_SAVE_FAILED", "message": str(exc)}) from exc

    effective = resolve_effective_marker_tuning()
    effective_llm = resolve_effective_marker_llm()
    return {
        "ok": True,
        "config": {
            "marker_tuning": asdict(saved.marker_tuning),
            "marker_llm": mask_marker_llm_secrets(saved.marker_llm),
            "updated_at": saved.updated_at,
        },
        "effective": {
            "marker_tuning": asdict(effective.values),
            "marker_llm": mask_marker_llm_secrets(asdict(effective_llm.values)),
        },
        "effective_source": {"marker_tuning": effective.source, "marker_llm": effective_llm.source},
        "warnings": effective.warnings + effective_llm.warnings,
    }


@app.get("/api/admin/runtime-overview")
def get_runtime_overview() -> dict[str, Any]:
    llm_cfg, llm_err = load_runtime_llm_config()
    if llm_err:
        return {
            "llm": {},
            "pipeline": {},
            "status": {"level": "ERROR", "reasons": [llm_err]},
            "updated_at": _iso_now(),
        }

    llm = {
        "answer": _runtime_stage_entry(asdict(llm_cfg.answer) if llm_cfg is not None else {}),
        "embedding": _runtime_stage_entry(asdict(llm_cfg.embedding) if llm_cfg is not None else {}),
        "rerank": _runtime_stage_entry(asdict(llm_cfg.rerank) if llm_cfg is not None else {}),
        "rewrite": _runtime_stage_entry(asdict(llm_cfg.rewrite) if llm_cfg is not None else {}),
        "graph_entity": _runtime_stage_entry(asdict(llm_cfg.graph_entity) if llm_cfg is not None else {}),
    }
    effective = resolve_effective_marker_tuning()
    effective_llm = resolve_effective_marker_llm()
    marker_llm_entry = _marker_llm_runtime_entry(asdict(effective_llm.values), effective_llm.source)
    latest_import = _load_latest_import_result()
    artifact_summary = latest_import.artifact_summary if latest_import.updated_at else {"counts": {}}
    status_level, reasons = _build_runtime_status(
        llm=llm,
        marker_source=effective.source,
        marker_warnings=effective.warnings,
        marker_llm=marker_llm_entry,
        artifact_summary=artifact_summary,
        ingest_degradation={
            "degraded": latest_import.degraded,
            "fallback_reason": latest_import.fallback_reason,
            "fallback_path": latest_import.fallback_path,
        },
    )
    return {
        "llm": llm,
        "pipeline": {
            "marker_tuning": asdict(effective.values),
            "effective_source": {"marker_tuning": effective.source},
            "marker_llm": marker_llm_entry,
            "last_ingest": {
                "degraded": latest_import.degraded,
                "fallback_reason": latest_import.fallback_reason,
                "fallback_path": latest_import.fallback_path,
                "confidence_note": latest_import.confidence_note,
                "updated_at": latest_import.updated_at,
                "stage_updated_at": latest_import.stage_updated_at,
            },
            "artifacts": artifact_summary,
        },
        "status": {
            "level": status_level,
            "reasons": reasons,
        },
        "updated_at": _iso_now(),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "python-kernel-fastapi"}


@app.post("/api/tasks/graph-build/start", response_model=TaskStatusResponse)
def start_graph_build_task(payload: GraphBuildTaskStartRequest) -> TaskStatusResponse:
    active = _find_active_task("graph_build")
    if active is not None and not payload.force_new:
        active.accepted = False
        return active

    task_id = f"task_graph_build_{uuid4().hex}"
    now = _iso_now()
    task = TaskStatusResponse(
        task_id=task_id,
        task_kind="graph_build",
        state="queued",
        created_at=now,
        updated_at=now,
        progress=TaskProgressInfo(stage="queued", processed=0, total=0, elapsed_ms=0, message="任务已排队"),
    )
    _save_task(task)
    cancel_event = threading.Event()
    with _TASKS_LOCK:
        _TASK_CANCEL_EVENTS[task_id] = cancel_event

    def worker() -> None:
        started = time.perf_counter()
        latest_stage = "queued"
        try:
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                local.state = "running"
                local.updated_at = _iso_now()
                local.progress = TaskProgressInfo(
                    stage="running",
                    processed=0,
                    total=0,
                    elapsed_ms=0,
                    message="图构建任务已启动",
                )
                _TASKS[task_id] = local

            def on_progress(progress: dict[str, Any]) -> None:
                nonlocal latest_stage
                if cancel_event.is_set():
                    raise _TaskCancelledError("task cancelled by user")
                stage = str(progress.get("stage", "") or "running")
                latest_stage = stage
                processed = int(progress.get("processed", 0) or 0)
                total = int(progress.get("total", 0) or 0)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                message = str(progress.get("message", "") or "")
                with _TASKS_LOCK:
                    local = _TASKS[task_id]
                    if local.state == "cancelled":
                        raise _TaskCancelledError("task cancelled by user")
                    local.progress = TaskProgressInfo(
                        stage=stage,
                        processed=max(0, processed),
                        total=max(0, total),
                        elapsed_ms=max(0, elapsed_ms),
                        message=message,
                    )
                    local.updated_at = _iso_now()
                    _TASKS[task_id] = local

            run_kwargs: dict[str, Any] = {
                "threshold": max(1, int(payload.threshold)),
                "top_m": max(1, int(payload.top_m)),
                "include_front_matter": bool(payload.include_front_matter),
                "on_progress": on_progress,
            }
            if payload.llm_max_concurrency is not None:
                run_kwargs["llm_max_concurrency"] = max(1, int(payload.llm_max_concurrency))
            code = run_graph_build(
                payload.input_path,
                payload.output_path,
                **run_kwargs,
            )
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                is_cancelled = cancel_event.is_set() or local.state == "cancelled"
                local.state = "cancelled" if is_cancelled else ("succeeded" if code == 0 else "failed")
                local.updated_at = _iso_now()
                local.result = {"output_path": payload.output_path, "code": int(code)}
                if local.progress is None:
                    local.progress = TaskProgressInfo(
                        stage="cancelled" if is_cancelled else "done",
                        processed=0 if is_cancelled else 1,
                        total=1,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="图构建已取消" if is_cancelled else "图构建已结束",
                    )
                elif is_cancelled:
                    local.progress = TaskProgressInfo(
                        stage="cancelled",
                        processed=local.progress.processed,
                        total=local.progress.total,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="图构建已取消",
                    )
                _TASKS[task_id] = local
        except _TaskCancelledError:
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                local.state = "cancelled"
                local.updated_at = _iso_now()
                if local.progress is None:
                    local.progress = TaskProgressInfo(
                        stage="cancelled",
                        processed=0,
                        total=0,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="图构建已取消",
                    )
                else:
                    local.progress = TaskProgressInfo(
                        stage="cancelled",
                        processed=local.progress.processed,
                        total=local.progress.total,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="图构建已取消",
                    )
                _TASKS[task_id] = local
        except Exception as exc:  # pragma: no cover - defensive
            with _TASKS_LOCK:
                local = _TASKS[task_id]
                local.state = "failed"
                local.updated_at = _iso_now()
                local.error = TaskErrorInfo(
                    stage=latest_stage or "unknown",
                    message=str(exc),
                    recovery="请检查输入文件与模型配置后重试",
                )
                if local.progress is None:
                    local.progress = TaskProgressInfo(
                        stage=latest_stage or "failed",
                        processed=0,
                        total=0,
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        message="图构建失败",
                    )
                _TASKS[task_id] = local
        finally:
            with _TASKS_LOCK:
                _TASK_CANCEL_EVENTS.pop(task_id, None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return _task_snapshot(task)


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    return _get_task_or_404(task_id)


@app.post("/api/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
def cancel_task(task_id: str) -> TaskCancelResponse:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "TASK_NOT_FOUND", "message": f"task_id not found: {task_id}"},
            )
        if task.state in {"succeeded", "failed", "cancelled"}:
            return TaskCancelResponse(
                task_id=task.task_id,
                task_kind=task.task_kind,
                state=task.state,
                cancelled=False,
                updated_at=task.updated_at,
                message=f"任务已处于终态：{task.state}",
            )

        task_label = _task_label(task.task_kind)
        task.state = "cancelled"
        task.updated_at = _iso_now()
        task.progress = TaskProgressInfo(
            stage="cancelled",
            processed=task.progress.processed if task.progress else 0,
            total=task.progress.total if task.progress else 0,
            elapsed_ms=task.progress.elapsed_ms if task.progress else 0,
            message=f"{task_label}已取消",
        )
        _TASKS[task_id] = task
        cancel_event = _TASK_CANCEL_EVENTS.get(task_id)
        if cancel_event is not None:
            cancel_event.set()

        return TaskCancelResponse(
            task_id=task.task_id,
            task_kind=task.task_kind,
            state=task.state,
            cancelled=True,
            updated_at=task.updated_at,
            message="任务取消请求已接收",
        )


@app.get("/api/tasks", response_model=list[TaskStatusResponse])
def list_tasks(limit: int = 20) -> list[TaskStatusResponse]:
    safe_limit = max(1, min(100, int(limit)))
    with _TASKS_LOCK:
        tasks = list(_TASKS.values())
    tasks.sort(key=lambda item: item.updated_at, reverse=True)
    return [_task_snapshot(item) for item in tasks[:safe_limit]]


@app.get("/api/library/import-latest", response_model=ImportLatestResultResponse)
def get_latest_import_result() -> ImportLatestResultResponse:
    return _load_latest_import_result()


@app.get("/api/library/import-history", response_model=list[ImportHistoryEntryResponse])
def get_import_history(limit: int = 20) -> list[ImportHistoryEntryResponse]:
    return _load_import_history(limit=limit)


@app.get("/api/library/marker-artifacts")
def get_marker_artifacts() -> dict[str, Any]:
    latest = _load_latest_import_result()
    artifacts = _build_marker_artifacts(latest_updated_at=latest.updated_at, stage_updated_at=latest.stage_updated_at)
    return {
        "items": [artifact.model_dump() for artifact in artifacts],
        "summary": _summarize_marker_artifacts(artifacts),
        "updated_at": latest.updated_at,
    }


@app.post("/api/library/marker-artifacts/delete")
def delete_marker_artifact(payload: MarkerArtifactDeleteRequest) -> dict[str, Any]:
    allowed = {key: path for key, path, _artifact_type, _stage in _ARTIFACT_INDEX}
    target = allowed.get(payload.key)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND", "message": "artifact key not found"})
    if not target.exists():
        raise HTTPException(status_code=404, detail={"code": "ARTIFACT_MISSING", "message": "artifact file does not exist"})
    try:
        target.unlink()
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "ARTIFACT_DELETE_FAILED", "message": str(exc)}) from exc
    return {
        "ok": True,
        "deleted": payload.key,
        "path": str(target),
        "message": f"已删除 {target.name}",
    }


@app.post("/api/library/import", response_model=LibraryImportResponse)
async def import_library_files(request: Request) -> LibraryImportResponse:
    try:
        form = await request.form()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "MULTIPART_UNAVAILABLE", "message": f"multipart form parsing unavailable: {exc}"},
        ) from exc

    topic = str(form.get("topic", "") or "")
    # request.form() returns Starlette UploadFile objects; use Starlette type to avoid dropping valid files.
    files = [item for item in form.getlist("files") if isinstance(item, StarletteUploadFile)]
    if not files:
        raise HTTPException(status_code=400, detail={"code": "NO_FILES", "message": "未上传文件"})
    active = _find_active_task("library_import")
    if active is not None:
        return LibraryImportResponse(
            ok=True,
            message="已有论文导入任务正在运行，已复用现有任务。",
            task_id=active.task_id,
            task_kind=active.task_kind,
            task_state=active.state,
            accepted=False,
        )

    task_id = f"task_library_import_{uuid4().hex}"
    try:
        upload_paths = _stage_library_import_files(files, task_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "UPLOAD_STAGING_FAILED", "message": f"暂存上传文件失败: {exc}"},
        ) from exc

    task = _start_library_import_task(task_id=task_id, upload_paths=upload_paths, topic=topic)
    return LibraryImportResponse(
        ok=True,
        message=f"已接收 {len(upload_paths)} 个文件，后台正在导入。",
        success_count=len(upload_paths),
        failed_count=0,
        task_id=task.task_id,
        task_kind=task.task_kind,
        task_state=task.state,
        accepted=task.accepted,
    )


@app.post("/api/library/import-from-dir", response_model=LibraryImportResponse)
def import_library_from_dir(payload: LibraryImportFromDirRequest) -> LibraryImportResponse:
    raw_dir = payload.source_dir.strip()
    source_dir = Path(raw_dir).expanduser()
    if not source_dir.is_absolute():
        source_dir = (Path.cwd() / source_dir).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"code": "DIR_NOT_FOUND", "message": f"目录不存在: {source_dir}"},
        )

    pdf_paths = sorted(path for path in source_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    if not pdf_paths:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_PDF_FILES", "message": f"目录中未找到 PDF: {source_dir}"},
        )

    active = _find_active_task("library_import")
    if active is not None:
        return LibraryImportResponse(
            ok=True,
            message="已有论文导入任务正在运行，已复用现有任务。",
            task_id=active.task_id,
            task_kind=active.task_kind,
            task_state=active.state,
            accepted=False,
        )

    task_id = f"task_library_import_{uuid4().hex}"
    task = _start_library_import_task(task_id=task_id, upload_paths=pdf_paths, topic=payload.topic)
    return LibraryImportResponse(
        ok=True,
        message=f"已接收目录中的 {len(pdf_paths)} 个 PDF，后台正在导入。",
        success_count=len(pdf_paths),
        failed_count=0,
        task_id=task.task_id,
        task_kind=task.task_kind,
        task_state=task.state,
        accepted=task.accepted,
    )


@app.post("/qa", response_model=KernelChatResponse)
def qa(payload: KernelChatRequest) -> KernelChatResponse:
    try:
        return _run_qa_once(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail={"code": "KERNEL_BAD_RESPONSE", "message": str(exc)}) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail={"code": "KERNEL_UNKNOWN", "message": str(exc)}) from exc


@app.post("/qa/stream")
def qa_stream(payload: KernelChatRequest) -> StreamingResponse:
    trace_id = payload.traceId or f"trace_{uuid4().hex}"

    def event_stream() -> Iterator[str]:
        queue: Queue[dict[str, Any]] = Queue()

        def send_sse(event_name: str, data: dict[str, Any]) -> str:
            return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        def on_delta(piece: str) -> None:
            # The answer LLM currently streams raw JSON payload tokens.
            # Emitting these chunks directly causes broken frontend rendering.
            # Keep callback for future use but do not forward raw deltas.
            _ = piece

        def worker() -> None:
            try:
                response = _run_qa_once(payload, on_stream_delta=on_delta)
                queue.put(
                    {
                        "event": "sources",
                        "data": {
                            "type": "sources",
                            "traceId": trace_id,
                            "mode": payload.mode,
                            "sources": [item.dict() for item in response.sources],
                        },
                    }
                )
                queue.put(
                    {
                        "event": "message",
                        "data": {
                            "type": "message",
                            "traceId": trace_id,
                            "mode": payload.mode,
                            "content": response.answer,
                        },
                    }
                )
                queue.put(
                    {
                        "event": "messageEnd",
                        "data": {
                            "type": "messageEnd",
                            "traceId": trace_id,
                            "mode": payload.mode,
                        },
                    }
                )
            except Exception as exc:
                queue.put(
                    {
                        "event": "error",
                        "data": {
                            "type": "error",
                            "traceId": trace_id,
                            "code": "KERNEL_UNKNOWN",
                            "message": str(exc),
                        },
                    }
                )
            finally:
                queue.put({"event": "done", "data": {}})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        stream_completed = False
        while not stream_completed:
            try:
                event = queue.get(timeout=15)
            except Empty:
                yield ": keep-alive\n\n"
                continue

            name = str(event.get("event"))
            data = event.get("data", {})
            if name == "done":
                stream_completed = True
                continue
            if name == "error":
                stream_completed = True
            yield send_sse(name, data if isinstance(data, dict) else {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
