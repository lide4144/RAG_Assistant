#!/usr/bin/env bash
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"
REWRITE_MODEL="${REWRITE_MODEL:-qwen2.5:3b}"

check_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] missing command: $1"
    if [[ "$1" == "ollama" ]]; then
      echo "[INFO] ollama is a system dependency and is not installed via requirements.txt"
      echo "[INFO] install ollama first, then rerun this script"
      echo "[INFO] Linux quick install: curl -fsSL https://ollama.com/install.sh | sh"
      echo "[INFO] After install, verify with: ollama --version"
    fi
    exit 1
  fi
}

ensure_ollama_alive() {
  if curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    echo "[OK] ollama is running at ${OLLAMA_HOST}"
    return
  fi

  echo "[INFO] ollama not running, trying to start 'ollama serve' in background"
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 2
  if ! curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    echo "[ERROR] failed to reach ollama at ${OLLAMA_HOST}. Check /tmp/ollama-serve.log"
    exit 1
  fi
  echo "[OK] ollama started"
}

pull_model() {
  local model="$1"
  echo "[INFO] pulling model: ${model}"
  ollama pull "${model}"
  echo "[OK] pulled model: ${model}"
}

check_cmd curl
check_cmd ollama
ensure_ollama_alive

pull_model "${EMBED_MODEL}"
pull_model "${REWRITE_MODEL}"

echo "[DONE] local models are ready"
echo "- embedding: ${EMBED_MODEL}"
echo "- rewrite: ${REWRITE_MODEL}"
echo "- rerank: not bootstrapped locally by default"
echo "Next: run scripts/check_local_llm_health.sh"
