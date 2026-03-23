from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.admin_llm_config import mask_api_key, normalize_api_base
from app.config_governance import PLANNER_RUNTIME_FIELD_GOVERNANCE
from app.paths import CONFIGS_DIR


PLANNER_RUNTIME_CONFIG_PATH = CONFIGS_DIR / "planner_runtime_config.json"


@dataclass(frozen=True)
class PlannerRuntimeConfig:
    use_llm: bool
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
        use_llm=False,
        provider="siliconflow",
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
    use_llm = _coerce_bool(payload.get("use_llm", defaults.use_llm))
    provider = str(payload.get("provider", defaults.provider) or "").strip() or defaults.provider
    api_base = normalize_api_base(str(payload.get("api_base", defaults.api_base) or defaults.api_base))
    api_key = str(payload.get("api_key", "") or "").strip()
    model = str(payload.get("model", defaults.model) or "").strip()
    timeout_ms = _coerce_timeout(payload.get("timeout_ms", defaults.timeout_ms))
    if not model:
        raise ValueError("planner.model is required")
    if use_llm and not api_key:
        raise ValueError("planner.api_key is required when use_llm is enabled")
    updated_at = str(payload.get("updated_at", "") or "").strip() or _utc_now_iso()
    return PlannerRuntimeConfig(
        use_llm=use_llm,
        provider=provider,
        api_base=api_base,
        api_key=api_key,
        model=model,
        timeout_ms=timeout_ms,
        updated_at=updated_at,
    )


def save_planner_runtime_config(
    *,
    use_llm: bool,
    provider: str,
    api_base: str,
    api_key: str,
    model: str,
    timeout_ms: int,
    path: Path | None = None,
) -> PlannerRuntimeConfig:
    payload = {
        "use_llm": use_llm,
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
        rule = PLANNER_RUNTIME_FIELD_GOVERNANCE[field]
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
        raw_key = "planner_use_llm" if field == "use_llm" else f"planner_{field}"
        if raw_key in raw_data:
            try:
                source[field] = "default"
                return normalize(raw_data.get(raw_key, default_value))
            except Exception as exc:
                warnings.append(f"Planner default config ignored for {field}: {exc}")
        source[field] = "default"
        return normalize(default_value)

    effective = PlannerRuntimeConfig(
        use_llm=_select("use_llm", defaults.use_llm, _coerce_bool),
        provider=_select("provider", str(raw_data.get("planner_provider", defaults.provider) or defaults.provider), lambda value: str(value or "").strip() or defaults.provider),
        api_base=_select("api_base", str(raw_data.get("planner_api_base", defaults.api_base) or defaults.api_base), lambda value: normalize_api_base(str(value or "").strip() or defaults.api_base)),
        api_key=_select("api_key", "", lambda value: str(value or "").strip()),
        model=_select("model", str(raw_data.get("planner_model", defaults.model) or defaults.model), lambda value: str(value or "").strip() or defaults.model),
        timeout_ms=_select("timeout_ms", int(raw_data.get("planner_timeout_ms", defaults.timeout_ms) or defaults.timeout_ms), _coerce_timeout),
        updated_at=runtime_cfg.updated_at if runtime_cfg is not None else defaults.updated_at,
    )
    return effective, source, warnings


def mask_planner_runtime_secrets(values: PlannerRuntimeConfig | dict[str, Any]) -> dict[str, Any]:
    payload = asdict(values) if isinstance(values, PlannerRuntimeConfig) else dict(values)
    payload["api_key_masked"] = mask_api_key(str(payload.get("api_key", "") or ""))
    payload.pop("api_key", None)
    return payload
