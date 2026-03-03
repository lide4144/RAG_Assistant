from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


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


def fetch_embeddings(
    texts: list[str],
    *,
    base_url: str,
    model: str,
    api_key_env: str,
    timeout_sec: float = 30.0,
) -> list[list[float]]:
    if not texts:
        return []

    api_key = get_api_key(api_key_env)
    url = base_url.rstrip("/") + "/embeddings"
    body = {
        "model": model,
        "input": texts,
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
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
    except error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        trace_id = _read_trace_id(exc.headers)
        recoverable, category = _classify_http_error(int(exc.code), detail)
        raise EmbeddingAPIError(
            f"Embedding API HTTP {exc.code}: {detail}",
            status_code=int(exc.code),
            response_body=detail,
            trace_id=trace_id,
            recoverable=recoverable,
            category=category,
        ) from exc
    except Exception as exc:
        raise EmbeddingAPIError(
            f"Embedding API request failed: {exc}",
            recoverable=True,
            category="network_error",
        ) from exc

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EmbeddingAPIError(
            f"Embedding API returned invalid JSON: {exc}",
            response_body=raw[:1000],
            category="invalid_response",
        ) from exc

    return _extract_embeddings(obj, expected=len(texts))
