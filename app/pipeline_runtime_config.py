from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from app.config_governance import PIPELINE_RUNTIME_FIELD_GOVERNANCE
from app.paths import CONFIGS_DIR


PIPELINE_RUNTIME_CONFIG_PATH = CONFIGS_DIR / "pipeline_runtime_config.json"

_INT_FIELDS = (
    "recognition_batch_size",
    "detector_batch_size",
    "layout_batch_size",
    "ocr_error_batch_size",
    "table_rec_batch_size",
)
_DTYPE_FIELD = "model_dtype"
_ALLOWED_DTYPES = {"float16", "float32", "bfloat16"}
_BATCH_MIN = 1
_BATCH_MAX = 32
_ENV_MAP = {
    field: rule.env_var
    for field, rule in PIPELINE_RUNTIME_FIELD_GOVERNANCE["marker_tuning"].items()
    if rule.env_var
}
_MARKER_LLM_ENV_MAP = {
    field: rule.env_var
    for field, rule in PIPELINE_RUNTIME_FIELD_GOVERNANCE["marker_llm"].items()
    if rule.env_var
}

GEMINI_SERVICE = "gemini"
VERTEX_SERVICE = "marker.services.vertex.GoogleVertexService"
OLLAMA_SERVICE = "marker.services.ollama.OllamaService"
CLAUDE_SERVICE = "marker.services.claude.ClaudeService"
OPENAI_SERVICE = "marker.services.openai.OpenAIService"
AZURE_OPENAI_SERVICE = "marker.services.azure_openai.AzureOpenAIService"
_MARKER_LLM_SERVICE_ALIASES = {
    "gemini": GEMINI_SERVICE,
    "googlevertex": VERTEX_SERVICE,
    "google_vertex": VERTEX_SERVICE,
    "vertex": VERTEX_SERVICE,
    "marker.services.vertex.googlevertexservice": VERTEX_SERVICE,
    "ollama": OLLAMA_SERVICE,
    "marker.services.ollama.ollamaservice": OLLAMA_SERVICE,
    "claude": CLAUDE_SERVICE,
    "marker.services.claude.claudeservice": CLAUDE_SERVICE,
    "openai": OPENAI_SERVICE,
    "marker.services.openai.openaiservice": OPENAI_SERVICE,
    "azure": AZURE_OPENAI_SERVICE,
    "azure_openai": AZURE_OPENAI_SERVICE,
    "marker.services.azure_openai.azureopenaiservice": AZURE_OPENAI_SERVICE,
}
_MARKER_LLM_REQUIRED_FIELDS = {
    GEMINI_SERVICE: ("gemini_api_key",),
    VERTEX_SERVICE: ("vertex_project_id",),
    OLLAMA_SERVICE: ("ollama_base_url", "ollama_model"),
    CLAUDE_SERVICE: ("claude_api_key", "claude_model_name"),
    OPENAI_SERVICE: ("openai_api_key", "openai_model"),
    AZURE_OPENAI_SERVICE: ("azure_endpoint", "azure_api_key", "deployment_name"),
}
_MARKER_LLM_SECRET_FIELDS = {
    "gemini_api_key",
    "claude_api_key",
    "openai_api_key",
    "azure_api_key",
}


@dataclass(frozen=True)
class MarkerTuning:
    recognition_batch_size: int = 2
    detector_batch_size: int = 2
    layout_batch_size: int = 2
    ocr_error_batch_size: int = 1
    table_rec_batch_size: int = 1
    model_dtype: str = "float16"


@dataclass(frozen=True)
class MarkerLLMConfig:
    use_llm: bool = False
    llm_service: str = ""
    gemini_api_key: str = ""
    vertex_project_id: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    claude_api_key: str = ""
    claude_model_name: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    azure_endpoint: str = ""
    azure_api_key: str = ""
    deployment_name: str = ""


@dataclass(frozen=True)
class PipelineRuntimeConfig:
    marker_tuning: MarkerTuning
    marker_llm: MarkerLLMConfig
    updated_at: str


@dataclass(frozen=True)
class EffectiveMarkerTuning:
    values: MarkerTuning
    source: dict[str, str]
    warnings: list[str]


@dataclass(frozen=True)
class EffectiveMarkerLLM:
    values: MarkerLLMConfig
    source: dict[str, str]
    warnings: list[str]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_marker_tuning() -> MarkerTuning:
    return MarkerTuning()


def default_marker_llm() -> MarkerLLMConfig:
    return MarkerLLMConfig()


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("must be an integer")
        return int(text)
    raise ValueError("must be an integer")


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
    raise ValueError("must be a boolean")


