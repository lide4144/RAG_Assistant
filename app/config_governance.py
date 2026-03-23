from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Literal

from app.admin_llm_config import RuntimeLLMConfig, normalize_api_base


ConfigOwner = Literal["static", "runtime", "env_only"]
RuntimeSource = Literal["default", "runtime", "env"]


@dataclass(frozen=True)
class ConfigFieldGovernance:
    owner: ConfigOwner
    allow_env_override: bool
    env_var: str | None = None
    note: str = ""


@dataclass(frozen=True)
class EffectiveStageConfig:
    provider: str
    api_base: str
    api_key_env: str
    model: str


@dataclass(frozen=True)
class EffectiveLLMStage:
    values: EffectiveStageConfig
    source: dict[str, RuntimeSource]


@dataclass(frozen=True)
class EffectiveLLMStages:
    stages: dict[str, EffectiveLLMStage]
    warnings: list[str]


LLM_STAGE_FIELD_GOVERNANCE: dict[str, dict[str, ConfigFieldGovernance]] = {
    "answer": {
        "provider": ConfigFieldGovernance("runtime", True, "RAG_LLM_ANSWER_PROVIDER", "回答模型 provider"),
        "api_base": ConfigFieldGovernance("runtime", True, "RAG_LLM_ANSWER_API_BASE", "回答模型 API Base"),
        "api_key": ConfigFieldGovernance("runtime", True, "RAG_LLM_ANSWER_API_KEY", "回答模型 API Key"),
        "model": ConfigFieldGovernance("runtime", True, "RAG_LLM_ANSWER_MODEL", "回答模型 model"),
    },
    "embedding": {
        "provider": ConfigFieldGovernance("runtime", True, "RAG_LLM_EMBEDDING_PROVIDER", "向量模型 provider"),
        "api_base": ConfigFieldGovernance("runtime", True, "RAG_LLM_EMBEDDING_API_BASE", "向量模型 API Base"),
        "api_key": ConfigFieldGovernance("runtime", True, "RAG_LLM_EMBEDDING_API_KEY", "向量模型 API Key"),
        "model": ConfigFieldGovernance("runtime", True, "RAG_LLM_EMBEDDING_MODEL", "向量模型 model"),
    },
    "rerank": {
        "provider": ConfigFieldGovernance("runtime", True, "RAG_LLM_RERANK_PROVIDER", "重排模型 provider"),
        "api_base": ConfigFieldGovernance("runtime", True, "RAG_LLM_RERANK_API_BASE", "重排模型 API Base"),
        "api_key": ConfigFieldGovernance("runtime", True, "RAG_LLM_RERANK_API_KEY", "重排模型 API Key"),
        "model": ConfigFieldGovernance("runtime", True, "RAG_LLM_RERANK_MODEL", "重排模型 model"),
    },
    "rewrite": {
        "provider": ConfigFieldGovernance("runtime", True, "RAG_LLM_REWRITE_PROVIDER", "问题改写模型 provider"),
        "api_base": ConfigFieldGovernance("runtime", True, "RAG_LLM_REWRITE_API_BASE", "问题改写模型 API Base"),
        "api_key": ConfigFieldGovernance("runtime", True, "RAG_LLM_REWRITE_API_KEY", "问题改写模型 API Key"),
        "model": ConfigFieldGovernance("runtime", True, "RAG_LLM_REWRITE_MODEL", "问题改写模型 model"),
    },
    "graph_entity": {
        "provider": ConfigFieldGovernance("runtime", True, "RAG_LLM_GRAPH_ENTITY_PROVIDER", "图谱实体模型 provider"),
        "api_base": ConfigFieldGovernance("runtime", True, "RAG_LLM_GRAPH_ENTITY_API_BASE", "图谱实体模型 API Base"),
        "api_key": ConfigFieldGovernance("runtime", True, "RAG_LLM_GRAPH_ENTITY_API_KEY", "图谱实体模型 API Key"),
        "model": ConfigFieldGovernance("runtime", True, "RAG_LLM_GRAPH_ENTITY_MODEL", "图谱实体模型 model"),
    },
    "sufficiency_judge": {
        "provider": ConfigFieldGovernance("runtime", True, "RAG_LLM_SUFFICIENCY_JUDGE_PROVIDER", "证据充分性判定模型 provider"),
        "api_base": ConfigFieldGovernance("runtime", True, "RAG_LLM_SUFFICIENCY_JUDGE_API_BASE", "证据充分性判定模型 API Base"),
        "api_key": ConfigFieldGovernance("runtime", True, "RAG_LLM_SUFFICIENCY_JUDGE_API_KEY", "证据充分性判定模型 API Key"),
        "model": ConfigFieldGovernance("runtime", True, "RAG_LLM_SUFFICIENCY_JUDGE_MODEL", "证据充分性判定模型 model"),
    },
}

