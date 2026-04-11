from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from app.paths import RUNS_DIR


DEFAULT_LLM_LOG_MAX_BODY_CHARS = 50000
MIN_LLM_LOG_MAX_BODY_CHARS = 1024
LLM_LOG_SAFE_ROOT = RUNS_DIR / "logs" / "llm_api"


@dataclass(frozen=True)
class EffectiveLlmLogConfig:
    enabled: bool
    max_body_chars: int
    safe_root: str
    log_path: str
    source: dict[str, str]
    warnings: list[str]


def _local_now() -> datetime:
    return datetime.now().astimezone()


_LOG_SESSION_STAMP = _local_now().strftime("%Y%m%d-%H%M%S")
_LOG_SESSION_SUFFIX = uuid4().hex[:8]


def _parse_positive_int(value: object, *, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed < MIN_LLM_LOG_MAX_BODY_CHARS:
        raise ValueError(f"{field} must be >= {MIN_LLM_LOG_MAX_BODY_CHARS}")
    return parsed


def resolve_effective_llm_log_config() -> EffectiveLlmLogConfig:
    warnings: list[str] = []
    source = {
        "enabled": "default",
        "max_body_chars": "default",
        "safe_root": "default",
        "log_path": "derived",
    }
    max_body_chars = DEFAULT_LLM_LOG_MAX_BODY_CHARS
    raw_max = os.getenv("KERNEL_LLM_LOG_MAX_BODY_CHARS")
    if raw_max is not None and raw_max.strip():
        try:
            max_body_chars = _parse_positive_int(raw_max, field="KERNEL_LLM_LOG_MAX_BODY_CHARS")
            source["max_body_chars"] = "env"
        except ValueError as exc:
            warnings.append(str(exc))

    safe_root = LLM_LOG_SAFE_ROOT
    safe_root.mkdir(parents=True, exist_ok=True)
    filename = f"llm-api-{_LOG_SESSION_STAMP}-{_LOG_SESSION_SUFFIX}.log"
    log_path = safe_root / filename
    return EffectiveLlmLogConfig(
        enabled=True,
        max_body_chars=max_body_chars,
        safe_root=str(safe_root),
        log_path=str(log_path),
        source=source,
        warnings=warnings,
    )
