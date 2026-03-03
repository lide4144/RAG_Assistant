from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.paths import CONFIGS_DIR


RUNTIME_LLM_CONFIG_PATH = CONFIGS_DIR / "llm_runtime_config.json"


@dataclass(frozen=True)
class RuntimeStageConfig:
    provider: str
    api_base: str
    api_key: str
    model: str


@dataclass(frozen=True)
class RuntimeLLMConfig:
    answer: RuntimeStageConfig
    embedding: RuntimeStageConfig
    rerank: RuntimeStageConfig
    updated_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_api_base(value: str) -> str:
    base = str(value or "").strip().rstrip("/")
    if not base:
        raise ValueError("api_base is required")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("api_base must be a valid http(s) URL")
    return base


def mask_api_key(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return f"{raw[:2]}***"
    return f"{raw[:4]}***{raw[-4:]}"


def _parse_runtime_payload(payload: Any) -> RuntimeLLMConfig:
    if not isinstance(payload, dict):
        raise ValueError("runtime config payload must be a JSON object")

    def _parse_stage(stage_payload: Any, *, stage_name: str, default_provider: str) -> RuntimeStageConfig:
        if not isinstance(stage_payload, dict):
            raise ValueError(f"{stage_name} must be an object")
        provider = str(stage_payload.get("provider", "")).strip() or default_provider
        api_base = normalize_api_base(str(stage_payload.get("api_base", "")))
        api_key = str(stage_payload.get("api_key", "")).strip()
        model = str(stage_payload.get("model", "")).strip()
        if not api_key:
            raise ValueError(f"{stage_name}.api_key is required")
        if not model:
            raise ValueError(f"{stage_name}.model is required")
        return RuntimeStageConfig(provider=provider, api_base=api_base, api_key=api_key, model=model)

    if "answer" in payload or "embedding" in payload or "rerank" in payload:
        answer = _parse_stage(payload.get("answer"), stage_name="answer", default_provider="openai")
        embedding = _parse_stage(payload.get("embedding"), stage_name="embedding", default_provider="siliconflow")
        rerank = _parse_stage(payload.get("rerank"), stage_name="rerank", default_provider="siliconflow")
    else:
        # Backward compatibility for old single-stage runtime payload.
        api_base = normalize_api_base(str(payload.get("api_base", "")))
        api_key = str(payload.get("api_key", "")).strip()
        model = str(payload.get("model", "")).strip()
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")
        answer = RuntimeStageConfig(provider="openai", api_base=api_base, api_key=api_key, model=model)
        embedding = RuntimeStageConfig(provider="siliconflow", api_base=api_base, api_key=api_key, model=model)
        rerank = RuntimeStageConfig(provider="siliconflow", api_base=api_base, api_key=api_key, model=model)

    updated_at = str(payload.get("updated_at", "")).strip() or _utc_now_iso()
    return RuntimeLLMConfig(answer=answer, embedding=embedding, rerank=rerank, updated_at=updated_at)


def save_runtime_llm_config(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    answer: dict[str, str] | None = None,
    embedding: dict[str, str] | None = None,
    rerank: dict[str, str] | None = None,
    path: Path | None = None,
) -> RuntimeLLMConfig:
    target = path or RUNTIME_LLM_CONFIG_PATH
    if answer is not None or embedding is not None or rerank is not None:
        payload: dict[str, Any] = {
            "answer": answer or {},
            "embedding": embedding or {},
            "rerank": rerank or {},
            "updated_at": _utc_now_iso(),
        }
    else:
        payload = {
            "api_base": api_base,
            "api_key": api_key,
            "model": model,
            "updated_at": _utc_now_iso(),
        }
    config = _parse_runtime_payload(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def load_runtime_llm_config(path: Path | None = None) -> tuple[RuntimeLLMConfig | None, str | None]:
    source = path or RUNTIME_LLM_CONFIG_PATH
    if not source.exists():
        return None, None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"failed to parse runtime llm config: {exc}"
    try:
        return _parse_runtime_payload(payload), None
    except ValueError as exc:
        return None, f"invalid runtime llm config: {exc}"