PIPELINE_RUNTIME_FIELD_GOVERNANCE: dict[str, dict[str, ConfigFieldGovernance]] = {
    "marker_tuning": {
        "recognition_batch_size": ConfigFieldGovernance("runtime", True, "RECOGNITION_BATCH_SIZE"),
        "detector_batch_size": ConfigFieldGovernance("runtime", True, "DETECTOR_BATCH_SIZE"),
        "layout_batch_size": ConfigFieldGovernance("runtime", True, "LAYOUT_BATCH_SIZE"),
        "ocr_error_batch_size": ConfigFieldGovernance("runtime", True, "OCR_ERROR_BATCH_SIZE"),
        "table_rec_batch_size": ConfigFieldGovernance("runtime", True, "TABLE_REC_BATCH_SIZE"),
        "model_dtype": ConfigFieldGovernance("runtime", True, "MODEL_DTYPE"),
    },
    "marker_llm": {
        "use_llm": ConfigFieldGovernance("runtime", True, "MARKER_USE_LLM"),
        "llm_service": ConfigFieldGovernance("runtime", True, "MARKER_LLM_SERVICE"),
        "gemini_api_key": ConfigFieldGovernance("runtime", True, "GEMINI_API_KEY"),
        "vertex_project_id": ConfigFieldGovernance("runtime", True, "VERTEX_PROJECT_ID"),
        "ollama_base_url": ConfigFieldGovernance("runtime", True, "OLLAMA_BASE_URL"),
        "ollama_model": ConfigFieldGovernance("runtime", True, "OLLAMA_MODEL"),
        "claude_api_key": ConfigFieldGovernance("runtime", True, "CLAUDE_API_KEY"),
        "claude_model_name": ConfigFieldGovernance("runtime", True, "CLAUDE_MODEL_NAME"),
        "openai_api_key": ConfigFieldGovernance("runtime", True, "OPENAI_API_KEY"),
        "openai_model": ConfigFieldGovernance("runtime", True, "OPENAI_MODEL"),
        "openai_base_url": ConfigFieldGovernance("runtime", True, "OPENAI_BASE_URL"),
        "azure_endpoint": ConfigFieldGovernance("runtime", True, "AZURE_ENDPOINT"),
        "azure_api_key": ConfigFieldGovernance("runtime", True, "AZURE_API_KEY"),
        "deployment_name": ConfigFieldGovernance("runtime", True, "DEPLOYMENT_NAME"),
    },
}

PLANNER_RUNTIME_FIELD_GOVERNANCE: dict[str, ConfigFieldGovernance] = {
    "use_llm": ConfigFieldGovernance("runtime", True, "PLANNER_USE_LLM"),
    "provider": ConfigFieldGovernance("runtime", True, "PLANNER_PROVIDER"),
    "api_base": ConfigFieldGovernance("runtime", True, "PLANNER_API_BASE"),
    "api_key": ConfigFieldGovernance("runtime", True, "PLANNER_API_KEY"),
    "model": ConfigFieldGovernance("runtime", True, "PLANNER_MODEL"),
    "timeout_ms": ConfigFieldGovernance("runtime", True, "PLANNER_TIMEOUT_MS"),
}

STATIC_BASELINE_FIELDS: tuple[str, ...] = (
    "chunk_size",
    "overlap",
    "top_k_retrieval",
    "top_n_evidence",
    "rewrite_meta_patterns",
    "planner_enabled",
    "session_store_backend",
    "graph_expand_alpha",
)

ENV_ONLY_FIELDS: tuple[str, ...] = (
    "KERNEL_CORS_ALLOW_ORIGINS",
    "KERNEL_ADMIN_UPSTREAM_TIMEOUT_SEC",
    "SESSION_REDIS_URL",
    "OPENAI_API_KEY",
    "SILICONFLOW_API_KEY",
)


def runtime_source_label(source: RuntimeSource) -> str:
    return {
        "default": "静态基线",
        "runtime": "运行时保存",
        "env": "环境变量",
    }.get(source, source)


