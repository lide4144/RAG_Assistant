#!/usr/bin/env bash
set -euo pipefail

: "${ANSWER_API_BASE:?set ANSWER_API_BASE}"
: "${ANSWER_API_KEY:?set ANSWER_API_KEY}"
: "${ANSWER_MODEL:?set ANSWER_MODEL}"

EMBED_PROVIDER="${EMBED_PROVIDER:-openai}"
EMBED_API_BASE="${EMBED_API_BASE:-${ANSWER_API_BASE}}"
EMBED_API_KEY="${EMBED_API_KEY:-${ANSWER_API_KEY}}"
EMBED_MODEL="${EMBED_MODEL:-${ANSWER_MODEL}}"

RERANK_PROVIDER="${RERANK_PROVIDER:-openai}"
RERANK_API_BASE="${RERANK_API_BASE:-${ANSWER_API_BASE}}"
RERANK_API_KEY="${RERANK_API_KEY:-${ANSWER_API_KEY}}"
RERANK_MODEL="${RERANK_MODEL:-${ANSWER_MODEL}}"

REWRITE_PROVIDER="${REWRITE_PROVIDER:-openai}"
REWRITE_API_BASE="${REWRITE_API_BASE:-${ANSWER_API_BASE}}"
REWRITE_API_KEY="${REWRITE_API_KEY:-${ANSWER_API_KEY}}"
REWRITE_MODEL="${REWRITE_MODEL:-${ANSWER_MODEL}}"

GRAPH_ENTITY_PROVIDER="${GRAPH_ENTITY_PROVIDER:-openai}"
GRAPH_ENTITY_API_BASE="${GRAPH_ENTITY_API_BASE:-${ANSWER_API_BASE}}"
GRAPH_ENTITY_API_KEY="${GRAPH_ENTITY_API_KEY:-${ANSWER_API_KEY}}"
GRAPH_ENTITY_MODEL="${GRAPH_ENTITY_MODEL:-${ANSWER_MODEL}}"

export ANSWER_API_BASE ANSWER_API_KEY ANSWER_MODEL
export EMBED_PROVIDER EMBED_API_BASE EMBED_API_KEY EMBED_MODEL
export RERANK_PROVIDER RERANK_API_BASE RERANK_API_KEY RERANK_MODEL
export REWRITE_PROVIDER REWRITE_API_BASE REWRITE_API_KEY REWRITE_MODEL
export GRAPH_ENTITY_PROVIDER GRAPH_ENTITY_API_BASE GRAPH_ENTITY_API_KEY GRAPH_ENTITY_MODEL

python3 - <<'PY'
import json
import os
from pathlib import Path

payload = {
    "answer": {
        "provider": "openai",
        "api_base": os.environ["ANSWER_API_BASE"],
        "api_key": os.environ["ANSWER_API_KEY"],
        "model": os.environ["ANSWER_MODEL"],
    },
    "embedding": {
        "provider": os.environ["EMBED_PROVIDER"],
        "api_base": os.environ["EMBED_API_BASE"],
        "api_key": os.environ["EMBED_API_KEY"],
        "model": os.environ["EMBED_MODEL"],
    },
    "rerank": {
        "provider": os.environ["RERANK_PROVIDER"],
        "api_base": os.environ["RERANK_API_BASE"],
        "api_key": os.environ["RERANK_API_KEY"],
        "model": os.environ["RERANK_MODEL"],
    },
    "rewrite": {
        "provider": os.environ["REWRITE_PROVIDER"],
        "api_base": os.environ["REWRITE_API_BASE"],
        "api_key": os.environ["REWRITE_API_KEY"],
        "model": os.environ["REWRITE_MODEL"],
    },
    "graph_entity": {
        "provider": os.environ["GRAPH_ENTITY_PROVIDER"],
        "api_base": os.environ["GRAPH_ENTITY_API_BASE"],
        "api_key": os.environ["GRAPH_ENTITY_API_KEY"],
        "model": os.environ["GRAPH_ENTITY_MODEL"],
    },
}
path = Path("configs/llm_runtime_config.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[DONE] wrote {path}")
PY

echo "Next: restart kernel and verify /health/deps"
