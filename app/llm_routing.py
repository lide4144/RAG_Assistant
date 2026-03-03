from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


RECOVERABLE_ERROR_CATEGORIES = {"timeout", "rate_limit", "http_5xx", "network"}
STAGE_FAILURE_CATEGORIES = {
    "missing_api_key",
    "auth_failed",
    "timeout",
    "network_error",
    "server_error",
    "dimension_mismatch",
    "other",
}


@dataclass(frozen=True)
class LLMRouteTarget:
    provider: str
    model: str
    api_base: str
    api_key_env: str

    @property
    def route_id(self) -> str:
        return f"{self.provider}:{self.model}@{self.api_base}"

    def resolve_api_key(self) -> str | None:
        value = os.getenv(self.api_key_env, "").strip()
        return value or None


@dataclass(frozen=True)
class LLMRoutePolicy:
    stage: str
    primary: LLMRouteTarget
    fallback: LLMRouteTarget | None
    max_retries: int
    cooldown_seconds: int
    failure_threshold: int
    use_litellm_sdk: bool
    use_legacy_client: bool


@dataclass(frozen=True)
class StageFallbackSignal:
    stage: str
    failure_category: str
    can_fallback: bool
    fallback_mode: str | None


_COOLDOWN_UNTIL: dict[str, float] = {}
_FAILURE_COUNTS: dict[str, int] = {}
_LAST_STAGE_FAILURE: dict[str, dict[str, Any]] = {}


def build_stage_policy(config: Any, *, stage: str) -> LLMRoutePolicy:
    stage = stage.strip().lower()
    if stage not in {"rewrite", "answer", "embedding", "rerank"}:
        raise ValueError(f"unsupported llm stage: {stage}")

    if stage in {"rewrite", "answer"}:
        prefix = "rewrite" if stage == "rewrite" else "answer"
        primary = LLMRouteTarget(
            provider=str(getattr(config, f"{prefix}_llm_provider", "")).strip() or "openai",
            model=str(getattr(config, f"{prefix}_llm_model", "")).strip(),
            api_base=str(getattr(config, f"{prefix}_llm_api_base", "")).strip(),
            api_key_env=str(getattr(config, f"{prefix}_llm_api_key_env", "")).strip() or "SILICONFLOW_API_KEY",
        )
        fb_model = str(getattr(config, f"{prefix}_llm_fallback_model", "")).strip()
        fb_provider = str(getattr(config, f"{prefix}_llm_fallback_provider", "")).strip() or primary.provider
        fb_base = str(getattr(config, f"{prefix}_llm_fallback_api_base", "")).strip() or primary.api_base
        fb_key_env = str(getattr(config, f"{prefix}_llm_fallback_api_key_env", "")).strip() or primary.api_key_env
    else:
        legacy_block = getattr(config, stage, None)

        def _stage_value(field_name: str, *, legacy_name: str, default: str) -> str:
            preferred = str(getattr(config, f"{stage}_{field_name}", "")).strip()
            legacy = ""
            if legacy_block is not None:
                legacy = str(getattr(legacy_block, legacy_name, "")).strip()
            if preferred:
                # Keep backward compatibility when code mutates legacy nested config at runtime.
                if legacy and preferred == default and legacy != default:
                    return legacy
                return preferred
            if legacy:
                return legacy
            return default

        primary = LLMRouteTarget(
            provider=_stage_value("provider", legacy_name="provider", default="siliconflow"),
            model=_stage_value("model", legacy_name="model", default=""),
            api_base=_stage_value("api_base", legacy_name="base_url", default="https://api.siliconflow.cn/v1"),
            api_key_env=_stage_value("api_key_env", legacy_name="api_key_env", default="SILICONFLOW_API_KEY"),
        )
        fb_model = str(getattr(config, f"{stage}_fallback_model", "")).strip()
        fb_provider = str(getattr(config, f"{stage}_fallback_provider", "")).strip() or primary.provider
        fb_base = str(getattr(config, f"{stage}_fallback_api_base", "")).strip() or primary.api_base
        fb_key_env = str(getattr(config, f"{stage}_fallback_api_key_env", "")).strip() or primary.api_key_env

    fallback: LLMRouteTarget | None = None
    if fb_model:
        fallback = LLMRouteTarget(
            provider=fb_provider,
            model=fb_model,
            api_base=fb_base,
            api_key_env=fb_key_env,
        )

    return LLMRoutePolicy(
        stage=stage,
        primary=primary,
        fallback=fallback,
        max_retries=max(0, int(getattr(config, "llm_router_retry", getattr(config, "llm_max_retries", 0)))),
        cooldown_seconds=max(0, int(getattr(config, "llm_router_cooldown_sec", 0))),
        failure_threshold=max(1, int(getattr(config, "llm_router_failure_threshold", 1))),
        use_litellm_sdk=bool(getattr(config, "llm_use_litellm_sdk", True)),
        use_legacy_client=bool(getattr(config, "llm_use_legacy_client", False)),
    )