def _runtime_stage_defaults(raw_data: dict[str, Any], *, stage: str) -> EffectiveStageConfig:
    if stage == "answer":
        return EffectiveStageConfig(
            provider=str(raw_data.get("answer_llm_provider", "siliconflow") or "siliconflow"),
            api_base=str(raw_data.get("answer_llm_api_base", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"),
            api_key_env=str(raw_data.get("answer_llm_api_key_env", "SILICONFLOW_API_KEY") or "SILICONFLOW_API_KEY"),
            model=str(raw_data.get("answer_llm_model", "Pro/deepseek-ai/DeepSeek-V3.2") or "Pro/deepseek-ai/DeepSeek-V3.2"),
        )
    if stage == "embedding":
        return EffectiveStageConfig(
            provider=str(raw_data.get("embedding_provider", "siliconflow") or "siliconflow"),
            api_base=str(raw_data.get("embedding_api_base", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"),
            api_key_env=str(raw_data.get("embedding_api_key_env", "SILICONFLOW_API_KEY") or "SILICONFLOW_API_KEY"),
            model=str(raw_data.get("embedding_model", "BAAI/bge-large-zh-v1.5") or "BAAI/bge-large-zh-v1.5"),
        )
    if stage == "rerank":
        return EffectiveStageConfig(
            provider=str(raw_data.get("rerank_provider", "siliconflow") or "siliconflow"),
            api_base=str(raw_data.get("rerank_api_base", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"),
            api_key_env=str(raw_data.get("rerank_api_key_env", "SILICONFLOW_API_KEY") or "SILICONFLOW_API_KEY"),
            model=str(raw_data.get("rerank_model", "Qwen/Qwen3-Reranker-8B") or "Qwen/Qwen3-Reranker-8B"),
        )
    if stage == "rewrite":
        return EffectiveStageConfig(
            provider=str(raw_data.get("rewrite_llm_provider", "siliconflow") or "siliconflow"),
            api_base=str(raw_data.get("rewrite_llm_api_base", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"),
            api_key_env=str(raw_data.get("rewrite_llm_api_key_env", "SILICONFLOW_API_KEY") or "SILICONFLOW_API_KEY"),
            model=str(raw_data.get("rewrite_llm_model", "Pro/deepseek-ai/DeepSeek-V3.2") or "Pro/deepseek-ai/DeepSeek-V3.2"),
        )
    if stage == "sufficiency_judge":
        return EffectiveStageConfig(
            provider=str(raw_data.get("sufficiency_judge_llm_provider", "siliconflow") or "siliconflow"),
            api_base=str(raw_data.get("sufficiency_judge_llm_api_base", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"),
            api_key_env=str(raw_data.get("sufficiency_judge_llm_api_key_env", "SILICONFLOW_API_KEY") or "SILICONFLOW_API_KEY"),
            model=str(raw_data.get("sufficiency_judge_llm_model", "Qwen/Qwen2.5-7B-Instruct") or "Qwen/Qwen2.5-7B-Instruct"),
        )
    return EffectiveStageConfig(
        provider=str(raw_data.get("graph_entity_llm_provider", "siliconflow") or "siliconflow"),
        api_base=str(raw_data.get("graph_entity_llm_base_url", "https://api.siliconflow.cn/v1") or "https://api.siliconflow.cn/v1"),
        api_key_env=str(raw_data.get("graph_entity_llm_api_key_env", "SILICONFLOW_API_KEY") or "SILICONFLOW_API_KEY"),
        model=str(raw_data.get("graph_entity_llm_model", "Pro/deepseek-ai/DeepSeek-V3.2") or "Pro/deepseek-ai/DeepSeek-V3.2"),
    )


def _runtime_stage_value(runtime_cfg: RuntimeLLMConfig | None, *, stage: str, field: str) -> str | None:
    if runtime_cfg is None:
        return None
    stage_cfg = getattr(runtime_cfg, stage)
    if field == "api_key":
        return str(stage_cfg.api_key or "").strip()
    return str(getattr(stage_cfg, field) or "").strip()


def _normalize_llm_field(field: str, value: str) -> str:
    text = str(value or "").strip()
    if field == "api_base":
        return normalize_api_base(text)
    return text


def resolve_effective_llm_stages(
    *,
    raw_data: dict[str, Any],
    runtime_cfg: RuntimeLLMConfig | None,
    runtime_api_key_env_prefix: str,
) -> EffectiveLLMStages:
    stages: dict[str, EffectiveLLMStage] = {}
    warnings: list[str] = []

    for stage, governance in LLM_STAGE_FIELD_GOVERNANCE.items():
        defaults = _runtime_stage_defaults(raw_data, stage=stage)
        values = {
            "provider": defaults.provider,
            "api_base": defaults.api_base,
            "api_key_env": defaults.api_key_env,
            "model": defaults.model,
        }
        source: dict[str, RuntimeSource] = {
            "provider": "default",
            "api_base": "default",
            "api_key": "default",
            "model": "default",
        }

        for field in ("provider", "api_base", "api_key", "model"):
            runtime_value = _runtime_stage_value(runtime_cfg, stage=stage, field=field)
            if runtime_value:
                if field == "api_key":
                    env_name = f"{runtime_api_key_env_prefix}_{stage.upper()}"
                    os.environ[env_name] = runtime_value
                    values["api_key_env"] = env_name
                else:
                    values[field] = runtime_value
                source[field] = "runtime"

            rule = governance[field]
            env_name = rule.env_var
            env_value = str(os.getenv(env_name or "", "") or "").strip() if env_name else ""
            if not (rule.allow_env_override and env_name and env_value):
                continue
            try:
                normalized = _normalize_llm_field(field, env_value)
            except ValueError as exc:
                warnings.append(f"{env_name} is invalid for {stage}.{field}: {exc}")
                continue
            if field == "api_key":
                values["api_key_env"] = env_name
            else:
                values[field] = normalized
            source[field] = "env"

        stages[stage] = EffectiveLLMStage(
            values=EffectiveStageConfig(
                provider=values["provider"],
                api_base=values["api_base"],
                api_key_env=values["api_key_env"],
                model=values["model"],
            ),
            source=source,
        )

    return EffectiveLLMStages(stages=stages, warnings=warnings)
