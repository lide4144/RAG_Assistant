from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, Iterator, Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.admin_llm_config import load_runtime_llm_config, mask_api_key, normalize_api_base, save_runtime_llm_config
from app.config import load_and_validate_config
from app.llm_routing import build_stage_policy, get_last_stage_failure
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
    for stage in ("answer", "embedding", "rerank"):
        if normalized.startswith(f"{stage}."):
            return stage
    return None


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

        if answer_stage is not None or embedding_stage is not None or rerank_stage is not None:
            if answer_stage is None or embedding_stage is None or rerank_stage is None:
                raise ValueError("answer/embedding/rerank stage payloads are all required")
            saved = save_runtime_llm_config(
                answer=answer_stage,
                embedding=embedding_stage,
                rerank=rerank_stage,
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
            "updated_at": saved.updated_at,
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "python-kernel-fastapi"}


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
