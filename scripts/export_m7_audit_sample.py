from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.qa import _extract_key_claims


def _collect_reports(runs_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    for run_dir in sorted([p for p in runs_dir.glob("*") if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
        report_path = run_dir / "qa_report.json"
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows.append((run_dir, report))
    return rows


def _evidence_lookup(report: dict[str, Any]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for group in report.get("evidence_grouped", []):
        paper_id = group.get("paper_id", "")
        for item in group.get("evidence", []):
            chunk_id = str(item.get("chunk_id", "")).strip()
            if not chunk_id:
                continue
            lookup[chunk_id] = {
                "paper_id": str(item.get("paper_id", paper_id)),
                "section_page": str(item.get("section_page", "")),
                "quote": str(item.get("quote", "")),
            }
    return lookup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export M7 manual audit sample from QA runs.")
    parser.add_argument("--runs-dir", default="runs", help="runs directory")
    parser.add_argument("--sample-size", type=int, default=10, help="number of samples")
    parser.add_argument("--seed", type=int, default=7, help="random seed")
    parser.add_argument("--out", default="reports/m7_audit_sample.json", help="output json path")
    args = parser.parse_args(argv)

    repo_root = Path(".").resolve()
    runs_dir = (repo_root / args.runs_dir).resolve()
    reports = _collect_reports(runs_dir)
    if not reports:
        print(f"[FAIL] no qa_report.json found under {runs_dir}")
        return 1

    with_citations = [(run_dir, report) for run_dir, report in reports if isinstance(report.get("answer_citations"), list)]
    if not with_citations:
        print("[FAIL] no reports with answer_citations")
        return 1

    random.seed(args.seed)
    sample_size = min(max(1, args.sample_size), len(with_citations))
    sampled = random.sample(with_citations, sample_size)

    rows: list[dict[str, Any]] = []
    for run_dir, report in sampled:
        citations = report.get("answer_citations", [])
        lookup = _evidence_lookup(report)
        citation_rows: list[dict[str, str]] = []
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            chunk_id = str(citation.get("chunk_id", "")).strip()
            evidence = lookup.get(chunk_id, {})
            citation_rows.append(
                {
                    "chunk_id": chunk_id,
                    "paper_id": str(citation.get("paper_id", "")),
                    "section_page": str(citation.get("section_page", "")),
                    "quote_snippet": str(evidence.get("quote", ""))[:180],
                }
            )

        rows.append(
            {
                "run_dir": str(run_dir.relative_to(repo_root)),
                "question": report.get("question", ""),
                "answer": report.get("answer", ""),
                "key_claims": _extract_key_claims(str(report.get("answer", ""))),
                "citations": citation_rows,
            }
        )

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"sample_size": sample_size, "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] audit sample exported: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
