from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.admin_llm_config import mask_api_key
from app.llm_log_config import resolve_effective_llm_log_config


_LOGGER_NAME = "rag_gpt.llm_api"
_SECRET_KEY_HINTS = ("api_key", "apikey", "authorization", "token", "secret", "password")
_LOGGER_INITIALIZED = False
_LOGGER_FILE_PATH: str | None = None


def _mask_secret_text(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("bearer "):
        token = raw[7:].strip()
        return f"Bearer {mask_api_key(token)}"
    return mask_api_key(raw)


def sanitize_llm_debug_value(value: Any) -> Any:
    if isinstance(value, str):
        parsed = _parse_json_text(value)
        if parsed is not None:
            return sanitize_llm_debug_value(parsed)
        return value
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key or "").strip().lower()
            if any(hint in lowered for hint in _SECRET_KEY_HINTS):
                sanitized[str(key)] = _mask_secret_text(str(item or ""))
            else:
                sanitized[str(key)] = sanitize_llm_debug_value(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_llm_debug_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_llm_debug_value(item) for item in value]
    return value


def _parse_json_text(value: str) -> Any | None:
    text = str(value or "").strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def dump_llm_debug_text(value: Any) -> str | None:
    if value is None:
        return None
    sanitized = sanitize_llm_debug_value(value)
    if isinstance(sanitized, str):
        return sanitized
    try:
        return json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        return str(sanitized)


def truncate_llm_debug_text(text: str | None) -> str | None:
    if text is None:
        return None
    max_chars = resolve_effective_llm_log_config().max_body_chars
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n... [truncated {omitted} chars]"


def format_llm_debug_text(value: Any) -> str | None:
    return truncate_llm_debug_text(dump_llm_debug_text(value))


def _event_log_level(event_name: str) -> int:
    if event_name == "request_failure":
        return logging.WARNING
    return logging.INFO


def _stringify_meta(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def render_llm_debug_event(event: dict[str, Any]) -> str:
    payload = {
        key: sanitize_llm_debug_value(value)
        for key, value in event.items()
        if value is not None
    }
    for text_key in ("request_payload", "response_payload", "system_prompt", "user_prompt", "response_text"):
        if text_key in payload:
            payload[text_key] = truncate_llm_debug_text(str(payload[text_key]))

    title = f"[LLM API] event={payload.get('event', '-')} stage={payload.get('debug_stage') or payload.get('stage') or '-'}"
    meta_keys = (
        "timestamp",
        "trace_id",
        "provider",
        "model",
        "api_base",
        "endpoint",
        "transport",
        "route_id",
        "attempts_used",
        "elapsed_ms",
        "status_code",
        "reason",
        "error_category",
        "fallback_reason",
        "first_token_latency_ms",
        "chunks_received",
    )
    lines = ["=" * 88, title]
    for key in meta_keys:
        text = _stringify_meta(payload, key)
        if text is not None:
            lines.append(f"{key}: {text}")
    for block_key, label in (
        ("system_prompt", "system_prompt"),
        ("user_prompt", "user_prompt"),
        ("request_payload", "request_payload"),
        ("response_payload", "response_payload"),
        ("response_text", "response_text"),
    ):
        text = _stringify_meta(payload, block_key)
        if text is not None:
            lines.append(f"{label}:")
            lines.append(text)
    lines.append("=" * 88)
    return "\n".join(lines)


def _configure_logger() -> logging.Logger:
    global _LOGGER_INITIALIZED, _LOGGER_FILE_PATH
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not _LOGGER_INITIALIZED:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(stream_handler)
        _LOGGER_INITIALIZED = True

    requested_path = resolve_effective_llm_log_config().log_path
    if requested_path and requested_path != _LOGGER_FILE_PATH:
        target = Path(requested_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)
        _LOGGER_FILE_PATH = requested_path
    return logger


def log_llm_debug_event(event: dict[str, Any]) -> None:
    if not resolve_effective_llm_log_config().enabled:
        return
    logger = _configure_logger()
    rendered = render_llm_debug_event(event)
    logger.log(_event_log_level(str(event.get("event") or "")), rendered)