def _normalize_marker_llm_service(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    normalized = text.lower().replace("-", "_")
    return _MARKER_LLM_SERVICE_ALIASES.get(normalized, text)


def validate_marker_tuning_payload(payload: Any) -> tuple[MarkerTuning, dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("marker_tuning must be an object")
    errors: dict[str, str] = {}
    parsed: dict[str, Any] = {}
    defaults = asdict(default_marker_tuning())

    for field in _INT_FIELDS:
        raw = payload.get(field, defaults[field])
        try:
            value = _coerce_int(raw)
        except Exception:
            errors[field] = "must be an integer"
            continue
        if value < _BATCH_MIN or value > _BATCH_MAX:
            errors[field] = f"must be between {_BATCH_MIN} and {_BATCH_MAX}"
            continue
        parsed[field] = value

    raw_dtype = str(payload.get(_DTYPE_FIELD, defaults[_DTYPE_FIELD]) or "").strip().lower()
    if not raw_dtype:
        raw_dtype = defaults[_DTYPE_FIELD]
    if raw_dtype not in _ALLOWED_DTYPES:
        errors[_DTYPE_FIELD] = f"must be one of {sorted(_ALLOWED_DTYPES)}"
    else:
        parsed[_DTYPE_FIELD] = raw_dtype

    return MarkerTuning(**parsed), errors


def validate_marker_llm_payload(payload: Any) -> tuple[MarkerLLMConfig, dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("marker_llm must be an object")
    defaults = asdict(default_marker_llm())
    errors: dict[str, str] = {}
    parsed: dict[str, Any] = {}

    try:
        parsed["use_llm"] = _coerce_bool(payload.get("use_llm", defaults["use_llm"]))
    except ValueError:
        errors["use_llm"] = "must be a boolean"
        parsed["use_llm"] = defaults["use_llm"]

    parsed["llm_service"] = _normalize_marker_llm_service(payload.get("llm_service", defaults["llm_service"]))
    if parsed["use_llm"] and not parsed["llm_service"]:
        errors["llm_service"] = "is required when use_llm is enabled"

    for field, default_value in defaults.items():
        if field in {"use_llm", "llm_service"}:
            continue
        parsed[field] = str(payload.get(field, default_value) or "").strip()

    if parsed["llm_service"] and parsed["llm_service"] not in _MARKER_LLM_REQUIRED_FIELDS:
        errors["llm_service"] = f"unsupported service: {parsed['llm_service']}"

    if parsed["use_llm"] and parsed["llm_service"] in _MARKER_LLM_REQUIRED_FIELDS:
        for field in _MARKER_LLM_REQUIRED_FIELDS[parsed["llm_service"]]:
            if not str(parsed.get(field, "")).strip():
                errors[field] = "is required for the selected llm_service"

    return MarkerLLMConfig(**parsed), errors


def mask_marker_llm_secrets(values: MarkerLLMConfig | dict[str, Any]) -> dict[str, Any]:
    payload = asdict(values) if isinstance(values, MarkerLLMConfig) else dict(values)
    for field in _MARKER_LLM_SECRET_FIELDS:
        raw = str(payload.get(field, "") or "")
        if not raw:
            payload[field] = ""
        elif len(raw) <= 8:
            payload[field] = "*" * len(raw)
        else:
            payload[field] = f"{raw[:4]}***{raw[-2:]}"
    return payload


def save_pipeline_runtime_config(
    *,
    marker_tuning: dict[str, Any],
    marker_llm: dict[str, Any] | None = None,
    path: Path | None = None,
) -> PipelineRuntimeConfig:
    tuning, errors = validate_marker_tuning_payload(marker_tuning)
    if errors:
        message = "; ".join(f"{field}: {reason}" for field, reason in errors.items())
        raise ValueError(message)
    llm_payload = dict(marker_llm or {})
    existing, _existing_err = load_pipeline_runtime_config(path=path)
    if existing is not None:
        existing_llm = asdict(existing.marker_llm)
        for field in _MARKER_LLM_SECRET_FIELDS:
            incoming = str(llm_payload.get(field, "") or "").strip()
            if not incoming and str(existing_llm.get(field, "")).strip():
                llm_payload[field] = existing_llm[field]
    llm_config, llm_errors = validate_marker_llm_payload(llm_payload)
    if llm_errors:
        message = "; ".join(f"{field}: {reason}" for field, reason in llm_errors.items())
        raise ValueError(message)
    config = PipelineRuntimeConfig(marker_tuning=tuning, marker_llm=llm_config, updated_at=_utc_now_iso())
    target = path or PIPELINE_RUNTIME_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def load_pipeline_runtime_config(path: Path | None = None) -> tuple[PipelineRuntimeConfig | None, str | None]:
    source = path or PIPELINE_RUNTIME_CONFIG_PATH
    if not source.exists():
        return None, None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"failed to parse pipeline runtime config: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid pipeline runtime config: payload must be a JSON object"
    marker_payload = payload.get("marker_tuning")
    tuning, errors = validate_marker_tuning_payload(marker_payload if marker_payload is not None else {})
    if errors:
        message = "; ".join(f"{field}: {reason}" for field, reason in errors.items())
        return None, f"invalid pipeline runtime config: {message}"
    llm_payload = payload.get("marker_llm")
    llm_config, llm_errors = validate_marker_llm_payload(llm_payload if llm_payload is not None else {})
    if llm_errors:
        message = "; ".join(f"{field}: {reason}" for field, reason in llm_errors.items())
        return None, f"invalid pipeline runtime config: {message}"
    updated_at = str(payload.get("updated_at", "")).strip() or _utc_now_iso()
    return PipelineRuntimeConfig(marker_tuning=tuning, marker_llm=llm_config, updated_at=updated_at), None


def _sanitize_runtime_value(field: str, value: Any) -> tuple[Any, bool]:
    if field in _INT_FIELDS:
        try:
            parsed = _coerce_int(value)
        except Exception:
            return None, False
        if parsed < _BATCH_MIN or parsed > _BATCH_MAX:
            return None, False
        return parsed, True
    dtype = str(value or "").strip().lower()
    if dtype in _ALLOWED_DTYPES:
        return dtype, True
    return None, False


def _sanitize_marker_llm_value(field: str, value: Any) -> tuple[Any, bool]:
    if field == "use_llm":
        try:
            return _coerce_bool(value), True
        except ValueError:
            return None, False
    if field == "llm_service":
        normalized = _normalize_marker_llm_service(value)
        if not normalized:
            return "", True
        return (normalized, True) if normalized in _MARKER_LLM_REQUIRED_FIELDS else (None, False)
    return str(value or "").strip(), True


def resolve_effective_marker_tuning(*, path: Path | None = None) -> EffectiveMarkerTuning:
    defaults = asdict(default_marker_tuning())
    runtime_payload: dict[str, Any] = {}
    warnings: list[str] = []
    config, load_err = load_pipeline_runtime_config(path=path)
    if load_err:
        warnings.append(load_err)
    if config is not None:
        runtime_payload = asdict(config.marker_tuning)

    effective: dict[str, Any] = {}
    source: dict[str, str] = {}
    for field, default_value in defaults.items():
        env_name = _ENV_MAP[field]
        env_raw = os.getenv(env_name)
        if env_raw is not None and str(env_raw).strip():
            env_value, ok = _sanitize_runtime_value(field, env_raw)
            if ok:
                effective[field] = env_value
                source[field] = "env"
                continue
            warnings.append(f"{env_name} is invalid, fallback to runtime/default")

        runtime_raw = runtime_payload.get(field)
        runtime_value, runtime_ok = _sanitize_runtime_value(field, runtime_raw)
        if runtime_ok:
            effective[field] = runtime_value
            source[field] = "runtime"
            continue
        if runtime_raw is not None:
            warnings.append(f"runtime field `{field}` is invalid, fallback to default")
        effective[field] = default_value
        source[field] = "default"

    return EffectiveMarkerTuning(values=MarkerTuning(**effective), source=source, warnings=warnings)


def resolve_effective_marker_llm(*, path: Path | None = None) -> EffectiveMarkerLLM:
    defaults = asdict(default_marker_llm())
    runtime_payload: dict[str, Any] = {}
    warnings: list[str] = []
    config, load_err = load_pipeline_runtime_config(path=path)
    if load_err:
        warnings.append(load_err)
    if config is not None:
        runtime_payload = asdict(config.marker_llm)

    effective: dict[str, Any] = {}
    source: dict[str, str] = {}
    for field, default_value in defaults.items():
        env_name = _MARKER_LLM_ENV_MAP[field]
        env_raw = os.getenv(env_name)
        if env_raw is not None and str(env_raw).strip():
            env_value, ok = _sanitize_marker_llm_value(field, env_raw)
            if ok:
                effective[field] = env_value
                source[field] = "env"
                continue
            warnings.append(f"{env_name} is invalid, fallback to runtime/default")

        runtime_raw = runtime_payload.get(field)
        runtime_value, runtime_ok = _sanitize_marker_llm_value(field, runtime_raw)
        if runtime_ok:
            effective[field] = runtime_value
            source[field] = "runtime" if runtime_raw is not None else "default"
            continue
        if runtime_raw is not None:
            warnings.append(f"runtime field `{field}` is invalid, fallback to default")
        effective[field] = default_value
        source[field] = "default"

    _, errors = validate_marker_llm_payload(effective)
    for field, message in errors.items():
        warnings.append(f"marker_llm `{field}` {message}")

    return EffectiveMarkerLLM(values=MarkerLLMConfig(**effective), source=source, warnings=warnings)
