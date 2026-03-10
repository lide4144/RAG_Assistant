#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PORT="${APP_PORT:-9000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
KERNEL_PORT="${KERNEL_PORT:-8000}"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"
NGINX_RUNTIME_DIR="${NGINX_RUNTIME_DIR:-$ROOT_DIR/.runtime/cloudstudio-nginx}"
NGINX_CONF="$NGINX_RUNTIME_DIR/nginx.conf"

cd "$ROOT_DIR"

if ! command -v nginx >/dev/null 2>&1; then
  echo "Missing nginx in PATH. Install nginx first, then rerun scripts/cloudstudio-up.sh."
  echo "Cloud Studio recommended flow: expose APP_PORT=$APP_PORT as the only public app port."
  exit 1
fi

mkdir -p "$NGINX_RUNTIME_DIR"

python3 - <<'PY' "$ROOT_DIR/deploy/nginx/cloudstudio-http.conf.template" "$NGINX_CONF" "$NGINX_RUNTIME_DIR" "$APP_PORT" "$FRONTEND_PORT" "$KERNEL_PORT" "$GATEWAY_PORT"
from pathlib import Path
import sys

template_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
runtime_dir = sys.argv[3]
app_port = sys.argv[4]
frontend_port = sys.argv[5]
kernel_port = sys.argv[6]
gateway_port = sys.argv[7]

content = template_path.read_text()
for key, value in {
    "__RUNTIME_DIR__": runtime_dir,
    "__APP_PORT__": app_port,
    "__FRONTEND_PORT__": frontend_port,
    "__KERNEL_PORT__": kernel_port,
    "__GATEWAY_PORT__": gateway_port,
}.items():
    content = content.replace(key, value)
output_path.write_text(content)
PY

cleanup() {
  if [[ -n "${NGINX_PID:-}" ]]; then kill "$NGINX_PID" 2>/dev/null || true; fi
  if [[ -n "${DEV_UP_PID:-}" ]]; then kill "$DEV_UP_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

env -u NEXT_PUBLIC_KERNEL_BASE_URL -u NEXT_PUBLIC_GATEWAY_WS_URL \
  KERNEL_HOST=127.0.0.1 \
  GATEWAY_HOST=127.0.0.1 \
  KERNEL_PORT="$KERNEL_PORT" \
  GATEWAY_PORT="$GATEWAY_PORT" \
  FRONTEND_PORT="$FRONTEND_PORT" \
  "$ROOT_DIR/scripts/dev-up.sh" &
DEV_UP_PID=$!

echo "cloudstudio internal services pid=$DEV_UP_PID"
echo "cloudstudio public app target=http://127.0.0.1:$APP_PORT"

nginx -p "$NGINX_RUNTIME_DIR" -c "$NGINX_CONF" -g 'daemon off;' &
NGINX_PID=$!

echo "cloudstudio nginx pid=$NGINX_PID conf=$NGINX_CONF"
echo "expose APP_PORT=$APP_PORT as the only public Cloud Studio application port"

wait
