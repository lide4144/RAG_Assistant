from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.clean_chunks import run_clean_chunks
from app.chunker import build_chunks
from app.config import load_and_validate_config
from app.fs_utils import FileLockTimeoutError, file_lock
from app.models import ChunkRecord, PageText, PaperRecord
from app.paths import CONFIGS_DIR, RUNS_DIR
from app.paper_summary import build_paper_summaries
from app.parser import (
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


@dataclass
class ImportCandidate:
    paper: PaperRecord
    chunks: list[ChunkRecord]


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


def _paper_from_row(row: dict[str, Any]) -> PaperRecord:
    ingest_metadata_raw = row.get("ingest_metadata")
    ingest_metadata = ingest_metadata_raw if isinstance(ingest_metadata_raw, dict) else None
    return PaperRecord(
        paper_id=str(row.get("paper_id", "")).strip(),
        title=str(row.get("title", "")).strip(),
        path=str(row.get("path", "")).strip(),
        source_type=str(row.get("source_type", "pdf")).strip() or "pdf",
        source_uri=str(row.get("source_uri", row.get("path", ""))).strip(),
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


def run_ingest(args: argparse.Namespace) -> int:
    config, config_warnings = load_and_validate_config(args.config)
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

    for pdf_path in pdf_paths:
        stable_paper_id, fingerprint = stable_pdf_paper_id(pdf_path)
        legacy_paper_id = make_paper_id(pdf_path)
        try:
            pages, page_errors, metadata_title = parse_pdf_pages(pdf_path)
        except Exception as exc:
            paper_failures.append(f"{pdf_path.name}: {exc}")
            continue

        parse_errors.extend(page_errors)
        if not pages:
            paper_failures.append(f"{pdf_path.name}: no readable pages")
            continue

        title = extract_title(metadata_title, pages)
        chunks = build_chunks(
            paper_id=stable_paper_id,
            pages=pages,
            chunk_size=config.chunk_size,
            overlap=config.overlap,
        )
        if not chunks:
            paper_failures.append(f"{pdf_path.name}: no chunks generated")
            continue

        source_uri = f"pdf://sha1/{fingerprint}"
        candidates.append(
            ImportCandidate(
                paper=PaperRecord(
                    paper_id=stable_paper_id,
                    title=title,
                    path=str(pdf_path),
                    source_type="pdf",
                    source_uri=source_uri,
                    imported_at=now_iso,
                    status="active",
                    fingerprint=fingerprint,
                    ingest_metadata={
                        "file_name": pdf_path.name,
                        "legacy_paper_id": legacy_paper_id,
                        "legacy_source_path": str(pdf_path.resolve()),
                    },
                ),
                chunks=chunks,
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
                    imported_at=now_iso,
                    status="active",
                    fingerprint=content_fingerprint,
                    ingest_metadata=url_meta_json(
                        fetched_at=fetched.fetched_at,
                        http_status=fetched.http_status,
                    ),
                ),
                chunks=chunks,
            )
        )

    chunks_file = output_dir / "chunks.jsonl"
    papers_file = output_dir / "papers.json"
    paper_summary_file = output_dir / "paper_summary.json"
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
    }

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
            "top_k_retrieval": config.top_k_retrieval,
            "alpha_expansion": config.alpha_expansion,
            "top_n_evidence": config.top_n_evidence,
            "fusion_weight": config.fusion_weight,
            "RRF_k": config.RRF_k,
            "sufficiency_threshold": config.sufficiency_threshold,
            "table_list_downweight": config.table_list_downweight,
        },
        "chunk_validation_ok": ok_chunks,
        "chunk_validation_errors": chunk_errors,
        "clean_enabled": clean_enabled,
        "clean_output": clean_output,
        "clean_success": clean_success,
        "clean_error": clean_error,
        "import_summary": import_summary,
        "import_outcomes": outcomes,
    }
    save_json(report, run_dir / "ingest_report.json")

    trace = {
        "input_question": args.question,
        "rewrite_query": None,
        "retrieval_top_k": [],
        "expansion_added_chunks": [],
        "rerank_top_n": [],
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
