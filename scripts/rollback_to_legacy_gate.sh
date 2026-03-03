#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CFG="${ROOT_DIR}/configs/default.yaml"
LEGACY_CFG="${ROOT_DIR}/configs/paper_assistant_growth_legacy.yaml"
BACKUP_CFG="${ROOT_DIR}/configs/default.yaml.bak.$(date +%Y%m%d%H%M%S)"

if [[ ! -f "${LEGACY_CFG}" ]]; then
  echo "[FAIL] missing legacy config: ${LEGACY_CFG}" >&2
  exit 1
fi

cp "${DEFAULT_CFG}" "${BACKUP_CFG}"
cp "${LEGACY_CFG}" "${DEFAULT_CFG}"
echo "[OK] rolled back to legacy gate config."
echo "backup saved at: ${BACKUP_CFG}"
