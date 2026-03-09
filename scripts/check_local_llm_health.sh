#!/usr/bin/env bash
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
KERNEL_BASE_URL="${KERNEL_BASE_URL:-http://127.0.0.1:8000}"
EMBED_MODEL="${EMBED_MODEL:-BAAI/bge-small-zh-v1.5}"
RERANK_MODEL="${RERANK_MODEL:-BAAI/bge-reranker-base}"
REWRITE_MODEL="${REWRITE_MODEL:-Qwen2.5-3B-Instruct}"

check_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] missing command: $1"
    exit 1
  fi
}

check_cmd curl
check_cmd python3

models_json="$(curl -fsS "${OLLAMA_HOST}/api/tags")"
python3 - <<'PY' "${models_json}" "${EMBED_MODEL}" "${RERANK_MODEL}" "${REWRITE_MODEL}"
import json
import sys

payload = json.loads(sys.argv[1])
required = sys.argv[2:]
rows = payload.get("models", []) if isinstance(payload, dict) else []
installed = {str(item.get("name", "")).split(":", 1)[0] for item in rows if isinstance(item, dict)}
missing = [m for m in required if m not in installed]
if missing:
    print("[ERROR] missing local models:", ", ".join(missing))
    sys.exit(1)
print("[OK] local model registry contains required models")
PY

echo "[INFO] checking kernel deps"
curl -fsS "${KERNEL_BASE_URL}/health/deps" | python3 -m json.tool >/tmp/kernel_deps_health.json
cat /tmp/kernel_deps_health.json

echo "[INFO] probing rewrite route with local model"
rewrite_resp="$(
  curl -fsS \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${REWRITE_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"health check: reply ok\"}],\"temperature\":0,\"max_tokens\":8}" \
    "${OLLAMA_HOST}/v1/chat/completions"
)"
python3 - <<'PY' "${rewrite_resp}"
import json
import sys

payload = json.loads(sys.argv[1])
choices = payload.get("choices", []) if isinstance(payload, dict) else []
first = choices[0] if isinstance(choices, list) and choices else {}
message = first.get("message", {}) if isinstance(first, dict) else {}
content = message.get("content") if isinstance(message, dict) else None
if not isinstance(content, str) or not content.strip():
    print("[ERROR] rewrite probe failed: empty completion content")
    sys.exit(1)
print("[OK] rewrite route probe succeeded")
PY

echo "[DONE] health check passed"
echo "Diagnostics when failed:"
echo "1) check ollama logs: tail -n 200 /tmp/ollama-serve.log"
echo "2) check kernel health: curl -sS ${KERNEL_BASE_URL}/health"
echo "3) check runtime config: cat configs/llm_runtime_config.json"
