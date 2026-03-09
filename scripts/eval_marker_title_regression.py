from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

BLACKLIST = [
    re.compile(r"^\s*preprint\.?\s+under\s+review\.?\s*$", re.IGNORECASE),
    re.compile(r"all rights reserved", re.IGNORECASE),
    re.compile(r"copyright", re.IGNORECASE),
]


def _is_blacklisted(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    return any(p.search(text) for p in BLACKLIST)


def _load_papers(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def _blacklisted_titles(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        paper_id = str(row.get("paper_id", "")).strip()
        title = str(row.get("title", "")).strip()
        if paper_id and _is_blacklisted(title):
            out.add(paper_id)
    return out


def _load_json_if_exists(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate title-fix rate and retrieval/answer regression summary")
    parser.add_argument("--before-papers", required=True)
    parser.add_argument("--after-papers", required=True)
    parser.add_argument("--before-qa-report", default="")
    parser.add_argument("--after-qa-report", default="")
    parser.add_argument("--out", default="reports/marker_title_regression.json")
    args = parser.parse_args()

    before_rows = _load_papers(Path(args.before_papers))
    after_rows = _load_papers(Path(args.after_papers))
    before_bad = _blacklisted_titles(before_rows)
    after_bad = _blacklisted_titles(after_rows)

    fixed = sorted(before_bad - after_bad)
    remaining = sorted(after_bad)
    before_count = len(before_bad)
    fixed_count = len(fixed)
    fix_rate = (fixed_count / before_count) if before_count else 1.0

    before_qa = _load_json_if_exists(Path(args.before_qa_report) if args.before_qa_report else None)
    after_qa = _load_json_if_exists(Path(args.after_qa_report) if args.after_qa_report else None)

    summary = {
        "before_blacklisted_titles": before_count,
        "after_blacklisted_titles": len(after_bad),
        "fixed_count": fixed_count,
        "fix_rate": round(fix_rate, 4),
        "remaining_blacklisted_paper_ids": remaining[:100],
        "fixed_paper_ids": fixed[:100],
        "retrieval_regression": {
            "before": before_qa,
            "after": after_qa,
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
