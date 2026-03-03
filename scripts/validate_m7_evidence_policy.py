from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_questions(path: Path) -> list[str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _latest_new_run_dir(runs_dir: Path, before: set[str]) -> Path | None:
    candidates = [p for p in runs_dir.glob("*") if p.is_dir() and p.name not in before]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _validate_citations(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    citations = report.get("answer_citations")
    if not isinstance(citations, list) or not citations:
        return ["answer_citations missing or empty"]
    for idx, item in enumerate(citations):
        if not isinstance(item, dict):
            errors.append(f"citation[{idx}] not object")
            continue
        chunk_id = str(item.get("chunk_id", "")).strip()
        section_page = str(item.get("section_page", "")).strip()
        if not chunk_id:
            errors.append(f"citation[{idx}] missing chunk_id")
        if not section_page:
            errors.append(f"citation[{idx}] missing section_page")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run M7 citation regression on 30 questions.")
    parser.add_argument("--questions", default="reports/m7_questions_30.txt", help="Questions file (one question per line)")
    parser.add_argument("--python", default=sys.executable, help="Python executable path")
    parser.add_argument("--mode", default="hybrid", choices=["bm25", "dense", "hybrid"], help="QA mode")
    parser.add_argument("--config", default="configs/m7_regression.yaml", help="QA config path")
    parser.add_argument("--chunks", default="data/processed/chunks_clean.jsonl", help="chunks_clean.jsonl path")
    parser.add_argument("--bm25-index", default="data/indexes/bm25_index.json", help="bm25 index path")
    parser.add_argument("--vec-index", default="data/indexes/vec_index.json", help="vec index path")
    parser.add_argument("--embed-index", default="data/indexes/vec_index_embed.json", help="embedding index path")
    parser.add_argument("--runs-dir", default="runs", help="runs directory")
    parser.add_argument("--out", default="reports/m7_regression_result.json", help="output summary json")
    args = parser.parse_args(argv)

    repo_root = Path(".").resolve()
    questions_path = (repo_root / args.questions).resolve()
    runs_dir = (repo_root / args.runs_dir).resolve()

    if not questions_path.exists():
        print(f"[FAIL] questions file not found: {questions_path}", file=sys.stderr)
        return 1
    if not runs_dir.exists():
        runs_dir.mkdir(parents=True, exist_ok=True)

    questions = _load_questions(questions_path)
    if len(questions) != 30:
        print(f"[FAIL] expected 30 questions, got {len(questions)}", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    for idx, question in enumerate(questions, start=1):
        before = {p.name for p in runs_dir.glob("*") if p.is_dir()}
        cmd = [
            args.python,
            "-m",
            "app.qa",
            "--q",
            question,
            "--mode",
            args.mode,
            "--config",
            args.config,
            "--chunks",
            args.chunks,
            "--bm25-index",
            args.bm25_index,
            "--vec-index",
            args.vec_index,
            "--embed-index",
            args.embed_index,
        ]
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
        row: dict[str, Any] = {
            "index": idx,
            "question": question,
            "returncode": proc.returncode,
            "errors": [],
        }
        if proc.returncode != 0:
            row["errors"].append("qa command failed")
            row["stderr_tail"] = "\n".join(proc.stderr.splitlines()[-10:])
            results.append(row)
            continue

        run_dir = _latest_new_run_dir(runs_dir, before)
        if run_dir is None:
            row["errors"].append("no new run dir created")
            results.append(row)
            continue

        report_path = run_dir / "qa_report.json"
        if not report_path.exists():
            row["errors"].append("qa_report.json missing")
            results.append(row)
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))
        row["run_dir"] = str(run_dir.relative_to(repo_root))
        row["errors"].extend(_validate_citations(report))
        results.append(row)

    passed = sum(1 for r in results if not r["errors"])
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }

    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if passed != len(results):
        print(f"[FAIL] M7 regression failed: {passed}/{len(results)} passed. details: {out_path}", file=sys.stderr)
        return 1

    print(f"[OK] M7 regression passed: {passed}/{len(results)} with citations. details: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