def classify_error_category(reason: str | None, status_code: int | None = None) -> str:
    normalized = str(reason or "").strip().lower()
    if normalized in {"timeout", "stream_first_token_timeout"}:
        return "timeout"
    if normalized == "rate_limit" or status_code == 429:
        return "rate_limit"
    if normalized in {"network_error", "stream_interrupted"}:
        return "network"
    if normalized == "http_error" and isinstance(status_code, int) and 500 <= status_code < 600:
        return "http_5xx"
    return "other"


def is_recoverable(reason: str | None, status_code: int | None = None) -> bool:
    return classify_error_category(reason, status_code) in RECOVERABLE_ERROR_CATEGORIES


def is_in_cooldown(route_id: str) -> bool:
    until = _COOLDOWN_UNTIL.get(route_id, 0.0)
    return until > time.time()


def register_route_success(route_id: str) -> None:
    _FAILURE_COUNTS.pop(route_id, None)
    _COOLDOWN_UNTIL.pop(route_id, None)


def register_route_failure(route_id: str, *, failure_threshold: int, cooldown_seconds: int) -> None:
    cnt = _FAILURE_COUNTS.get(route_id, 0) + 1
    _FAILURE_COUNTS[route_id] = cnt
    if cnt >= max(1, int(failure_threshold)) and cooldown_seconds > 0:
        _COOLDOWN_UNTIL[route_id] = time.time() + cooldown_seconds
        _FAILURE_COUNTS[route_id] = 0


def normalize_stage_failure_category(category: str | None) -> str:
    normalized = str(category or "").strip().lower()
    if normalized in STAGE_FAILURE_CATEGORIES:
        return normalized
    return "other"


def register_stage_failure(stage: str, *, category: str, reason: str | None = None) -> None:
    stage_key = stage.strip().lower()
    _LAST_STAGE_FAILURE[stage_key] = {
        "category": normalize_stage_failure_category(category),
        "reason": str(reason or category or "").strip(),
        "checked_at": int(time.time()),
    }


def register_stage_success(stage: str) -> None:
    _LAST_STAGE_FAILURE.pop(stage.strip().lower(), None)


def get_last_stage_failure(stage: str) -> dict[str, Any] | None:
    value = _LAST_STAGE_FAILURE.get(stage.strip().lower())
    if not value:
        return None
    return dict(value)


def build_stage_fallback_signal(stage: str, *, category: str) -> StageFallbackSignal:
    stage_key = stage.strip().lower()
    normalized = normalize_stage_failure_category(category)
    if stage_key == "embedding":
        can_fallback = normalized in {"missing_api_key", "auth_failed", "timeout", "network_error", "server_error", "dimension_mismatch"}
        fallback_mode = "tfidf" if can_fallback else None
        return StageFallbackSignal(stage=stage_key, failure_category=normalized, can_fallback=can_fallback, fallback_mode=fallback_mode)
    if stage_key == "rerank":
        can_fallback = normalized in {"timeout", "network_error", "server_error", "missing_api_key", "auth_failed"}
        fallback_mode = "passthrough_retrieval" if can_fallback else None
        return StageFallbackSignal(stage=stage_key, failure_category=normalized, can_fallback=can_fallback, fallback_mode=fallback_mode)
    return StageFallbackSignal(stage=stage_key, failure_category=normalized, can_fallback=False, fallback_mode=None)
