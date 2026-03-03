from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


RUN_ID_RE = re.compile(r"`(runs/\d{8}_\d{6}(?:_\d{2})?)`")


def _extract_run_ids(report_path: Path) -> list[str]:
    run_ids: list[str] = []
    in_mapping = False
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("## 运行追溯映射"):
            in_mapping = True
            continue
        if in_mapping and line.strip().startswith("## "):
            break
        if not in_mapping:
            continue
        if "|" not in line:
            continue
        m = RUN_ID_RE.search(line)
        if m:
            run_ids.append(m.group(1))
    return run_ids


def validate_report(report_path: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    if not report_path.exists():
        return [f"report not found: {report_path}"]

    run_ids = _extract_run_ids(report_path)
    if len(run_ids) != 20:
        errors.append(f"expected 20 run mappings, got {len(run_ids)}")
    if len(set(run_ids)) != len(run_ids):
        errors.append("run mappings contain duplicate run_id")

    for i, rid in enumerate(run_ids, start=1):
        run_dir = repo_root / rid
        trace_path = run_dir / "run_trace.json"
        if not run_dir.exists():
            errors.append(f"row {i}: run dir missing: {rid}")
            continue
        if not trace_path.exists():
            errors.append(f"row {i}: run_trace missing: {trace_path}")
            continue
        try:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"row {i}: run_trace invalid json: {trace_path} ({exc})")
            continue
        for key in ("retrieval_top_k", "rerank_top_n"):
            if key not in trace:
                errors.append(f"row {i}: run_trace missing key `{key}`: {trace_path}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate m6 rerank report run mapping.")
    parser.add_argument(
        "--report",
        default="reports/m6_rerank.md",
        help="Path to m6 report markdown file.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(".").resolve()
    report_path = (repo_root / args.report).resolve()
    errors = validate_report(report_path, repo_root)
    if errors:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        return 1
    print(f"[OK] {report_path} mapping is valid (20/20) and run_trace files are readable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
