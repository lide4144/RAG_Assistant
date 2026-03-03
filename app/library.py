from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.build_indexes import main as run_build_indexes
from app.fs_utils import atomic_text_writer
from app.fs_utils import FileLockTimeoutError, file_lock
from app.ingest import run_ingest
from app.paths import CONFIGS_DIR, DATA_DIR, RUNS_DIR

DEFAULT_PAPERS_PATH = DATA_DIR / "processed" / "papers.json"
DEFAULT_TOPICS_PATH = DATA_DIR / "library_topics.json"
DEFAULT_RAW_IMPORT_DIR = DATA_DIR / "raw" / "imported"
DEFAULT_PROCESSED_DIR = DATA_DIR / "processed"


def load_papers(path: Path = DEFAULT_PAPERS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "paper_id": str(row.get("paper_id", "")).strip(),
                "title": str(row.get("title", "")).strip(),
                "path": str(row.get("path", "")).strip(),
                "source_type": str(row.get("source_type", "pdf")).strip() or "pdf",
                "source_uri": str(row.get("source_uri", row.get("path", ""))).strip(),
                "imported_at": str(row.get("imported_at", "")).strip(),
                "status": str(row.get("status", "active")).strip() or "active",
                "fingerprint": str(row.get("fingerprint", "")).strip(),
                "ingest_metadata": row.get("ingest_metadata"),
            }
        )
    return [r for r in rows if r["paper_id"]]


def load_topics(path: Path = DEFAULT_TOPICS_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
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


def assign_topic(topics: dict[str, list[str]], topic: str, paper_id: str) -> dict[str, list[str]]:
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
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    def _progress(step: int, total: int, message: str) -> None:
        if progress_callback is not None:
            progress_callback(step, total, message)

    if not uploaded_files:
        return {
            "ok": False,
            "success_count": 0,
            "failed_count": 0,
            "failure_reasons": ["未选择任何文件。"],
            "next_steps": ["请先选择至少一个 PDF 文件。"],
            "message": "未选择文件",
        }

    DEFAULT_RAW_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    topic_name = str(topic).strip()
    success_count = 0
    failed_count = 0
    failure_reasons: list[str] = []
    copied: list[Path] = []
    _progress(1, 6, "检查上传文件")
    for src in uploaded_files:
        if not src.exists() or src.suffix.lower() != ".pdf":
            failed_count += 1
            failure_reasons.append(f"{src.name}: 仅支持 PDF 文件")
            continue
        dst = DEFAULT_RAW_IMPORT_DIR / src.name
        if dst.exists():
            dst = DEFAULT_RAW_IMPORT_DIR / f"{src.stem}-{src.stat().st_mtime_ns}.pdf"
        shutil.copyfile(src, dst)
        copied.append(dst)
        success_count += 1

    if not copied:
        return {
            "ok": False,
            "success_count": 0,
            "failed_count": failed_count,
            "failure_reasons": failure_reasons or ["未检测到可导入的 PDF 文件。"],
            "next_steps": ["请确认文件为 .pdf 且文件可读后重试。"],
            "message": "未检测到可导入的 PDF 文件",
        }

    with tempfile.TemporaryDirectory() as tmp:
        input_dir = Path(tmp) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        _progress(2, 6, "准备导入批次")
        for path in copied:
            shutil.copyfile(path, input_dir / path.name)

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
        _progress(3, 6, "执行入库与清洗")
        ingest_rc = run_ingest(ingest_args)
        ingest_report: dict[str, Any] = {}
        ingest_report_path = ingest_run_dir / "ingest_report.json"
        if ingest_report_path.exists():
            try:
                ingest_report = json.loads(ingest_report_path.read_text(encoding="utf-8"))
            except Exception:
                ingest_report = {}
        if ingest_rc != 0:
            if ingest_rc == 3:
                return {
                    "ok": False,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failure_reasons": failure_reasons + ["导入冲突：另一个导入或知识库准备任务正在运行。"],
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
                "failure_reasons": failure_reasons + ["入库失败：PDF 解析或清洗未通过。"],
                "next_steps": [
                    "确认 PDF 未损坏且包含可提取正文。",
                    "缩小批次先导入 1-2 篇定位问题文件。",
                ],
                    "message": "导入失败，请检查 PDF 内容是否可解析。",
                }

        _progress(4, 6, "准备知识库")
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
                return {
                    "ok": False,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failure_reasons": failure_reasons + ["知识库准备冲突：另一个任务正在运行。"],
                    "next_steps": ["请等待当前知识库准备任务完成后重试。"],
                    "message": "知识库准备冲突，请稍后重试。",
                    "import_summary": ingest_report.get("import_summary", {}),
                    "index_stage": {
                        "status": "conflict",
                        "duration_sec": round(time.perf_counter() - index_started, 3),
                    },
                }
        if build_rc != 0:
            index_status = "failed"
            return {
                "ok": False,
                "success_count": success_count,
                "failed_count": failed_count,
                "failure_reasons": failure_reasons + ["知识库准备失败：准备流程未完成。"],
                "next_steps": [
                    "稍后重试知识库准备。",
                    "若持续失败，请检查输出目录权限与磁盘空间。",
                ],
                "message": "论文已导入，但知识库准备失败，请稍后重试。",
                "import_summary": ingest_report.get("import_summary", {}),
                "index_stage": {
                    "status": index_status,
                    "duration_sec": round(time.perf_counter() - index_started, 3),
                },
            }
        index_duration = round(time.perf_counter() - index_started, 3)

    if topic_name:
        _progress(5, 6, "更新专题映射")
        papers = load_papers()
        paper_paths = {Path(row.get("path", "")).name: str(row.get("paper_id", "")) for row in papers}
        topics = load_topics()
        for src in copied:
            pid = paper_paths.get(src.name)
            if pid:
                topics = assign_topic(topics, topic_name, pid)
        save_topics(topics)

    _progress(6, 6, "导入完成")
    return {
        "ok": True,
        "success_count": success_count,
        "failed_count": failed_count,
        "failure_reasons": failure_reasons,
        "import_summary": ingest_report.get("import_summary", {}),
        "import_outcomes": ingest_report.get("import_outcomes", []),
        "index_stage": {"status": "success", "duration_sec": index_duration},
        "next_steps": [
            "切换到 Chat，基于新导入论文开始提问。",
            "如需分组管理，先在 Library 里把论文加入专题。",
            "在 Ideas 中可将回答一键沉淀为灵感卡片。",
        ],
        "message": "导入完成，可以直接前往 Chat 提问或生成灵感卡片。",
    }
