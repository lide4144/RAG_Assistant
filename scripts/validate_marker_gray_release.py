from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate marker gray-release switches")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--ingest-report", default="")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}

    checks: list[str] = []
    failures: list[str] = []

    marker_enabled = bool(cfg.get("marker_enabled", True))
    marker_timeout = float(cfg.get("marker_timeout_sec", 0) or 0)
    threshold = float(cfg.get("title_confidence_threshold", -1) or -1)

    if marker_timeout <= 0:
        failures.append(f"marker_timeout_sec must be > 0, got {marker_timeout}")
    else:
        checks.append(f"marker_timeout_sec={marker_timeout}")

    if threshold < 0 or threshold > 1:
        failures.append(f"title_confidence_threshold must be in [0,1], got {threshold}")
    else:
        checks.append(f"title_confidence_threshold={threshold}")

    checks.append(f"marker_enabled={marker_enabled}")
    checks.append("rollback_ready=true (set marker_enabled=false to force legacy parser)")

    if args.ingest_report:
        report_path = Path(args.ingest_report)
        if report_path.exists():
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            parser_rows = payload.get("parser_observability", []) if isinstance(payload, dict) else []
            fallback_count = 0
            marker_count = 0
            for row in parser_rows:
                if not isinstance(row, dict):
                    continue
                if bool(row.get("parser_fallback")):
                    fallback_count += 1
                if str(row.get("parser_engine", "")) == "marker":
                    marker_count += 1
            checks.append(f"parser_observability.marker_count={marker_count}")
            checks.append(f"parser_observability.fallback_count={fallback_count}")

    if failures:
        print("MARKER_GRAY_RELEASE: FAIL")
        for row in failures:
            print(f"- {row}")
        return 1

    print("MARKER_GRAY_RELEASE: PASS")
    for row in checks:
        print(f"- {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
