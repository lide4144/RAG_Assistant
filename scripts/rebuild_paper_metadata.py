from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.models import PageText
from app.parser import choose_best_title


def _load_papers(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("papers.json must be a list")
    return [row for row in payload if isinstance(row, dict)]


def _load_chunks(path: Path) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            paper_id = str(row.get("paper_id", "")).strip()
            if not paper_id:
                continue
            grouped.setdefault(paper_id, []).append(row)
    return grouped


def _build_pages(chunk_rows: list[dict]) -> list[PageText]:
    pages: list[PageText] = []
    for row in chunk_rows:
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        try:
            page_num = int(row.get("page_start", 1))
        except Exception:
            page_num = 1
        pages.append(PageText(page_num=max(1, page_num), text=text))
    pages.sort(key=lambda x: x.page_num)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Incrementally rebuild title/metadata by paper_id")
    parser.add_argument("--papers", default="data/processed/papers.json")
    parser.add_argument("--chunks", default="data/processed/chunks.jsonl")
    parser.add_argument("--paper-id", action="append", required=True, help="paper_id to rebuild (repeatable)")
    parser.add_argument("--title-threshold", type=float, default=0.6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    papers_path = Path(args.papers)
    chunks_path = Path(args.chunks)
    if not papers_path.exists() or not chunks_path.exists():
        raise SystemExit("papers/chunks file not found")

    paper_ids = {str(pid).strip() for pid in args.paper_id if str(pid).strip()}
    papers = _load_papers(papers_path)
    chunks_by_paper = _load_chunks(chunks_path)

    updated = 0
    skipped = 0
    for row in papers:
        paper_id = str(row.get("paper_id", "")).strip()
        if paper_id not in paper_ids:
            continue
        pages = _build_pages(chunks_by_paper.get(paper_id, []))
        if not pages:
            skipped += 1
            continue
        decision = choose_best_title(
            metadata_title=str(row.get("title", "")).strip(),
            pages=pages,
            title_candidates=None,
            confidence_threshold=float(args.title_threshold),
        )
        row["title"] = decision.title
        row["title_source"] = decision.source
        row["title_confidence"] = round(float(decision.confidence), 4)
        row["parser_engine"] = str(row.get("parser_engine", "legacy")).strip() or "legacy"
        updated += 1

    if not args.dry_run:
        papers_path.write_text(json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "updated": updated,
                "skipped": skipped,
                "target_count": len(paper_ids),
                "dry_run": bool(args.dry_run),
                "papers": str(papers_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
