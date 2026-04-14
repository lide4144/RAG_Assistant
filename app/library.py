from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.build_indexes import main as run_build_indexes
from app.fs_utils import atomic_text_writer
from app.fs_utils import FileLockTimeoutError, file_lock
from app.ingest import run_ingest
from app.paper_store import (
    assign_topic as assign_topic_record,
    ensure_store_current,
    export_store_to_compat,
    list_papers as list_paper_records,
    load_topics as load_topics_from_store,
    paper_store_path,
    update_paper,
    upsert_artifact,
    upsert_stage_status,
    replace_topics,
)
from app.parser import SUPPORTED_LOCAL_DOC_EXTENSIONS
from app.paths import CONFIGS_DIR, DATA_DIR, RUNS_DIR

DEFAULT_PAPERS_PATH = DATA_DIR / "processed" / "papers.json"
DEFAULT_TOPICS_PATH = DATA_DIR / "library_topics.json"
DEFAULT_RAW_IMPORT_DIR = DATA_DIR / "raw" / "imported"
DEFAULT_PROCESSED_DIR = DATA_DIR / "processed"


def _normalize_item_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown-item"
    return Path(text).name or text


def _store_lookup_maps(
    *,
    store_rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for row in store_rows:
        if not isinstance(row, dict):
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        if paper_id:
            by_id[paper_id] = row
        for raw in (
            row.get("storage_path"),
            row.get("path"),
            row.get("source_uri"),
            row.get("title"),
        ):
            name = _normalize_item_name(str(raw or ""))
            if name and name not in by_name:
                by_name[name] = row
    return by_id, by_name


def _attach_store_paper_metadata(
    rows: list[dict[str, Any]],
    *,
    store_rows: list[dict[str, Any]] | None = None,
    paper_ids_by_name: dict[str, str] | None = None,
    paper_status_by_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    source_rows = list(store_rows or [])
    by_id, by_name = _store_lookup_maps(store_rows=source_rows)
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        name = _normalize_item_name(str(item.get("name", "")))
        paper_id = str(item.get("paper_id", "")).strip()
        if not paper_id and paper_ids_by_name:
            paper_id = str(paper_ids_by_name.get(name, "")).strip()
        store_row = by_id.get(paper_id) if paper_id else None
        if store_row is None and name:
            store_row = by_name.get(name)
            if store_row is not None and not paper_id:
                paper_id = str(store_row.get("paper_id", "")).strip()
        if paper_id:
            item["paper_id"] = paper_id
        paper_status = str(item.get("paper_status", "")).strip()
        if not paper_status and paper_id and paper_status_by_id:
            paper_status = str(paper_status_by_id.get(paper_id, "")).strip()
        if not paper_status and store_row is not None:
            paper_status = str(store_row.get("status", "")).strip()
        if paper_status:
            item["paper_status"] = paper_status
        if store_row is not None and str(store_row.get("title", "")).strip():
            item["name"] = str(store_row.get("title")).strip()
        out.append(item)
    return out


def _recent_items_from_files(
    uploaded_files: list[Path],
    *,
    stage: str,
    copied_names: set[str],
    failed_reasons: dict[str, str],
    active_name: str | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in uploaded_files[:6]:
        name = path.name
        if name in failed_reasons:
            rows.append(
                {
                    "name": name,
                    "state": "failed",
                    "stage": stage,
                    "message": failed_reasons[name],
                }
            )
            continue
        if name not in copied_names:
            rows.append(
                {"name": name, "state": "queued", "stage": stage, "message": "等待校验"}
            )
            continue
        rows.append(
            {
                "name": name,
                "state": "running" if active_name and name == active_name else "queued",
                "stage": stage,
                "message": "正在处理"
                if active_name and name == active_name
                else "等待当前阶段",
            }
        )
    return rows


def _recent_items_from_progress(
    uploaded_files: list[Path],
    *,
    stage: str,
    active_name: str | None,
    completed_names: set[str],
    failed_reasons: dict[str, str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in uploaded_files[:6]:
        name = path.name
        if name in failed_reasons:
            rows.append(
                {
                    "name": name,
                    "state": "failed",
                    "stage": stage,
                    "message": failed_reasons[name],
                }
            )
            continue
        if active_name and name == active_name:
            rows.append(
                {
                    "name": name,
                    "state": "running",
                    "stage": stage,
                    "message": "正在处理",
                }
            )
            continue
        if name in completed_names:
            rows.append(
                {
                    "name": name,
                    "state": "succeeded",
                    "stage": stage,
                    "message": "当前阶段完成",
                }
            )
            continue
        rows.append(
            {"name": name, "state": "queued", "stage": stage, "message": "等待当前阶段"}
        )
    return rows


def _recent_items_from_outcomes(outcomes: Any, *, stage: str) -> list[dict[str, str]]:
    if not isinstance(outcomes, list):
        return []
    rows: list[dict[str, str]] = []
    for row in outcomes:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "")).strip().lower() or "running"
        if status in {
            "added",
            "succeeded",
            "success",
            "completed",
            "imported",
            "skipped",
        }:
            state = "succeeded"
        elif status in {"failed", "error"}:
            state = "failed"
        else:
            state = "running"
        rows.append(
            {
                "name": _normalize_item_name(
                    str(
                        row.get("title")
                        or row.get("source_uri")
                        or row.get("paper_id")
                        or ""
                    )
                ),
                "state": state,
                "stage": stage,
                "message": str(row.get("reason", status)).strip() or status,
            }
        )
    return rows[:6]


def load_papers(path: Path = DEFAULT_PAPERS_PATH) -> list[dict[str, Any]]:
    target = Path(path)
    if target == DEFAULT_PAPERS_PATH:
        store_path = ensure_store_current(
            processed_dir=target.parent, topics_path=DEFAULT_TOPICS_PATH
        )
        rows = list_paper_records(db_path=store_path, limit=10_000)
        return [row for row in rows if str(row.get("paper_id", "")).strip()]
    # Deprecated: reading papers directly from JSON file is deprecated, use paper_store instead
    warnings.warn(
        "Reading papers directly from JSON file is deprecated. Use paper_store module instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [
        row
        for row in payload
        if isinstance(row, dict) and str(row.get("paper_id", "")).strip()
    ]


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> dict[str, list[str]]:
    target = Path(path)
    if target == DEFAULT_TOPICS_PATH:
        store_path = ensure_store_current(
            processed_dir=DEFAULT_PROCESSED_DIR, topics_path=target
        )
        return load_topics_from_store(db_path=store_path)
    # Deprecated: reading topics directly from JSON file is deprecated, use paper_store instead
    warnings.warn(
        "Reading topics directly from JSON file is deprecated. Use paper_store module instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    topics: dict[str, list[str]] = {}
    for topic, paper_ids in payload.items():
        key = str(topic).strip()
        if not key:
            continue
        if not isinstance(paper_ids, list):
            topics[key] = []
            continue
        topics[key] = [str(pid).strip() for pid in paper_ids if str(pid).strip()]
    return topics


def save_topics(topics: dict[str, list[str]], path: Path = DEFAULT_TOPICS_PATH) -> None:
    normalized: dict[str, list[str]] = {}
    for topic, paper_ids in topics.items():
        key = str(topic).strip()
        if not key:
            continue
        normalized[key] = [str(pid).strip() for pid in paper_ids if str(pid).strip()]
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(path) as f:
        f.write(json.dumps(normalized, ensure_ascii=False, indent=2))
    if Path(path) == DEFAULT_TOPICS_PATH:
        store_path = ensure_store_current(
            processed_dir=DEFAULT_PROCESSED_DIR, topics_path=path
        )
        replace_topics(normalized, db_path=store_path)
        export_store_to_compat(
            processed_dir=DEFAULT_PROCESSED_DIR, topics_path=path, db_path=store_path
        )


def assign_topic(
    topics: dict[str, list[str]], topic: str, paper_id: str
) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in topics.items()}
    topic_name = str(topic).strip()
    pid = str(paper_id).strip()
    if not topic_name or not pid:
        return out
    out.setdefault(topic_name, [])
    if pid not in out[topic_name]:
        out[topic_name].append(pid)
    return out


def run_import_workflow(
    *,
    uploaded_files: list[Path],
    topic: str,
    config_path: str = str(CONFIGS_DIR / "default.yaml"),
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def _progress(event: dict[str, Any]) -> None:
        if progress_callback is not None:
            progress_callback(event)

    total_files = len(uploaded_files)

    def _emit_progress(
        *,
        stage: str,
        stage_processed: int,
        stage_total: int,
        message: str,
        batch_completed: int = 0,
        batch_running: int = 0,
        batch_failed: int = 0,
        current_item_name: str | None = None,
        recent_items: list[dict[str, str]] | None = None,
    ) -> None:
        _progress(
            {
                "stage": stage,
                "current_stage": stage,
                "processed": max(0, int(stage_processed)),
                "total": max(0, int(stage_total)),
                "stage_processed": max(0, int(stage_processed)),
                "stage_total": max(0, int(stage_total)),
                "message": message,
                "batch_total": max(0, total_files),
                "batch_completed": max(0, int(batch_completed)),
                "batch_running": max(0, int(batch_running)),
                "batch_failed": max(0, int(batch_failed)),
                "current_item_name": current_item_name,
                "recent_items": list(recent_items or []),
            }
        )

    if not uploaded_files:
        return {
            "ok": False,
            "success_count": 0,
            "failed_count": 0,
            "failure_reasons": ["未选择任何文件。"],
            "next_steps": ["请先选择至少一个本地文档文件。"],
            "message": "未选择文件",
        }

    DEFAULT_RAW_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    topic_name = str(topic).strip()
    success_count = 0
    failed_count = 0
    failure_reasons: list[str] = []
    copied: list[Path] = []
    _emit_progress(
        stage="import_validate",
        stage_processed=0,
        stage_total=total_files,
        message="检查上传文件",
        batch_completed=0,
        batch_running=min(1, total_files),
        batch_failed=0,
        current_item_name=uploaded_files[0].name if uploaded_files else None,
        recent_items=_recent_items_from_files(
            uploaded_files,
            stage="import_validate",
            copied_names=set(),
            failed_reasons={},
            active_name=uploaded_files[0].name if uploaded_files else None,
        ),
    )
    failed_reason_map: dict[str, str] = {}
    for src in uploaded_files:
        if not src.exists() or src.suffix.lower() not in SUPPORTED_LOCAL_DOC_EXTENSIONS:
            failed_count += 1
            reason = f"{src.name}: 当前首版仅支持常见本地文档类型"
            failure_reasons.append(reason)
            failed_reason_map[src.name] = reason
            continue
        dst = DEFAULT_RAW_IMPORT_DIR / src.name
        if dst.exists():
            dst = (
                DEFAULT_RAW_IMPORT_DIR
                / f"{src.stem}-{src.stat().st_mtime_ns}{src.suffix.lower()}"
            )
        shutil.copyfile(src, dst)
        copied.append(dst)
        success_count += 1

    copied_names = {path.name for path in copied}
    active_name = copied[0].name if copied else None
    stage_completed_names: set[str] = set()
    paper_ids_by_name: dict[str, str] = {}
    paper_status_by_id: dict[str, str] = {}
    _emit_progress(
        stage="import_prepare",
        stage_processed=len(copied),
        stage_total=max(1, len(copied)),
        message="准备导入批次",
        batch_completed=0,
        batch_running=min(1, len(copied)),
        batch_failed=failed_count,
        current_item_name=active_name,
        recent_items=_attach_store_paper_metadata(
            _recent_items_from_files(
                uploaded_files,
                stage="import_prepare",
                copied_names=copied_names,
                failed_reasons=failed_reason_map,
                active_name=active_name,
            ),
            paper_ids_by_name=paper_ids_by_name,
            paper_status_by_id=paper_status_by_id,
        ),
    )

    if not copied:
        return {
            "ok": False,
            "success_count": 0,
            "failed_count": failed_count,
            "failure_reasons": failure_reasons or ["未检测到可导入的本地文档文件。"],
            "next_steps": ["请确认文件扩展名属于首版支持范围且文件可读后重试。"],
            "message": "未检测到可导入的本地文档文件",
        }

    with tempfile.TemporaryDirectory() as tmp:
        input_dir = Path(tmp) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        source_path_overrides: dict[str, str] = {}
        for path in copied:
            dst = input_dir / path.name
            shutil.copyfile(path, dst)
            source_path_overrides[str(dst)] = str(path)
            source_path_overrides[str(dst.resolve())] = str(path.resolve())

        ingest_run_dir = RUNS_DIR / f"import_{uuid.uuid4().hex[:10]}"
        ingest_args = argparse.Namespace(
            input=str(input_dir),
            out=str(DEFAULT_PROCESSED_DIR),
            config=config_path,
            question=None,
            clean=True,
            run_id="",
            run_dir=str(ingest_run_dir),
            lock_timeout_sec=10.0,
        )
        ingest_args.source_path_overrides = source_path_overrides

        def _on_ingest_progress(event: dict[str, Any]) -> None:
            event_name = str(event.get("event", "")).strip().lower()
            paper_name = _normalize_item_name(str(event.get("paper_name", "")).strip())
            paper_id = str(event.get("paper_id", "")).strip()
            if paper_name and paper_id:
                paper_ids_by_name[paper_name] = paper_id
            if paper_id and event_name in {"document_finished", "pdf_finished"}:
                paper_status_by_id[paper_id] = (
                    "failed"
                    if str(event.get("status", "")).strip().lower() == "failed"
                    else "parsed"
                )
            if event_name in {"document_started", "pdf_started"}:
                _emit_progress(
                    stage="import_clean",
                    stage_processed=max(0, int(event.get("pdf_completed", 0) or 0)),
                    stage_total=max(1, len(copied)),
                    message=f"正在解析 {paper_name}",
                    batch_completed=max(0, int(event.get("pdf_completed", 0) or 0)),
                    batch_running=1,
                    batch_failed=max(
                        failed_count, int(event.get("pdf_failed", 0) or 0)
                    ),
                    current_item_name=paper_name,
                    recent_items=_attach_store_paper_metadata(
                        _recent_items_from_progress(
                            copied,
                            stage="import_clean",
                            active_name=paper_name,
                            completed_names=stage_completed_names,
                            failed_reasons=failed_reason_map,
                        ),
                        paper_ids_by_name=paper_ids_by_name,
                        paper_status_by_id=paper_status_by_id,
                    ),
                )
                return
            if event_name in {"document_finished", "pdf_finished"}:
                status = str(event.get("status", "")).strip().lower()
                if status == "failed":
                    reason = str(event.get("reason", "解析失败")).strip() or "解析失败"
                    failed_reason_map[paper_name] = f"{paper_name}: {reason}"
                else:
                    stage_completed_names.add(paper_name)
                _emit_progress(
                    stage="import_clean",
                    stage_processed=max(0, int(event.get("pdf_completed", 0) or 0)),
                    stage_total=max(1, len(copied)),
                    message=f"{paper_name} {'失败' if status == 'failed' else '完成当前阶段'}",
                    batch_completed=len(stage_completed_names),
                    batch_running=0,
                    batch_failed=max(
                        failed_count, int(event.get("pdf_failed", 0) or 0)
                    ),
                    current_item_name=None,
                    recent_items=_attach_store_paper_metadata(
                        _recent_items_from_progress(
                            copied,
                            stage="import_clean",
                            active_name=None,
                            completed_names=stage_completed_names,
                            failed_reasons=failed_reason_map,
                        ),
                        paper_ids_by_name=paper_ids_by_name,
                        paper_status_by_id=paper_status_by_id,
                    ),
                )

        ingest_args.progress_callback = _on_ingest_progress
        _emit_progress(
            stage="import_clean",
            stage_processed=0,
            stage_total=max(1, len(copied)),
            message="执行入库与清洗",
            batch_completed=0,
            batch_running=min(1, len(copied)),
            batch_failed=failed_count,
            current_item_name=active_name,
            recent_items=_attach_store_paper_metadata(
                _recent_items_from_files(
                    uploaded_files,
                    stage="import_clean",
                    copied_names=copied_names,
                    failed_reasons=failed_reason_map,
                    active_name=active_name,
                ),
                paper_ids_by_name=paper_ids_by_name,
                paper_status_by_id=paper_status_by_id,
            ),
        )
        ingest_rc = run_ingest(ingest_args)
        ingest_finished_at = time.time()
        ingest_report: dict[str, Any] = {}
        ingest_report_path = ingest_run_dir / "ingest_report.json"
        if ingest_report_path.exists():
            try:
                ingest_report = json.loads(
                    ingest_report_path.read_text(encoding="utf-8")
                )
            except Exception:
                ingest_report = {}
        if ingest_rc != 0:
            if ingest_rc == 3:
                return {
                    "ok": False,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failure_reasons": failure_reasons
                    + ["导入冲突：另一个导入或知识库准备任务正在运行。"],
                    "next_steps": [
                        "请等待当前任务完成后重试。",
                        "避免重复点击“开始导入论文”或并发打开多个导入页面。",
                    ],
                    "message": "导入冲突，请稍后重试。",
                }
            return {
                "ok": False,
                "success_count": success_count,
                "failed_count": failed_count,
                "failure_reasons": failure_reasons
                + ["入库失败：本地文档解析或清洗未通过。"],
                "next_steps": [
                    "确认文档未损坏且包含可提取正文。",
                    "缩小批次先导入 1-2 篇定位问题文件。",
                ],
                "message": "导入失败，请检查文档内容是否可解析。",
            }

        import_summary = ingest_report.get("import_summary")
        if not isinstance(import_summary, dict):
            import_summary = {}
        import_outcomes = ingest_report.get("import_outcomes", [])
        terminal_completed = int(import_summary.get("added", 0) or 0) + int(
            import_summary.get("skipped", 0) or 0
        )
        terminal_failed = int(import_summary.get("failed", 0) or 0)
        if (
            int(import_summary.get("added", 0) or 0) == 0
            and terminal_failed == 0
            and terminal_completed > 0
        ):
            recent_items = _attach_store_paper_metadata(
                _recent_items_from_outcomes(import_outcomes, stage="done"),
                paper_ids_by_name=paper_ids_by_name,
                paper_status_by_id=paper_status_by_id,
            )
            no_op_updated_at = (
                datetime.fromtimestamp(ingest_finished_at, timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
            _emit_progress(
                stage="done",
                stage_processed=max(1, len(copied)),
                stage_total=max(1, len(copied)),
                message="导入完成",
                batch_completed=terminal_completed,
                batch_running=0,
                batch_failed=0,
                current_item_name=None,
                recent_items=recent_items,
            )
            if bool(import_summary.get("controlled_skip")):
                message = "导入完成，本批文件已按类型受控跳过。"
                next_steps = [
                    "检查受控跳过提示，确认当前文件类型是否已支持稳定抽取。",
                    "必要时转换为 txt、md、docx 或 PDF 后重试。",
                    "若只需增强解析，可在设置页开启 Marker 后重新导入 PDF。",
                ]
            else:
                message = "导入完成，未发现需要新增的文档。"
                next_steps = [
                    "切换到 Library 或 Chat，继续使用当前已导入文档。",
                    "如需强制重跑，请先替换文件内容或清理旧产物后再导入。",
                ]
            return {
                "ok": True,
                "success_count": success_count,
                "failed_count": failed_count,
                "failure_reasons": failure_reasons,
                "import_summary": import_summary,
                "fallback_reason": ingest_report.get("fallback_reason"),
                "fallback_path": ingest_report.get("fallback_path"),
                "confidence_note": ingest_report.get("confidence_note"),
                "import_outcomes": import_outcomes,
                "recent_items": recent_items,
                "import_stage": {"updated_at": no_op_updated_at},
                "clean_stage": {"updated_at": no_op_updated_at},
                "index_stage": {
                    "status": "success",
                    "duration_sec": 0.0,
                    "updated_at": no_op_updated_at,
                },
                "next_steps": next_steps,
                "message": message,
            }
        _emit_progress(
            stage="index_build",
            stage_processed=terminal_completed + terminal_failed,
            stage_total=max(1, len(copied)),
            message="准备知识库",
            batch_completed=terminal_completed,
            batch_running=0,
            batch_failed=terminal_failed,
            current_item_name=None,
            recent_items=_attach_store_paper_metadata(
                _recent_items_from_outcomes(import_outcomes, stage="index_build"),
                paper_ids_by_name=paper_ids_by_name,
                paper_status_by_id=paper_status_by_id,
            ),
        )
        index_started = time.perf_counter()
        index_status = "success"
        try:
            with file_lock(DATA_DIR / "indexes" / ".build.lock", timeout_sec=10.0):
                build_rc = run_build_indexes(
                    [
                        "--input",
                        str(DEFAULT_PROCESSED_DIR / "chunks_clean.jsonl"),
                        "--bm25-out",
                        str(DATA_DIR / "indexes" / "bm25_index.json"),
                        "--vec-out",
                        str(DATA_DIR / "indexes" / "vec_index.json"),
                        "--embed-out",
                        str(DATA_DIR / "indexes" / "vec_index_embed.json"),
                        "--config",
                        config_path,
                    ]
                )
        except FileLockTimeoutError:
            stage_updated_at = (
                datetime.fromtimestamp(ingest_finished_at, timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
            return {
                "ok": False,
                "success_count": success_count,
                "failed_count": failed_count,
                "failure_reasons": failure_reasons
                + ["知识库准备冲突：另一个任务正在运行。"],
                "next_steps": ["请等待当前知识库准备任务完成后重试。"],
                "message": "知识库准备冲突，请稍后重试。",
                "import_summary": ingest_report.get("import_summary", {}),
                "fallback_reason": ingest_report.get("fallback_reason"),
                "fallback_path": ingest_report.get("fallback_path"),
                "confidence_note": ingest_report.get("confidence_note"),
                "import_stage": {"updated_at": stage_updated_at},
                "clean_stage": {"updated_at": stage_updated_at},
                "index_stage": {
                    "status": "conflict",
                    "duration_sec": round(time.perf_counter() - index_started, 3),
                    "updated_at": datetime.now(timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                },
            }
        if build_rc != 0:
            index_status = "failed"
            stage_updated_at = (
                datetime.fromtimestamp(ingest_finished_at, timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
            return {
                "ok": False,
                "success_count": success_count,
                "failed_count": failed_count,
                "failure_reasons": failure_reasons
                + ["知识库准备失败：准备流程未完成。"],
                "next_steps": [
                    "稍后重试知识库准备。",
                    "若持续失败，请检查输出目录权限与磁盘空间。",
                ],
                "message": "论文已导入，但知识库准备失败，请稍后重试。",
                "import_summary": ingest_report.get("import_summary", {}),
                "fallback_reason": ingest_report.get("fallback_reason"),
                "fallback_path": ingest_report.get("fallback_path"),
                "confidence_note": ingest_report.get("confidence_note"),
                "import_stage": {"updated_at": stage_updated_at},
                "clean_stage": {"updated_at": stage_updated_at},
                "index_stage": {
                    "status": index_status,
                    "duration_sec": round(time.perf_counter() - index_started, 3),
                    "updated_at": datetime.now(timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                },
            }
        index_duration = round(time.perf_counter() - index_started, 3)
        index_finished_at = time.time()

    store_path = ensure_store_current(
        processed_dir=DEFAULT_PROCESSED_DIR,
        topics_path=DEFAULT_TOPICS_PATH,
        db_path=paper_store_path(DEFAULT_PROCESSED_DIR),
    )
    store_rows = list_paper_records(db_path=store_path, limit=10_000)
    store_by_id = {
        str(row.get("paper_id", "")).strip(): row
        for row in store_rows
        if str(row.get("paper_id", "")).strip()
    }
    for outcome in import_outcomes:
        if not isinstance(outcome, dict):
            continue
        paper_id = str(outcome.get("paper_id", "")).strip()
        status = str(outcome.get("status", "")).strip().lower()
        if not paper_id:
            continue
        if status in {"added", "succeeded", "success", "completed", "imported"}:
            paper_status_by_id[paper_id] = "ready"
            update_paper(paper_id, status="ready", error_message="", db_path=store_path)
            upsert_stage_status(
                paper_id=paper_id, stage="index", state="succeeded", db_path=store_path
            )
            upsert_stage_status(
                paper_id=paper_id,
                stage="graph_build",
                state="queued",
                db_path=store_path,
            )
            upsert_artifact(
                paper_id=paper_id,
                artifact_key="vector_index",
                artifact_type="vector_index",
                status="ready",
                path=str(DATA_DIR / "indexes" / "vec_index_embed.json"),
                metadata={"backend_name": "file"},
                db_path=store_path,
            )
        elif status in {"failed", "error"}:
            paper_status_by_id[paper_id] = "failed"
            update_paper(
                paper_id,
                status="failed",
                error_message=str(outcome.get("reason", "")).strip(),
                db_path=store_path,
            )
            upsert_stage_status(
                paper_id=paper_id,
                stage="index",
                state="failed",
                error_message=str(outcome.get("reason", "")).strip(),
                db_path=store_path,
            )
    store_rows = list_paper_records(db_path=store_path, limit=10_000)

    if topic_name:
        _emit_progress(
            stage="topic_assign",
            stage_processed=terminal_completed + terminal_failed,
            stage_total=max(1, len(copied)),
            message="更新专题映射",
            batch_completed=terminal_completed,
            batch_running=0,
            batch_failed=terminal_failed,
            current_item_name=None,
            recent_items=_attach_store_paper_metadata(
                _recent_items_from_outcomes(import_outcomes, stage="topic_assign"),
                store_rows=store_rows,
                paper_ids_by_name=paper_ids_by_name,
                paper_status_by_id=paper_status_by_id,
            ),
        )
        papers = load_papers()
        paper_paths = {
            Path(str(row.get("storage_path") or row.get("path", ""))).name: str(
                row.get("paper_id", "")
            )
            for row in papers
        }
        topics = load_topics()
        for src in copied:
            pid = paper_paths.get(src.name)
            if pid:
                topics = assign_topic(topics, topic_name, pid)
                assign_topic_record(topic_name, pid, db_path=store_path)
        save_topics(topics)
        store_rows = list_paper_records(db_path=store_path, limit=10_000)

    export_store_to_compat(
        processed_dir=DEFAULT_PROCESSED_DIR,
        topics_path=DEFAULT_TOPICS_PATH,
        db_path=store_path,
    )
    recent_items = _attach_store_paper_metadata(
        _recent_items_from_outcomes(import_outcomes, stage="done"),
        store_rows=store_rows,
        paper_ids_by_name=paper_ids_by_name,
        paper_status_by_id=paper_status_by_id,
    )
    _emit_progress(
        stage="done",
        stage_processed=max(1, len(copied)),
        stage_total=max(1, len(copied)),
        message="导入完成",
        batch_completed=terminal_completed,
        batch_running=0,
        batch_failed=terminal_failed,
        current_item_name=None,
        recent_items=recent_items,
    )
    return {
        "ok": True,
        "success_count": success_count,
        "failed_count": failed_count,
        "failure_reasons": failure_reasons,
        "import_summary": import_summary,
        "fallback_reason": ingest_report.get("fallback_reason"),
        "fallback_path": ingest_report.get("fallback_path"),
        "confidence_note": ingest_report.get("confidence_note"),
        "import_outcomes": import_outcomes,
        "recent_items": recent_items,
        "import_stage": {
            "updated_at": datetime.fromtimestamp(ingest_finished_at, timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        },
        "clean_stage": {
            "updated_at": datetime.fromtimestamp(ingest_finished_at, timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        },
        "index_stage": {
            "status": "success",
            "duration_sec": index_duration,
            "updated_at": datetime.fromtimestamp(index_finished_at, timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        },
        "next_steps": [
            "切换到 Chat，基于新导入论文开始提问。",
            "如需分组管理，先在 Library 里把论文加入专题。",
            "在 Ideas 中可将回答一键沉淀为灵感卡片。",
        ],
        "message": "导入完成，可以直接前往 Chat 提问或生成灵感卡片。",
    }
