from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.clean_chunks import run_clean_chunks
from app.chunker import build_chunks
from app.config import load_and_validate_config
from app.document_structure import (
    STRUCTURE_DEGRADED,
    STRUCTURE_READY,
    STRUCTURE_UNAVAILABLE,
    load_structure_index,
    merge_structure_entries,
    save_structure_index,
)
from app.fs_utils import FileLockTimeoutError, file_lock
from app.marker_parser import MarkerParseError, parse_pdf_with_marker
from app.models import ChunkRecord, PageText, PaperRecord
from app.pipeline_runtime_config import resolve_effective_marker_llm, resolve_effective_marker_tuning, validate_marker_llm_payload
from app.paths import CONFIGS_DIR, RUNS_DIR
from app.paper_summary import build_paper_summaries
from app.parser import (
    choose_best_title,
    # Kept for backward-compatible test patch targets.
    extract_title,
    list_pdf_files,
    make_paper_id,
    parse_pdf_pages,
    stable_pdf_paper_id,
)
from app.runlog import create_run_dir, save_json, validate_trace_schema
from app.web_ingest import fetch_url_document, load_urls_from_inputs, structured_url_failure, url_meta_json
from app.writer import (
    ensure_dir,
    validate_chunks_jsonl,
    write_chunks_jsonl,
    write_paper_summaries_json,
    write_papers_json,
)

_MARKER_ENV_MAP = {
    "recognition_batch_size": "RECOGNITION_BATCH_SIZE",
    "detector_batch_size": "DETECTOR_BATCH_SIZE",
    "layout_batch_size": "LAYOUT_BATCH_SIZE",
    "ocr_error_batch_size": "OCR_ERROR_BATCH_SIZE",
    "table_rec_batch_size": "TABLE_REC_BATCH_SIZE",
    "model_dtype": "MODEL_DTYPE",
}
_MARKER_LLM_ENV_MAP = {
    "use_llm": "MARKER_USE_LLM",
    "llm_service": "MARKER_LLM_SERVICE",
    "gemini_api_key": "GEMINI_API_KEY",
    "vertex_project_id": "VERTEX_PROJECT_ID",
    "ollama_base_url": "OLLAMA_BASE_URL",
    "ollama_model": "OLLAMA_MODEL",
    "claude_api_key": "CLAUDE_API_KEY",
    "claude_model_name": "CLAUDE_MODEL_NAME",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "OPENAI_MODEL",
    "openai_base_url": "OPENAI_BASE_URL",
    "azure_endpoint": "AZURE_ENDPOINT",
    "azure_api_key": "AZURE_API_KEY",
    "deployment_name": "DEPLOYMENT_NAME",
}


@dataclass
class ImportCandidate:
    paper: PaperRecord
    chunks: list[ChunkRecord]
    structure_entry: dict[str, Any] | None = None


@dataclass
class ParsedPdf:
    pages: list[PageText]
    page_errors: list[str]
    metadata_title: str | None
    title_candidates: list[str]
    structured_title_candidates: list[dict[str, Any]]
    parser_engine: str
    parser_fallback: bool
    parser_fallback_stage: str
    parser_fallback_reason: str
    structured_segments: list[dict[str, Any]]
    diagnostics: dict[str, Any] | None = None
    structure_parse_status: str = STRUCTURE_UNAVAILABLE
    structure_parse_reason: str = ""
    marker_attempt_duration_sec: float = 0.0
    marker_stage_timings: dict[str, float] | None = None


def _build_marker_llm_summary(values: Any, source: dict[str, str], warnings: list[str]) -> dict[str, Any]:
    payload = asdict(values)
    _, field_errors = validate_marker_llm_payload(payload)
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
        value = str(payload.get(field, "") or "").strip()
        if value:
            summary_fields.append({"field": field, "value": value, "source": source.get(field, "default")})
    return {
        "use_llm": bool(payload.get("use_llm")),
        "llm_service": str(payload.get("llm_service", "")).strip(),
        "configured": bool(payload.get("use_llm")) and not field_errors,
        "field_errors": field_errors,
        "effective_source": source,
        "warnings": warnings,
        "summary_fields": summary_fields,
        "has_api_key": any(bool(str(payload.get(field, "")).strip()) for field in ("gemini_api_key", "claude_api_key", "openai_api_key", "azure_api_key")),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest PDFs and URLs into chunked JSON outputs.")
    parser.add_argument("--input", required=False, default=None, help="Input folder containing PDF files")
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="URL to ingest. Can be provided multiple times.",
    )
    parser.add_argument(
        "--url-file",
        default=None,
        help="Optional file containing URLs (one per line, comments allowed).",
    )
    parser.add_argument("--out", required=True, help="Output folder path")
    parser.add_argument(
        "--config",
        default=str(CONFIGS_DIR / "default.yaml"),
        help="Config file path (default: configs/default.yaml)",
    )
    parser.add_argument(
        "--question",
        default=None,
        help="Optional input question to include in run trace",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Run chunk cleaning after successful ingest and produce chunks_clean.jsonl",
    )
    parser.add_argument("--run-id", default="", help="Optional run id used as run directory name")
    parser.add_argument("--run-dir", default="", help="Optional explicit run directory path")
    parser.add_argument(
        "--lock-timeout-sec",
        type=float,
        default=10.0,
        help="Lock timeout for local output write section",
    )
    return parser.parse_args(argv)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_source_uri(value: str) -> str:
    return str(value or "").strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _paper_from_row(row: dict[str, Any]) -> PaperRecord:
    ingest_metadata_raw = row.get("ingest_metadata")
    ingest_metadata = ingest_metadata_raw if isinstance(ingest_metadata_raw, dict) else None
    return PaperRecord(
        paper_id=str(row.get("paper_id", "")).strip(),
        title=str(row.get("title", "")).strip(),
        path=str(row.get("path", "")).strip(),
        source_type=str(row.get("source_type", "pdf")).strip() or "pdf",
        source_uri=str(row.get("source_uri", row.get("path", ""))).strip(),
        parser_engine=str(row.get("parser_engine", "legacy")).strip() or "legacy",
        title_source=str(row.get("title_source", "")).strip(),
        title_confidence=_to_float(row.get("title_confidence", 0.0), default=0.0),
        imported_at=str(row.get("imported_at", "")).strip(),
        status=str(row.get("status", "active")).strip() or "active",
        fingerprint=str(row.get("fingerprint", "")).strip(),
        ingest_metadata=ingest_metadata,
    )


