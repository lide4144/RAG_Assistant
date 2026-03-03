# Multi-Service Local Development

This project now supports a three-service development layout:

- `frontend` (Next.js): chat UI shell
- `gateway` (Node + Express + WebSocket): orchestration entrypoint
- `python-kernel` (FastAPI + SSE): local QA kernel adapter target

## Port convention

- `3000`: frontend (`http://127.0.0.1:3000`)
- `8080`: gateway (`http://127.0.0.1:8080`)
- `8000`: python-kernel-fastapi (`http://127.0.0.1:8000`)

You can override with env vars:

- `FRONTEND_PORT`
- `GATEWAY_HOST`, `GATEWAY_PORT`
- `KERNEL_HOST`, `KERNEL_PORT`
- `WEB_PROVIDER` (`mock` or `duckduckgo`)
- `WEB_PROVIDER_STRICT` (`true` enables strict no-fallback mode)
- `WEB_TOP_K`

Default values:

- `WEB_PROVIDER=mock`
- `WEB_PROVIDER_STRICT=false`

## Install dependencies

```bash
cd frontend && npm install
cd ../gateway && npm install
cd .. && venv/bin/python -m pip install -r requirements.txt
```

## Start all services

From repository root:

```bash
scripts/dev-up.sh
```

## Health checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/health/deps
```

Expected gateway response includes dependency status for `kernel`.
`/health/deps` additionally reports real-web status:

- `kernel_ok`
- `web_provider_ok`
- `provider_used`
- `is_mock_fallback`
- `last_web_provider_error`
- `last_fallback_reason`

## Notes

- `app.kernel_api` executes the existing `app.qa` pipeline and exposes `/qa` + `/qa/stream`.
- `/qa/stream` emits SSE events (`message`, `sources`, `messageEnd`, `error`) for typing-style output.
- Gateway routing:
  - `Local`: consumes Python SSE stream and forwards WS deltas
  - `Web`: uses configurable web provider and unified source contract
  - `Hybrid`: merges local + web sources with stable citation mapping

## Strict web mode

Use this when you need guaranteed real web provider behavior:

```bash
WEB_PROVIDER=duckduckgo WEB_PROVIDER_STRICT=true scripts/dev-up.sh
```

In strict mode, provider failures return errors instead of silently falling back to mock.
