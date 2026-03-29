from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Literal
import yaml

from app.admin_llm_config import mask_api_key, normalize_api_base, normalize_provider_alias
from app.config_governance import PLANNER_RUNTIME_FIELD_GOVERNANCE
from app.paths import CONFIGS_DIR


PLANNER_RUNTIME_CONFIG_PATH = CONFIGS_DIR / "planner_runtime_config.json"
PlannerServiceMode = Literal["production", "diagnostic"]
PLANNER_RUNTIME_API_KEY_ENV = "PLANNER_RUNTIME_API_KEY"
PLANNER_BLOCKED_REASON_MESSAGES: dict[str, str] = {
    "planner_diagnostic_mode": "Planner Runtime 当前处于诊断模式，正式聊天入口不可用。",
    "planner_legacy_disabled": "检测到历史 planner_use_llm=false 配置，正式模式已将其视为阻断。",
    "planner_model_missing": "Planner Runtime 缺少模型配置，正式聊天入口不可用。",
    "planner_api_key_missing": "Planner Runtime 缺少 API Key，正式聊天入口不可用。",
    "planner_invalid_service_mode": "Planner Runtime service_mode 非法，正式聊天入口不可用。",
}


@dataclass(frozen=True)
class PlannerRuntimeConfig:
    service_mode: PlannerServiceMode
    legacy_use_llm: bool | None
    provider: str
    api_base: str
    api_key: str
    model: str
    timeout_ms: int
    updated_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_planner_runtime_config() -> PlannerRuntimeConfig:
    return PlannerRuntimeConfig(
        service_mode="production",
        legacy_use_llm=None,
        provider="openai",
        api_base="https://api.siliconflow.cn/v1",
        api_key="",
        model="Pro/deepseek-ai/DeepSeek-V3.2",
        timeout_ms=6000,
        updated_at=_utc_now_iso(),
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("use_llm must be a boolean")


def _coerce_service_mode(value: Any) -> PlannerServiceMode:
    text = str(value or "").strip().lower()
    if text in {"", "production"}:
        return "production"
    if text == "diagnostic":
        return "diagnostic"
    raise ValueError("service_mode must be production or diagnostic")


def _coerce_legacy_use_llm(value: Any) -> bool | None:
    if value is None:
        return None
    return _coerce_bool(value)


def _compat_service_mode_from_payload(payload: dict[str, Any], defaults: PlannerRuntimeConfig) -> PlannerServiceMode:
    if "service_mode" in payload:
        return _coerce_service_mode(payload.get("service_mode", defaults.service_mode))
    legacy_use_llm = _coerce_legacy_use_llm(payload.get("use_llm"))
    if legacy_use_llm is False:
        return "diagnostic"
    return defaults.service_mode


def _coerce_timeout(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("timeout_ms must be an integer")
    if isinstance(value, int):
        timeout = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timeout_ms is required")
        timeout = int(text)
    if timeout < 1000:
        raise ValueError("timeout_ms must be >= 1000")
    return timeout


def validate_planner_runtime_payload(payload: Any) -> PlannerRuntimeConfig:
    if not isinstance(payload, dict):
        raise ValueError("planner runtime payload must be a JSON object")
    defaults = default_planner_runtime_config()
    service_mode = _compat_service_mode_from_payload(payload, defaults)
    legacy_use_llm = _coerce_legacy_use_llm(payload.get("use_llm"))
    provider = normalize_provider_alias(str(payload.get("provider", defaults.provider) or "").strip() or defaults.provider)
    api_base = normalize_api_base(str(payload.get("api_base", defaults.api_base) or defaults.api_base))
    api_key = str(payload.get("api_key", "") or "").strip()
    model = str(payload.get("model", defaults.model) or "").strip()
    timeout_ms = _coerce_timeout(payload.get("timeout_ms", defaults.timeout_ms))
    if not model:
        raise ValueError("planner.model is required")
    updated_at = str(payload.get("updated_at", "") or "").strip() or _utc_now_iso()
    return PlannerRuntimeConfig(
        service_mode=service_mode,
        legacy_use_llm=legacy_use_llm,
        provider=provider,
        api_base=api_base,
        api_key=api_key,
        model=model,
        timeout_ms=timeout_ms,
        updated_at=updated_at,
    )


def save_planner_runtime_config(
    *,
    service_mode: PlannerServiceMode,
    provider: str,
    api_base: str,
    api_key: str,
    model: str,
    timeout_ms: int,
    path: Path | None = None,
) -> PlannerRuntimeConfig:
    payload = {
        "service_mode": service_mode,
        "provider": provider,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "timeout_ms": timeout_ms,
        "updated_at": _utc_now_iso(),
    }
    config = validate_planner_runtime_payload(payload)
    target = path or PLANNER_RUNTIME_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def load_planner_runtime_config(path: Path | None = None) -> tuple[PlannerRuntimeConfig | None, str | None]:
    source = path or PLANNER_RUNTIME_CONFIG_PATH
    if not source.exists():
        return None, None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"failed to parse planner runtime config: {exc}"
    try:
        return validate_planner_runtime_payload(payload), None
    except ValueError as exc:
        return None, f"invalid planner runtime config: {exc}"


def load_effective_planner_runtime(config_path: str | Path | None = None) -> tuple[PlannerRuntimeConfig, dict[str, str], list[str]]:
    raw_data: dict[str, Any] = {}
    config_warnings: list[str] = []
    source = Path(config_path) if config_path is not None else (CONFIGS_DIR / "default.yaml")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        if isinstance(payload, dict):
            raw_data = payload
        else:
            config_warnings.append(f"Config root must be a mapping in {source}.")
    except FileNotFoundError:
        config_warnings.append(f"Config file not found: {source}.")
    except Exception as exc:
        config_warnings.append(f"Failed to load planner config from {source}: {exc}")

    runtime_cfg, runtime_err = load_planner_runtime_config()
    if runtime_err:
        config_warnings.append(f"Planner runtime config ignored: {runtime_err}")

    effective, source_map, planner_warnings = resolve_effective_planner_runtime(
        raw_data=raw_data,
        runtime_cfg=runtime_cfg if runtime_err is None else None,
    )
    return effective, source_map, config_warnings + planner_warnings


def resolve_effective_planner_runtime(
    *,
    raw_data: dict[str, Any],
    runtime_cfg: PlannerRuntimeConfig | None,
) -> tuple[PlannerRuntimeConfig, dict[str, str], list[str]]:
    defaults = default_planner_runtime_config()
    runtime_payload = asdict(runtime_cfg) if runtime_cfg is not None else {}
    source: dict[str, str] = {}
    warnings: list[str] = []

    def _select(field: str, default_value: Any, normalize: callable) -> Any:
        rule = PLANNER_RUNTIME_FIELD_GOVERNANCE.get(field)
        env_var = rule.env_var
        if rule.allow_env_override and env_var:
            env_value = str(__import__("os").environ.get(env_var, "") or "").strip()
            if env_value:
                try:
                    source[field] = "env"
                    return normalize(env_value)
                except Exception as exc:
                    warnings.append(f"Planner env override ignored for {field}: {exc}")
        if field in runtime_payload:
            try:
                source[field] = "runtime"
                return normalize(runtime_payload[field])
            except Exception as exc:
                warnings.append(f"Planner runtime config ignored for {field}: {exc}")
        raw_key = f"planner_{field}"
        if raw_key in raw_data:
            try:
                source[field] = "default"
                return normalize(raw_data.get(raw_key, default_value))
            except Exception as exc:
                warnings.append(f"Planner default config ignored for {field}: {exc}")
        source[field] = "default"
        return normalize(default_value)

    legacy_use_llm: bool | None = None
    legacy_source = "default"
    if runtime_cfg is not None and runtime_cfg.legacy_use_llm is not None:
        legacy_use_llm = runtime_cfg.legacy_use_llm
        legacy_source = "runtime"
    elif "planner_use_llm" in raw_data:
        try:
            legacy_use_llm = _coerce_bool(raw_data.get("planner_use_llm"))
        except Exception as exc:
            warnings.append(f"Planner default config ignored for planner_use_llm: {exc}")
        else:
            legacy_source = "default"
    env_legacy = str(os.environ.get("PLANNER_USE_LLM", "") or "").strip()
    if env_legacy:
        try:
            legacy_use_llm = _coerce_bool(env_legacy)
        except Exception as exc:
            warnings.append(f"Planner env override ignored for planner_use_llm: {exc}")
        else:
            legacy_source = "env"
    source["legacy_use_llm"] = legacy_source

    effective = PlannerRuntimeConfig(
        service_mode=_select("service_mode", defaults.service_mode, _coerce_service_mode),
        legacy_use_llm=legacy_use_llm,
        provider=_select("provider", str(raw_data.get("planner_provider", defaults.provider) or defaults.provider), lambda value: str(value or "").strip() or defaults.provider),
        api_base=_select("api_base", str(raw_data.get("planner_api_base", defaults.api_base) or defaults.api_base), lambda value: normalize_api_base(str(value or "").strip() or defaults.api_base)),
        api_key=_select("api_key", "", lambda value: str(value or "").strip()),
        model=_select("model", str(raw_data.get("planner_model", defaults.model) or defaults.model), lambda value: str(value or "").strip() or defaults.model),
        timeout_ms=_select("timeout_ms", int(raw_data.get("planner_timeout_ms", defaults.timeout_ms) or defaults.timeout_ms), _coerce_timeout),
        updated_at=runtime_cfg.updated_at if runtime_cfg is not None else defaults.updated_at,
    )
    if effective.legacy_use_llm is False:
        warnings.append("检测到历史 planner_use_llm=false；正式模式下该配置将被视为阻断，请迁移到 planner_service_mode=diagnostic。")
    return effective, source, warnings


def mask_planner_runtime_secrets(values: PlannerRuntimeConfig | dict[str, Any]) -> dict[str, Any]:
    payload = asdict(values) if isinstance(values, PlannerRuntimeConfig) else dict(values)
    payload["api_key_masked"] = mask_api_key(str(payload.get("api_key", "") or ""))
    payload.pop("api_key", None)
    return payload


def evaluate_planner_service_state(
    cfg: Any,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    service_mode_raw = getattr(cfg, "planner_service_mode", getattr(cfg, "service_mode", "production"))
    try:
        service_mode = _coerce_service_mode(service_mode_raw)
    except ValueError:
        service_mode = "production"
        invalid_mode = True
    else:
        invalid_mode = False
    legacy_use_llm = getattr(
        cfg,
        "planner_legacy_use_llm",
        getattr(cfg, "legacy_use_llm", getattr(cfg, "planner_use_llm", None)),
    )
    model = str(getattr(cfg, "planner_model", getattr(cfg, "model", "")) or "").strip()
    provider = str(getattr(cfg, "planner_provider", getattr(cfg, "provider", "")) or "").strip()
    api_base = str(getattr(cfg, "planner_api_base", getattr(cfg, "api_base", "")) or "").strip()
    api_key_env = str(getattr(cfg, "planner_api_key_env", PLANNER_RUNTIME_API_KEY_ENV) or "").strip()
    resolved_api_key = str(api_key if api_key is not None else os.getenv(api_key_env, "")).strip()
    reason_code: str | None = None
    if invalid_mode:
        reason_code = "planner_invalid_service_mode"
    elif service_mode == "diagnostic":
        reason_code = "planner_diagnostic_mode"
    elif legacy_use_llm is False:
        reason_code = "planner_legacy_disabled"
    elif not model:
        reason_code = "planner_model_missing"
    elif not resolved_api_key:
        reason_code = "planner_api_key_missing"
    blocked = reason_code is not None and service_mode == "production"
    formal_chat_available = service_mode == "production" and not blocked
    return {
        "service_mode": service_mode,
        "provider": provider,
        "api_base": api_base,
        "model": model,
        "api_key_env": api_key_env,
        "api_key_configured": bool(resolved_api_key),
        "legacy_use_llm": legacy_use_llm,
        "llm_required": service_mode == "production",
        "configured": bool(model and api_base and resolved_api_key),
        "blocked": blocked,
        "reason_code": reason_code,
        "reason_message": PLANNER_BLOCKED_REASON_MESSAGES.get(reason_code or "", ""),
        "formal_chat_available": formal_chat_available,
    }
