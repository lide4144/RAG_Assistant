#!/usr/bin/env bash
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
EMBED_MODEL="${EMBED_MODEL:-BAAI/bge-small-zh-v1.5}"
RERANK_MODEL="${RERANK_MODEL:-BAAI/bge-reranker-base}"
REWRITE_MODEL="${REWRITE_MODEL:-Qwen2.5-3B-Instruct}"

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
pull_model "${RERANK_MODEL}"
pull_model "${REWRITE_MODEL}"

echo "[DONE] local models are ready"
echo "- embedding: ${EMBED_MODEL}"
echo "- rerank: ${RERANK_MODEL}"
echo "- rewrite: ${REWRITE_MODEL}"
echo "Next: run scripts/check_local_llm_health.sh"
