from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any
from urllib import error, request

from app.llm_client import emit_llm_debug_event
from app.llm_observability import format_llm_debug_text


class EmbeddingAPIError(RuntimeError):
    """Raised when embedding API request fails or returns invalid payload."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
        trace_id: str | None = None,
        recoverable: bool = False,
        category: str = "unknown",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.trace_id = trace_id
        self.recoverable = recoverable
        self.category = category

    def __str__(self) -> str:
        return self.message


def get_api_key(api_key_env: str) -> str:
    key = os.getenv(api_key_env, "").strip()
    if not key:
        raise EmbeddingAPIError(f"Missing API key in env var: {api_key_env}")
    return key


def _extract_embeddings(payload: dict[str, Any], expected: int) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise EmbeddingAPIError("Embedding response missing data list")

    vectors: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict):
            raise EmbeddingAPIError("Embedding response item must be object")
        emb = item.get("embedding")
        if not isinstance(emb, list):
            raise EmbeddingAPIError("Embedding item missing embedding list")
        try:
            vectors.append([float(x) for x in emb])
        except (TypeError, ValueError) as exc:
            raise EmbeddingAPIError(f"Embedding contains non-numeric value: {exc}") from exc

    if len(vectors) != expected:
        raise EmbeddingAPIError(
            f"Embedding response size mismatch: expected {expected}, got {len(vectors)}",
            category="invalid_response",
        )
    return vectors


def _read_trace_id(headers: Any) -> str | None:
    if headers is None:
        return None
    for key in ("x-siliconcloud-trace-id", "x-trace-id", "trace-id"):
        value = headers.get(key)
        if value:
            return str(value)
    return None


def _classify_http_error(status_code: int, detail: str) -> tuple[bool, str]:
    if status_code in {401, 403}:
        return False, "auth_failed"
    if status_code == 429:
        return True, "rate_limit"
    if 500 <= status_code <= 599:
        return True, "server_error"
    lowered = (detail or "").lower()
    if any(k in lowered for k in ("empty", "blank", "must not be empty")):
        return False, "input_empty"
    if any(k in lowered for k in ("token", "max length", "too long", "context length")):
        return False, "input_over_limit"
    if any(k in lowered for k in ("invalid", "format", "malformed")):
        return False, "input_format"
    return False, "http_error"


def _embedding_response_summary(vectors: list[list[float]]) -> dict[str, int]:
    if not vectors:
        return {"embedding_count": 0, "embedding_dim": 0}
    return {
        "embedding_count": len(vectors),
        "embedding_dim": len(vectors[0]),
    }


def fetch_embeddings(
    texts: list[str],
    *,
    base_url: str,
    model: str,
    api_key_env: str,
    provider: str | None = None,
    timeout_sec: float = 30.0,
) -> list[list[float]]:
    if not texts:
        return []

    debug_provider = str(provider or "").strip() or "embedding"
    request_payload = format_llm_debug_text(
        {
            "model": model,
            "input": texts,
        }
    )
    endpoint = base_url.rstrip("/") + "/embeddings"
    started_at = perf_counter()
    api_key = get_api_key(api_key_env)
    body = {
        "model": model,
        "input": texts,
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            trace_id = _read_trace_id(getattr(resp, "headers", None))
    except error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        trace_id = _read_trace_id(exc.headers)
        recoverable, category = _classify_http_error(int(exc.code), detail)
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "embedding",
                "debug_stage": "embedding",
                "provider": debug_provider,
                "model": model,
                "api_base": base_url,
                "endpoint": endpoint,
                "transport": "urllib",
                "status_code": int(exc.code),
                "reason": category,
                "error_category": category,
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(detail),
            }
        )
        raise EmbeddingAPIError(
            f"Embedding API HTTP {exc.code}: {detail}",
            status_code=int(exc.code),
            response_body=detail,
            trace_id=trace_id,
            recoverable=recoverable,
            category=category,
        ) from exc
    except Exception as exc:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "embedding",
                "debug_stage": "embedding",
                "provider": debug_provider,
                "model": model,
                "api_base": base_url,
                "endpoint": endpoint,
                "transport": "urllib",
                "reason": "network_error",
                "error_category": "network_error",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(str(exc)),
            }
        )
        raise EmbeddingAPIError(
            f"Embedding API request failed: {exc}",
            recoverable=True,
            category="network_error",
        ) from exc

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "embedding",
                "debug_stage": "embedding",
                "provider": debug_provider,
                "model": model,
                "api_base": base_url,
                "endpoint": endpoint,
                "transport": "urllib",
                "reason": "invalid_response",
                "error_category": "invalid_response",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(raw),
            }
        )
        raise EmbeddingAPIError(
            f"Embedding API returned invalid JSON: {exc}",
            response_body=raw[:1000],
            category="invalid_response",
        ) from exc

    try:
        vectors = _extract_embeddings(obj, expected=len(texts))
    except EmbeddingAPIError as exc:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "embedding",
                "debug_stage": "embedding",
                "provider": debug_provider,
                "model": model,
                "api_base": base_url,
                "endpoint": endpoint,
                "transport": "urllib",
                "status_code": 200,
                "reason": exc.category,
                "error_category": exc.category,
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(obj),
            }
        )
        raise

    emit_llm_debug_event(
        {
            "event": "request_success",
            "stage": "embedding",
            "debug_stage": "embedding",
            "provider": debug_provider,
            "model": model,
            "api_base": base_url,
            "endpoint": endpoint,
            "transport": "urllib",
            "status_code": 200,
            "elapsed_ms": int((perf_counter() - started_at) * 1000),
            "trace_id": trace_id,
            "request_payload": request_payload,
            "response_payload": format_llm_debug_text(obj),
            "response_text": format_llm_debug_text(_embedding_response_summary(vectors)),
        }
    )
    return vectors
