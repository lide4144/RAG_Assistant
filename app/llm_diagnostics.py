from __future__ import annotations

from typing import Any


def build_llm_diagnostics(
    *,
    stage: str,
    provider: str,
    model: str,
    reason: str,
    fallback_warning: str,
    status_code: int | None = None,
    attempts_used: int = 0,
    max_retries: int = 0,
    elapsed_ms: int = 0,
    timestamp: str | None = None,
    provider_used: str | None = None,
    model_used: str | None = None,
    fallback_reason: str | None = None,
    error_category: str | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "provider": provider,
        "model": model,
        "reason": reason,
        "status_code": status_code,
        "attempts_used": int(max(0, attempts_used)),
        "max_retries": int(max(0, max_retries)),
        "elapsed_ms": int(max(0, elapsed_ms)),
        "fallback_warning": fallback_warning,
        "timestamp": timestamp,
        "provider_used": provider_used,
        "model_used": model_used,
        "fallback_reason": fallback_reason,
        "error_category": error_category,
    }