def _load_existing_papers(path: Path) -> list[PaperRecord]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    out: list[PaperRecord] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        paper = _paper_from_row(row)
        if paper.paper_id:
            out.append(paper)
    return out


def _load_existing_chunks(path: Path) -> list[ChunkRecord]:
    if not path.exists():
        return []
    out: list[ChunkRecord] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except Exception:
                    continue
                chunk_id = str(row.get("chunk_id", "")).strip()
                paper_id = str(row.get("paper_id", "")).strip()
                text = str(row.get("text", "")).strip()
                page_start_raw = row.get("page_start", 1)
                try:
                    page_start = int(page_start_raw)
                except Exception:
                    page_start = 1
                if not chunk_id or not paper_id or not text:
                    continue
                out.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        paper_id=paper_id,
                        page_start=max(1, page_start),
                        text=text,
                    )
                )
    except Exception:
        return []
    return out


def _group_chunks_by_paper(chunks: list[ChunkRecord]) -> dict[str, list[ChunkRecord]]:
    grouped: dict[str, list[ChunkRecord]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.paper_id, []).append(chunk)
    return grouped


def _build_match_indexes(existing: dict[str, PaperRecord]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    by_fingerprint: dict[str, str] = {}
    by_source: dict[str, str] = {}
    by_legacy: dict[str, str] = {}
    for pid, row in existing.items():
        fp = str(row.fingerprint or "").strip()
        if fp and fp not in by_fingerprint:
            by_fingerprint[fp] = pid
        src = _normalize_source_uri(row.source_uri)
        if src and src not in by_source:
            by_source[src] = pid
        metadata = row.ingest_metadata if isinstance(row.ingest_metadata, dict) else {}
        legacy_id = str(metadata.get("legacy_paper_id", "")).strip()
        if legacy_id and legacy_id not in by_legacy:
            by_legacy[legacy_id] = pid
    return by_fingerprint, by_source, by_legacy


def _merge_candidates(
    existing_papers: list[PaperRecord],
    existing_chunks: list[ChunkRecord],
    candidates: list[ImportCandidate],
) -> tuple[list[PaperRecord], list[ChunkRecord], dict[str, Any]]:
    paper_map: dict[str, PaperRecord] = {row.paper_id: row for row in existing_papers if row.paper_id}
    chunk_groups = _group_chunks_by_paper(existing_chunks)
    by_fingerprint, by_source, by_legacy = _build_match_indexes(paper_map)

    added = 0
    skipped = 0
    conflicts = 0
    outcomes: list[dict[str, Any]] = []

    for item in candidates:
        paper = item.paper
        chunks = item.chunks
        pid = str(paper.paper_id).strip()
        if not pid:
            continue

        matched_pid = ""
        if pid in paper_map:
            matched_pid = pid
        elif paper.fingerprint and paper.fingerprint in by_fingerprint:
            matched_pid = by_fingerprint[paper.fingerprint]
        elif paper.source_uri and paper.source_uri in by_source:
            matched_pid = by_source[paper.source_uri]
        else:
            legacy_id = ""
            if isinstance(paper.ingest_metadata, dict):
                legacy_id = str(paper.ingest_metadata.get("legacy_paper_id", "")).strip()
            if legacy_id and legacy_id in by_legacy:
                matched_pid = by_legacy[legacy_id]

        if matched_pid:
            matched = paper_map[matched_pid]
            same_source = bool(paper.source_uri and matched.source_uri and paper.source_uri == matched.source_uri)
            if (
                same_source
                and matched.fingerprint
                and paper.fingerprint
                and matched.fingerprint != paper.fingerprint
            ):
                conflicts += 1
                outcomes.append(
                    {
                        "paper_id": matched_pid,
                        "title": matched.title or paper.title,
                        "source_uri": paper.source_uri,
                        "status": "conflict",
                        "reason": "same_source_different_fingerprint",
                    }
                )
                continue

            skipped += 1
            patched = False
            if not matched.fingerprint and paper.fingerprint:
                matched.fingerprint = paper.fingerprint
                patched = True
            if not matched.imported_at and paper.imported_at:
                matched.imported_at = paper.imported_at
                patched = True
            if not matched.source_uri and paper.source_uri:
                matched.source_uri = paper.source_uri
                patched = True
            if not matched.status:
                matched.status = "active"
                patched = True
            if patched:
                paper_map[matched_pid] = matched
                fp = str(matched.fingerprint or "").strip()
                if fp:
                    by_fingerprint[fp] = matched_pid
                src = _normalize_source_uri(matched.source_uri)
                if src:
                    by_source[src] = matched_pid

            outcomes.append(
                {
                    "paper_id": matched_pid,
                    "title": matched.title or paper.title,
                    "source_uri": paper.source_uri,
                    "status": "skipped",
                    "reason": "already_exists",
                }
            )
            continue

        paper_map[pid] = paper
        chunk_groups[pid] = list(chunks)
        if paper.fingerprint:
            by_fingerprint[paper.fingerprint] = pid
        if paper.source_uri:
            by_source[paper.source_uri] = pid
        if isinstance(paper.ingest_metadata, dict):
            legacy_id = str(paper.ingest_metadata.get("legacy_paper_id", "")).strip()
            if legacy_id:
                by_legacy[legacy_id] = pid

        added += 1
        outcomes.append(
            {
                "paper_id": pid,
                "title": paper.title,
                "source_uri": paper.source_uri,
                "status": "added",
                "reason": "new_paper",
            }
        )

    merged_papers = sorted(paper_map.values(), key=lambda x: (x.imported_at, x.title, x.paper_id))
    merged_chunks: list[ChunkRecord] = []
    for row in merged_papers:
        merged_chunks.extend(chunk_groups.get(row.paper_id, []))

    summary = {
        "added": added,
        "skipped": skipped,
        "conflicts": conflicts,
        "outcomes": outcomes,
    }
    return merged_papers, merged_chunks, summary


def _marker_preflight_check(config: Any) -> tuple[bool, str, str]:
    marker_enabled = bool(getattr(config, "marker_enabled", True))
    if not marker_enabled:
        return True, "", ""
    try:
        import marker.converters.pdf as converter_module

        _ = getattr(converter_module, "PdfConverter")
    except Exception as exc:
        return False, "import_converter", f"marker preflight failed: {exc}"

    try:
        from marker import models as marker_models

        _ = getattr(marker_models, "create_model_dict")
    except Exception as exc:
        return False, "model_loader", f"marker preflight failed: {exc}"

    try:
        from surya.settings import settings as surya_settings

        cache_dir = Path(str(surya_settings.MODEL_CACHE_DIR or "")).expanduser()
        if not str(cache_dir).strip():
            return False, "model_cache_access", "marker preflight failed: MODEL_CACHE_DIR is empty"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(cache_dir, os.W_OK):
            return False, "model_cache_access", f"marker preflight failed: cache dir not writable: {cache_dir}"
    except Exception as exc:
        return False, "model_cache_access", f"marker preflight failed: {exc}"

    return True, "", ""


def _parse_pdf_with_fallback(
    pdf_path: Path,
    config: Any,
    *,
    marker_ready: bool,
    marker_preflight_stage: str,
    marker_preflight_reason: str,
) -> ParsedPdf:
    marker_enabled = bool(getattr(config, "marker_enabled", True))
    marker_timeout = float(getattr(config, "marker_timeout_sec", 30.0))
    if marker_enabled and not marker_ready:
        pages, page_errors, metadata_title = parse_pdf_pages(pdf_path)
        return ParsedPdf(
            pages=pages,
            page_errors=page_errors,
            metadata_title=metadata_title,
            title_candidates=[],
            structured_title_candidates=[],
            parser_engine="legacy",
            parser_fallback=True,
            parser_fallback_stage=marker_preflight_stage or "preflight",
            parser_fallback_reason=marker_preflight_reason or "marker preflight failed",
            structured_segments=[],
            diagnostics={},
            structure_parse_status=STRUCTURE_UNAVAILABLE,
            structure_parse_reason=marker_preflight_reason or "marker_preflight_failed",
            marker_attempt_duration_sec=0.0,
            marker_stage_timings={},
        )
    if marker_enabled and marker_ready:
        marker_started = time.perf_counter()
        try:
            marker_result = parse_pdf_with_marker(pdf_path, timeout_sec=marker_timeout)
            structured_segments = [
                {
                    "page": block.page_num,
                    "text": block.text,
                    "heading_level": block.heading_level,
                    "block_type": block.block_type,
                    "markdown_source": block.markdown_source,
                }
                for block in marker_result.blocks
            ]
            return ParsedPdf(
                pages=marker_result.pages,
                page_errors=[],
                metadata_title=None,
                title_candidates=marker_result.title_candidates,
                structured_title_candidates=marker_result.structured_title_candidates,
                parser_engine="marker",
                parser_fallback=False,
                parser_fallback_stage="",
                parser_fallback_reason="",
                structured_segments=structured_segments,
                diagnostics=marker_result.diagnostics,
                structure_parse_status=STRUCTURE_READY if structured_segments else STRUCTURE_UNAVAILABLE,
                structure_parse_reason="" if structured_segments else "marker_blocks_empty",
                marker_attempt_duration_sec=round(time.perf_counter() - marker_started, 3),
                marker_stage_timings=marker_result.stage_timings,
            )
        except MarkerParseError as exc:
            pages, page_errors, metadata_title = parse_pdf_pages(pdf_path)
            stage = str(getattr(exc, "stage", "")).strip() or "unknown"
            return ParsedPdf(
                pages=pages,
                page_errors=page_errors,
                metadata_title=metadata_title,
                title_candidates=[],
                structured_title_candidates=[],
                parser_engine="legacy",
                parser_fallback=True,
                parser_fallback_stage=stage,
                parser_fallback_reason=str(exc),
                structured_segments=[],
                diagnostics={},
                structure_parse_status=STRUCTURE_UNAVAILABLE,
                structure_parse_reason=stage,
                marker_attempt_duration_sec=round(time.perf_counter() - marker_started, 3),
                marker_stage_timings={},
            )
    pages, page_errors, metadata_title = parse_pdf_pages(pdf_path)
    return ParsedPdf(
        pages=pages,
        page_errors=page_errors,
        metadata_title=metadata_title,
        title_candidates=[],
        structured_title_candidates=[],
        parser_engine="legacy",
        parser_fallback=False,
        parser_fallback_stage="",
        parser_fallback_reason="",
        structured_segments=[],
        diagnostics={},
        structure_parse_status=STRUCTURE_UNAVAILABLE,
        structure_parse_reason="marker_disabled_or_legacy_parser",
        marker_attempt_duration_sec=0.0,
        marker_stage_timings={},
    )


def _build_structure_entry(
    *,
    paper_id: str,
    parser_engine: str,
    parser_fallback: bool,
    structure_parse_status: str,
    structure_parse_reason: str,
    structured_segments: list[dict[str, Any]],
    chunks: list[ChunkRecord],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "paper_id": paper_id,
        "parser_engine": parser_engine,
        "structure_parse_status": structure_parse_status,
        "structure_parse_reason": structure_parse_reason,
        "sections": [],
        "warnings": [],
    }
    if parser_fallback:
        entry["structure_parse_status"] = STRUCTURE_UNAVAILABLE
        entry["structure_parse_reason"] = structure_parse_reason or "marker_fallback"
        return entry
    if not structured_segments:
        entry["structure_parse_status"] = STRUCTURE_UNAVAILABLE
        entry["structure_parse_reason"] = structure_parse_reason or "marker_blocks_empty"
        return entry

    sections: list[dict[str, Any]] = []
    section_lookup: dict[str, dict[str, Any]] = {}
    stack: list[dict[str, Any]] = []
    heading_counter = 0
    for block in structured_segments:
        level = block.get("heading_level")
        if not isinstance(level, int) or level <= 0:
            continue
        title = str(block.get("text", "")).strip()
        if not title:
            continue
        heading_counter += 1
        page_num = max(1, int(block.get("page", 1) or 1))
        while stack and int(stack[-1]["section_level"]) >= level:
            stack.pop()
        parent_section_id = str(stack[-1]["section_id"]) if stack else None
        heading_path = [str(item["section_title"]) for item in stack] + [title]
        section_id = f"{paper_id}:sec:{heading_counter:04d}"
        local_section_id = f"sec-{heading_counter:04d}"
        row = {
            "section_id": section_id,
            "paper_id": paper_id,
            "section_title": title,
            "section_level": level,
            "heading_path": heading_path,
            "start_page": page_num,
            "end_page": page_num,
            "parent_section_id": parent_section_id,
            "child_chunk_ids": [],
        }
        sections.append(row)
        section_lookup[section_id] = row
        section_lookup[local_section_id] = row
        stack.append(row)

    if not sections:
        entry["structure_parse_status"] = STRUCTURE_UNAVAILABLE
        entry["structure_parse_reason"] = structure_parse_reason or "no_heading_blocks"
        return entry

    for chunk in chunks:
        if not chunk.section_id:
            continue
        row = section_lookup.get(chunk.section_id)
        if row is None:
            continue
        row["end_page"] = max(int(row.get("end_page", chunk.page_start) or chunk.page_start), int(chunk.page_start))
        row["start_page"] = min(int(row.get("start_page", chunk.page_start) or chunk.page_start), int(chunk.page_start))
        row["child_chunk_ids"].append(chunk.chunk_id)

    indexed_sections: list[dict[str, Any]] = []
    unmapped = 0
    for row in sections:
        child_chunk_ids = [str(x).strip() for x in row.get("child_chunk_ids", []) if str(x).strip()]
        if not child_chunk_ids:
            unmapped += 1
            continue
        row["child_chunk_ids"] = child_chunk_ids
        indexed_sections.append(row)

    entry["sections"] = indexed_sections
    entry["section_count"] = len(sections)
    entry["indexed_section_count"] = len(indexed_sections)
    if not indexed_sections:
        entry["structure_parse_status"] = STRUCTURE_DEGRADED
        entry["structure_parse_reason"] = "no_section_chunk_mapping"
        entry["warnings"] = ["section_chunk_mapping_missing"]
        return entry

    coverage_ratio = len(indexed_sections) / max(1, len(sections))
    if coverage_ratio < 0.6 or unmapped > 0:
        entry["structure_parse_status"] = STRUCTURE_DEGRADED
        entry["structure_parse_reason"] = "partial_section_chunk_mapping"
        entry["warnings"] = ["section_chunk_mapping_partial"]
    else:
        entry["structure_parse_status"] = STRUCTURE_READY
        entry["structure_parse_reason"] = ""
    return entry


def _aggregate_parser_observability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    parser_engine_counts: dict[str, int] = {}
    title_source_counts: dict[str, int] = {}
    parser_fallback_stage_counts: dict[str, int] = {}
    structure_status_counts: dict[str, int] = {}
    structured_missing_count = 0
    structured_missing_reasons: dict[str, int] = {}
    confidences: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parser_engine = str(row.get("parser_engine", "")).strip() or "unknown"
        title_source = str(row.get("title_source", "")).strip() or "unknown"
        parser_engine_counts[parser_engine] = parser_engine_counts.get(parser_engine, 0) + 1
        title_source_counts[title_source] = title_source_counts.get(title_source, 0) + 1
        if bool(row.get("parser_fallback")):
            stage = str(row.get("parser_fallback_stage", "")).strip() or "unknown"
            parser_fallback_stage_counts[stage] = parser_fallback_stage_counts.get(stage, 0) + 1
        structure_status = str(row.get("structure_parse_status", "")).strip() or STRUCTURE_UNAVAILABLE
        structure_status_counts[structure_status] = structure_status_counts.get(structure_status, 0) + 1
        if bool(row.get("structured_segments_missing")):
            structured_missing_count += 1
            reason = str(row.get("structured_segments_missing_reason", "")).strip() or "unknown"
            structured_missing_reasons[reason] = structured_missing_reasons.get(reason, 0) + 1
        try:
            confidence = float(row.get("title_confidence", 0.0))
        except Exception:
            confidence = 0.0
        confidences.append(confidence)
    confidences.sort()
    if not confidences:
        stats = {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0}
    else:
        count = len(confidences)
        p50 = confidences[int((count - 1) * 0.5)]
        p90 = confidences[int((count - 1) * 0.9)]
        stats = {
            "count": count,
            "min": round(min(confidences), 4),
            "max": round(max(confidences), 4),
            "mean": round(sum(confidences) / count, 4),
            "p50": round(p50, 4),
            "p90": round(p90, 4),
        }
    return {
        "parser_engine_counts": parser_engine_counts,
        "title_source_counts": title_source_counts,
        "parser_fallback_stage_counts": parser_fallback_stage_counts,
        "structure_status_counts": structure_status_counts,
        "structured_segments_missing_count": structured_missing_count,
        "structured_segments_missing_reasons": structured_missing_reasons,
        "title_confidence_stats": stats,
    }


def run_ingest(args: argparse.Namespace) -> int:
    config, config_warnings = load_and_validate_config(args.config)
    marker_tuning_effective = resolve_effective_marker_tuning()
    marker_tuning_values = marker_tuning_effective.values
    marker_tuning_source = marker_tuning_effective.source
    marker_llm_effective = resolve_effective_marker_llm()
    marker_llm_values = marker_llm_effective.values
    marker_llm_summary = _build_marker_llm_summary(marker_llm_values, marker_llm_effective.source, marker_llm_effective.warnings)
    for field, env_name in _MARKER_ENV_MAP.items():
        os.environ[env_name] = str(getattr(marker_tuning_values, field))
    for field, env_name in _MARKER_LLM_ENV_MAP.items():
        os.environ[env_name] = str(getattr(marker_llm_values, field))

    run_dir_arg = str(getattr(args, "run_dir", "")).strip()
    run_id = str(getattr(args, "run_id", "")).strip()
    run_dir = Path(run_dir_arg) if run_dir_arg else create_run_dir(RUNS_DIR, timestamp=(run_id or None))
    run_dir.mkdir(parents=True, exist_ok=True)
    output_dir = ensure_dir(args.out)
    ensure_dir(Path(output_dir).parent / "reports")

    for warning in config_warnings:
        print(f"[config-warning] {warning}", file=sys.stderr)

    input_dir = getattr(args, "input", None)
    pdf_paths = list_pdf_files(input_dir) if input_dir else []
    urls, invalid_urls = load_urls_from_inputs(
        list(getattr(args, "url", []) or []),
        getattr(args, "url_file", None),
    )
    if not pdf_paths and not urls:
        if input_dir:
            print(f"No PDF files found under: {input_dir}", file=sys.stderr)
        else:
            print("No valid input detected (PDF or URL).", file=sys.stderr)
        return 2

    now_iso = _now_iso()
    candidates: list[ImportCandidate] = []
    parse_errors: list[str] = []
    paper_failures: list[str] = []
    url_failures: list[dict[str, str]] = list(invalid_urls)
    parser_observability: list[dict[str, Any]] = []
    structure_entries: list[dict[str, Any]] = []
    marker_ready, marker_preflight_stage, marker_preflight_reason = _marker_preflight_check(config)

    for pdf_path in pdf_paths:
        stable_paper_id, fingerprint = stable_pdf_paper_id(pdf_path)
        legacy_paper_id = make_paper_id(pdf_path)
        try:
            parsed_pdf = _parse_pdf_with_fallback(
                pdf_path,
                config,
                marker_ready=marker_ready,
                marker_preflight_stage=marker_preflight_stage,
                marker_preflight_reason=marker_preflight_reason,
            )
        except Exception as exc:
            paper_failures.append(f"{pdf_path.name}: {exc}")
            continue

        parse_errors.extend(parsed_pdf.page_errors)
        if not parsed_pdf.pages:
            paper_failures.append(f"{pdf_path.name}: no readable pages")
            continue

        title_decision = choose_best_title(
            metadata_title=parsed_pdf.metadata_title,
            pages=parsed_pdf.pages,
            title_candidates=parsed_pdf.structured_title_candidates or parsed_pdf.title_candidates,
            confidence_threshold=config.title_confidence_threshold,
            blacklist_patterns=config.title_blacklist_patterns,
        )
        chunk_kwargs: dict[str, Any] = {
            "paper_id": stable_paper_id,
            "pages": parsed_pdf.pages,
            "chunk_size": config.chunk_size,
            "overlap": config.overlap,
        }
        if parsed_pdf.structured_segments:
            chunk_kwargs["structured_segments"] = parsed_pdf.structured_segments
        structured_segments_missing = parsed_pdf.parser_engine == "marker" and not bool(parsed_pdf.structured_segments)
        structured_segments_missing_reason = "marker_blocks_empty" if structured_segments_missing else ""
        chunks = build_chunks(**chunk_kwargs)
        if not chunks:
            paper_failures.append(f"{pdf_path.name}: no chunks generated")
            continue
        structure_entry = _build_structure_entry(
            paper_id=stable_paper_id,
            parser_engine=parsed_pdf.parser_engine,
            parser_fallback=parsed_pdf.parser_fallback,
            structure_parse_status=parsed_pdf.structure_parse_status,
            structure_parse_reason=parsed_pdf.structure_parse_reason,
            structured_segments=parsed_pdf.structured_segments,
            chunks=chunks,
        )

        source_uri = f"pdf://sha1/{fingerprint}"
        block_types = sorted(
            {
                str(block.get("block_type", "")).strip()
                for block in parsed_pdf.structured_segments
                if str(block.get("block_type", "")).strip()
            }
        )
        markdown_diagnostics = (
            parsed_pdf.diagnostics.get("markdown", {})
            if isinstance(parsed_pdf.diagnostics, dict)
            else {}
        )
        block_semantics = (
            parsed_pdf.diagnostics.get("block_semantics", {})
            if isinstance(parsed_pdf.diagnostics, dict)
            else {}
        )
        if not block_semantics:
            block_semantics = {
                "available": bool(block_types),
                "preserved": bool(block_types),
            }
        parser_observability.append(
            {
                "paper_id": stable_paper_id,
                "source_uri": source_uri,
                "parser_engine": parsed_pdf.parser_engine,
                "parser_fallback": parsed_pdf.parser_fallback,
                "parser_fallback_stage": parsed_pdf.parser_fallback_stage,
                "parser_fallback_reason": parsed_pdf.parser_fallback_reason,
                "marker_tuning": {
                    **asdict(marker_tuning_values),
                    "effective_source": marker_tuning_source,
                },
                "marker_timing": {
                    "attempt_duration_sec": round(float(parsed_pdf.marker_attempt_duration_sec or 0.0), 3),
                    "stage_timings": parsed_pdf.marker_stage_timings or {},
                },
                "marker_llm": {
                    "use_llm": marker_llm_summary["use_llm"],
                    "llm_service": marker_llm_summary["llm_service"],
                    "configured": marker_llm_summary["configured"],
                    "summary_fields": marker_llm_summary["summary_fields"],
                    "effective_source": marker_llm_summary["effective_source"],
                    "degraded": bool(parsed_pdf.parser_fallback) and bool(marker_llm_summary["use_llm"]),
                },
                "structured_segments_missing": structured_segments_missing,
                "structured_segments_missing_reason": structured_segments_missing_reason,
                "structure_parse_status": structure_entry.get("structure_parse_status", STRUCTURE_UNAVAILABLE),
                "structure_parse_reason": structure_entry.get("structure_parse_reason", ""),
                "section_count": int(structure_entry.get("section_count", 0) or 0),
                "indexed_section_count": int(structure_entry.get("indexed_section_count", 0) or 0),
                "title_source": title_decision.source,
                "title_layer": title_decision.adopted_layer,
                "title_confidence": round(float(title_decision.confidence), 4),
                "title_decision_trace": list(title_decision.decision_trace or []),
                "structured_title_candidates": parsed_pdf.structured_title_candidates,
                "structured_title_candidate_counts": (
                    parsed_pdf.diagnostics.get("structured_title_candidate_counts", {})
                    if isinstance(parsed_pdf.diagnostics, dict)
                    else {}
                ),
                "markdown_available": bool(markdown_diagnostics.get("available")),
                "markdown_consumption_status": str(markdown_diagnostics.get("consumption_status", "missing")),
                "block_semantics_available": bool(block_semantics.get("available")),
                "block_semantics_preserved": bool(block_semantics.get("preserved")),
                "block_types": block_types,
            }
        )
        structure_entries.append(structure_entry)
        candidates.append(
            ImportCandidate(
                paper=PaperRecord(
                    paper_id=stable_paper_id,
                    title=title_decision.title,
                    path=str(pdf_path),
                    source_type="pdf",
                    source_uri=source_uri,
                    parser_engine=parsed_pdf.parser_engine,
                    title_source=title_decision.source,
                    title_confidence=round(float(title_decision.confidence), 4),
                    imported_at=now_iso,
                    status="active",
                    fingerprint=fingerprint,
                    ingest_metadata={
                        "file_name": pdf_path.name,
                        "legacy_paper_id": legacy_paper_id,
                        "legacy_source_path": str(pdf_path.resolve()),
                        "parser_fallback": parsed_pdf.parser_fallback,
                        "parser_fallback_stage": parsed_pdf.parser_fallback_stage,
                        "parser_fallback_reason": parsed_pdf.parser_fallback_reason,
                        "marker_attempt_duration_sec": round(float(parsed_pdf.marker_attempt_duration_sec or 0.0), 3),
                        "marker_stage_timings": parsed_pdf.marker_stage_timings or {},
                        "structure_parse_status": structure_entry.get("structure_parse_status", STRUCTURE_UNAVAILABLE),
                        "structure_parse_reason": structure_entry.get("structure_parse_reason", ""),
                        "section_count": int(structure_entry.get("section_count", 0) or 0),
                        "indexed_section_count": int(structure_entry.get("indexed_section_count", 0) or 0),
                        "title_layer": title_decision.adopted_layer,
                        "title_decision_trace": list(title_decision.decision_trace or []),
                        "structured_title_candidates": parsed_pdf.structured_title_candidates,
                        "structured_title_candidate_counts": (
                            parsed_pdf.diagnostics.get("structured_title_candidate_counts", {})
                            if isinstance(parsed_pdf.diagnostics, dict)
                            else {}
                        ),
                        "markdown_available": bool(markdown_diagnostics.get("available")),
                        "markdown_consumption_status": str(markdown_diagnostics.get("consumption_status", "missing")),
                        "block_semantics_available": bool(block_semantics.get("available")),
                        "block_semantics_preserved": bool(block_semantics.get("preserved")),
                        "block_types": block_types,
                    },
                ),
                chunks=chunks,
                structure_entry=structure_entry,
            )
        )

    for url in urls:
        fetched = fetch_url_document(url)
        if not fetched.ok:
            url_failures.append(structured_url_failure(fetched))
            continue

        normalized_url = str(url).strip()
        content_fingerprint = hashlib.sha1(fetched.text.encode("utf-8", errors="ignore")).hexdigest()
        paper_id = f"url_{hashlib.sha1(normalized_url.encode('utf-8')).hexdigest()[:12]}"
        pages = [PageText(page_num=1, text=fetched.text)]
        chunks = build_chunks(
            paper_id=paper_id,
            pages=pages,
            chunk_size=config.chunk_size,
            overlap=config.overlap,
        )
        if not chunks:
            url_failures.append(
                {
                    "source_type": "url",
                    "source_uri": normalized_url,
                    "reason": "chunk_generation_failed",
                    "detail": "no chunks generated",
                }
            )
            continue

        candidates.append(
            ImportCandidate(
                paper=PaperRecord(
                    paper_id=paper_id,
                    title=fetched.title,
                    path=normalized_url,
                    source_type="url",
                    source_uri=normalized_url,
                    parser_engine="url",
                    title_source="url_content",
                    title_confidence=1.0,
                    imported_at=now_iso,
                    status="active",
                    fingerprint=content_fingerprint,
                    ingest_metadata=url_meta_json(
                        fetched_at=fetched.fetched_at,
                        http_status=fetched.http_status,
                    ),
                ),
                chunks=chunks,
                structure_entry={
                    "paper_id": paper_id,
                    "parser_engine": "url",
                    "structure_parse_status": STRUCTURE_UNAVAILABLE,
                    "structure_parse_reason": "url_source_no_structure",
                    "sections": [],
                    "warnings": [],
                    "section_count": 0,
                    "indexed_section_count": 0,
                },
            )
        )

    chunks_file = output_dir / "chunks.jsonl"
    papers_file = output_dir / "papers.json"
    paper_summary_file = output_dir / "paper_summary.json"
    structure_index_file = output_dir / "structure_index.json"
    lock_path = output_dir / ".ingest.lock"
    lock_timeout = float(getattr(args, "lock_timeout_sec", 10.0))

    try:
        with file_lock(lock_path, timeout_sec=lock_timeout):
            existing_papers = _load_existing_papers(papers_file)
            existing_chunks = _load_existing_chunks(chunks_file)
            merged_papers, merged_chunks, merge_summary = _merge_candidates(
                existing_papers,
                existing_chunks,
                candidates,
            )
            write_chunks_jsonl(merged_chunks, chunks_file)
            write_papers_json(merged_papers, papers_file)
            structure_index = merge_structure_entries(
                load_structure_index(chunks_file),
                [row.structure_entry for row in candidates if isinstance(row.structure_entry, dict)],
            )
            save_structure_index(structure_index, chunks_file)
    except FileLockTimeoutError:
        print(
            f"Another import/index process is active for {output_dir}. Please retry in a moment.",
            file=sys.stderr,
        )
        return 3

    previous_hashes: dict[str, str] = {}
    if paper_summary_file.exists():
        try:
            raw_prev = json.loads(paper_summary_file.read_text(encoding="utf-8"))
            if isinstance(raw_prev, list):
                for row in raw_prev:
                    if not isinstance(row, dict):
                        continue
                    pid = str(row.get("paper_id", "")).strip()
                    snapshot = str(row.get("chunk_snapshot_hash", "")).strip()
                    if pid and snapshot:
                        previous_hashes[pid] = snapshot
        except Exception:
            previous_hashes = {}

    paper_summaries, rebuilt_summary_paper_ids = build_paper_summaries(
        merged_papers,
        merged_chunks,
        previous_hashes=previous_hashes,
        summary_version="v1",
    )
    try:
        with file_lock(lock_path, timeout_sec=lock_timeout):
            write_paper_summaries_json(paper_summaries, paper_summary_file)
    except FileLockTimeoutError:
        print(
            f"Another import/index process is active for {output_dir}. Please retry in a moment.",
            file=sys.stderr,
        )
        return 3

    ok_chunks, chunk_errors = validate_chunks_jsonl(chunks_file)
    clean_enabled = bool(args.clean)
    clean_output = str(output_dir / "chunks_clean.jsonl") if clean_enabled else None
    clean_success = False
    clean_error: str | None = None

    if merged_papers and ok_chunks and clean_enabled:
        try:
            run_clean_chunks(chunks_file, output_dir / "chunks_clean.jsonl")
            clean_success = True
        except Exception as exc:
            clean_error = str(exc)
            print(f"[clean-error] {clean_error}", file=sys.stderr)

    outcomes = list(merge_summary.get("outcomes", []))
    for failed in paper_failures:
        outcomes.append(
            {
                "paper_id": "",
                "title": "",
                "source_uri": "",
                "status": "failed",
                "reason": failed,
            }
        )
    for failed in url_failures:
        outcomes.append(
            {
                "paper_id": "",
                "title": "",
                "source_uri": str(failed.get("source_uri", "")),
                "status": "failed",
                "reason": str(failed.get("reason", "unknown")),
            }
        )

    import_summary = {
        "added": int(merge_summary.get("added", 0)),
        "skipped": int(merge_summary.get("skipped", 0)),
        "conflicts": int(merge_summary.get("conflicts", 0)),
        "failed": len(paper_failures) + len(url_failures),
        "total_candidates": len(candidates),
        "degraded": any(bool(row.get("parser_fallback")) for row in parser_observability),
    }
    fallback_rows = [row for row in parser_observability if isinstance(row, dict) and bool(row.get("parser_fallback"))]
    fallback_reason = str(fallback_rows[0].get("parser_fallback_reason", "")).strip() if fallback_rows else None
    fallback_stage = str(fallback_rows[0].get("parser_fallback_stage", "")).strip() if fallback_rows else None
    fallback_path = f"marker -> legacy ({fallback_stage or 'unknown'})" if fallback_rows else None
    confidence_note = (
        "当前导入结果包含降级路径，结构化质量可能低于启用 Marker LLM/完整 Marker 解析时的结果。"
        if fallback_rows
        else "当前导入结果未检测到 Marker 降级路径。"
    )

    report = {
        "input_dir": str(args.input),
        "url_total": len(urls),
        "url_invalid_or_failed": url_failures,
        "paper_summary_total": len(paper_summaries),
        "paper_summary_rebuilt_count": len(rebuilt_summary_paper_ids),
        "paper_summary_rebuilt_paper_ids": rebuilt_summary_paper_ids[:50],
        "output_dir": str(output_dir),
        "run_dir": str(run_dir),
        "pdf_total": len(pdf_paths),
        "papers_processed": len(candidates),
        "papers_total_after_merge": len(merged_papers),
        "chunks_total_after_merge": len(merged_chunks),
        "page_parse_errors": parse_errors,
        "paper_failures": paper_failures,
        "config_warnings": config_warnings,
        "effective_config": {
            "chunk_size": config.chunk_size,
            "overlap": config.overlap,
            "marker_enabled": config.marker_enabled,
            "marker_timeout_sec": config.marker_timeout_sec,
            "title_confidence_threshold": config.title_confidence_threshold,
            "top_k_retrieval": config.top_k_retrieval,
            "alpha_expansion": config.alpha_expansion,
            "top_n_evidence": config.top_n_evidence,
            "fusion_weight": config.fusion_weight,
            "RRF_k": config.RRF_k,
            "sufficiency_threshold": config.sufficiency_threshold,
            "table_list_downweight": config.table_list_downweight,
        },
        "marker_tuning": {
            **asdict(marker_tuning_values),
            "effective_source": marker_tuning_source,
            "warnings": marker_tuning_effective.warnings,
        },
        "marker_llm": marker_llm_summary,
        "chunk_validation_ok": ok_chunks,
        "chunk_validation_errors": chunk_errors,
        "clean_enabled": clean_enabled,
        "clean_output": clean_output,
        "clean_success": clean_success,
        "clean_error": clean_error,
        "import_summary": import_summary,
        "fallback_reason": fallback_reason,
        "fallback_path": fallback_path,
        "confidence_note": confidence_note,
        "import_outcomes": outcomes,
        "parser_observability": parser_observability,
        "structure_index_path": str(structure_index_file),
        "structured_segments_missing": [
            row
            for row in parser_observability
            if bool(row.get("structured_segments_missing"))
        ],
    }
    save_json(report, run_dir / "ingest_report.json")

    trace = {
        "input_question": args.question,
        "rewrite_query": None,
        "retrieval_top_k": [],
        "expansion_added_chunks": [],
        "rerank_top_n": [],
        "parser_fallback": any(bool(row.get("parser_fallback")) for row in parser_observability),
        "parser_fallback_reasons": [
            str(row.get("parser_fallback_reason", ""))
            for row in parser_observability
            if bool(row.get("parser_fallback")) and str(row.get("parser_fallback_reason", "")).strip()
        ][:20],
        "parser_fallback_stages": [
            str(row.get("parser_fallback_stage", "")).strip() or "unknown"
            for row in parser_observability
            if bool(row.get("parser_fallback"))
        ][:20],
        "marker_tuning": {
            **asdict(marker_tuning_values),
            "effective_source": marker_tuning_source,
            "warnings": marker_tuning_effective.warnings[:20],
        },
        "marker_llm": {
            "use_llm": marker_llm_summary["use_llm"],
            "llm_service": marker_llm_summary["llm_service"],
            "configured": marker_llm_summary["configured"],
            "warnings": marker_llm_summary["warnings"][:20],
        },
        "fallback_reason": fallback_reason,
        "fallback_path": fallback_path,
        **_aggregate_parser_observability(parser_observability),
        "final_decision": "ingestion_completed" if merged_papers else "ingestion_failed",
        "final_answer": (
            f"total papers {len(merged_papers)}, added {import_summary['added']}, skipped {import_summary['skipped']}"
            if merged_papers
            else "no papers were successfully processed"
        ),
    }
    trace_ok, trace_errors = validate_trace_schema(trace)
    save_json(trace, run_dir / "run_trace.json")
    save_json(
        {"trace_validation_ok": trace_ok, "trace_validation_errors": trace_errors},
        run_dir / "run_trace_validation.json",
    )

    if not merged_papers:
        print("No documents were processed successfully.", file=sys.stderr)
        return 1
    if not ok_chunks:
        print("Chunk validation failed. See run report for details.", file=sys.stderr)
        return 1

    print(
        "Processed import candidates "
        f"{len(candidates)} -> added {import_summary['added']} / "
        f"skipped {import_summary['skipped']} / conflicts {import_summary['conflicts']}"
    )
    print(f"Outputs: {chunks_file} and {papers_file}")
    if clean_enabled:
        if clean_success:
            print(f"Clean output: {output_dir / 'chunks_clean.jsonl'}")
        else:
            print("Clean output: failed (see ingest report)")
    print(f"Run logs: {run_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_ingest(args)


if __name__ == "__main__":
    raise SystemExit(main())
