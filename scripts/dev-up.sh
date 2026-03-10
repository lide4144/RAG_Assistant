#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

KERNEL_HOST="${KERNEL_HOST:-127.0.0.1}"
KERNEL_PORT="${KERNEL_PORT:-8000}"
GATEWAY_HOST="${GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

KERNEL_INTERNAL_BASE_URL="${KERNEL_BASE_URL:-}"
if [[ -z "$KERNEL_INTERNAL_BASE_URL" ]]; then
  if [[ "$KERNEL_HOST" == "0.0.0.0" ]]; then
    KERNEL_INTERNAL_BASE_URL="http://127.0.0.1:$KERNEL_PORT"
  else
    KERNEL_INTERNAL_BASE_URL="http://$KERNEL_HOST:$KERNEL_PORT"
  fi
fi

FRONTEND_KERNEL_BASE_URL="${NEXT_PUBLIC_KERNEL_BASE_URL:-}"
if [[ -z "$FRONTEND_KERNEL_BASE_URL" && "$KERNEL_HOST" != "0.0.0.0" ]]; then
  FRONTEND_KERNEL_BASE_URL="http://$KERNEL_HOST:$KERNEL_PORT"
fi

FRONTEND_GATEWAY_WS_URL="${NEXT_PUBLIC_GATEWAY_WS_URL:-}"

KERNEL_CMD=(venv/bin/python -m uvicorn app.kernel_api:app --host "$KERNEL_HOST" --port "$KERNEL_PORT")
GATEWAY_CMD=(npm run dev)
FRONTEND_CMD=(npm run dev)

cd "$ROOT_DIR"

if [[ ! -x "venv/bin/python" ]]; then
  echo "Missing Python virtualenv at venv/bin/python"
  exit 1
fi

if [[ ! -f "gateway/package.json" || ! -f "frontend/package.json" ]]; then
  echo "Missing gateway/frontend package.json"
  exit 1
fi

cleanup() {
  if [[ -n "${KERNEL_PID:-}" ]]; then kill "$KERNEL_PID" 2>/dev/null || true; fi
  if [[ -n "${GATEWAY_PID:-}" ]]; then kill "$GATEWAY_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

"${KERNEL_CMD[@]}" &
KERNEL_PID=$!

echo "python-kernel-fastapi pid=$KERNEL_PID url=http://$KERNEL_HOST:$KERNEL_PORT"

(
  cd "$ROOT_DIR/gateway"
  GATEWAY_HOST="$GATEWAY_HOST" GATEWAY_PORT="$GATEWAY_PORT" KERNEL_BASE_URL="$KERNEL_INTERNAL_BASE_URL" "${GATEWAY_CMD[@]}"
) &
GATEWAY_PID=$!

echo "gateway pid=$GATEWAY_PID url=http://$GATEWAY_HOST:$GATEWAY_PORT"

(
  cd "$ROOT_DIR/frontend"
  PORT="$FRONTEND_PORT" NEXT_PUBLIC_KERNEL_BASE_URL="$FRONTEND_KERNEL_BASE_URL" NEXT_PUBLIC_GATEWAY_WS_URL="$FRONTEND_GATEWAY_WS_URL" "${FRONTEND_CMD[@]}"
) &
FRONTEND_PID=$!

echo "frontend pid=$FRONTEND_PID url=http://127.0.0.1:$FRONTEND_PORT"

echo "all services started; press Ctrl+C to stop"
wait
