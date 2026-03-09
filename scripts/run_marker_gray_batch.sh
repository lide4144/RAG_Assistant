#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${1:-configs/default.yaml}"
INPUT_DIR="${2:-data/samples/gray_batch}"
OUTPUT_DIR="${3:-data/processed/gray_batch}"
RUN_DIR="${4:-runs/marker_gray_batch}"

echo "[gray] validate marker switches"
venv/bin/python scripts/validate_marker_gray_release.py --config "$CONFIG_PATH"

echo "[gray] run ingest batch"
venv/bin/python -m app.ingest --input "$INPUT_DIR" --out "$OUTPUT_DIR" --config "$CONFIG_PATH" --run-dir "$RUN_DIR"

echo "[gray] validate report"
venv/bin/python scripts/validate_marker_gray_release.py --config "$CONFIG_PATH" --ingest-report "$RUN_DIR/ingest_report.json"

echo "[gray] done. rollback by setting marker_enabled=false in $CONFIG_PATH"
