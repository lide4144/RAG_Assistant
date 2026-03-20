from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml

from app.admin_llm_config import load_runtime_llm_config

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")
RUNTIME_LLM_API_KEY_ENV = "RAG_RUNTIME_LLM_API_KEY"


@dataclass
class EmbeddingConfig:
    enabled: bool = True
    provider: str = "siliconflow"
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "BAAI/bge-large-zh-v1.5"
    api_key_env: str = "SILICONFLOW_API_KEY"
    batch_size: int = 32
    normalize: bool = True
    cache_enabled: bool = True
    cache_path: str = "data/indexes/embedding_cache.jsonl"
    failure_log_path: str = "data/indexes/embedding_failures.jsonl"
    max_requests_per_minute: int = 120
    max_concurrent_requests: int = 2
    max_retries: int = 2
    backoff_base_ms: int = 500
    backoff_max_ms: int = 8000
    max_tokens_per_chunk: int = 512
    over_limit_strategy: str = "truncate"
    max_failed_chunk_ids: int = 200
    max_skipped_chunk_ids: int = 200


@dataclass
class RerankConfig:
    enabled: bool = True
    provider: str = "siliconflow"
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "Qwen/Qwen3-Reranker-8B"
    api_key_env: str = "SILICONFLOW_API_KEY"
    top_n: int = 8
    timeout_ms: int = 8000
    max_retries: int = 1
    fallback_to_retrieval: bool = True


@dataclass
class PipelineConfig:
    chunk_size: int = 400
    overlap: int = 50
    marker_enabled: bool = True
    marker_timeout_sec: float = 30.0
    title_confidence_threshold: float = 0.6
    title_blacklist_patterns: list[str] = field(
        default_factory=lambda: [
            r"^\s*preprint\.?\s+under\s+review\.?\s*$",
            r"all rights reserved",
            r"copyright",
            r"arxiv preprint",
            r"provided proper attribution is provided",
            r"hereby grants permission to",
        ]
    )
    top_k_retrieval: int = 20
    alpha_expansion: float = 0.3
    top_n_evidence: int = 8
    fusion_weight: float = 0.5
    RRF_k: int = 60
    sufficiency_threshold: float = 0.7
    table_list_downweight: float = 0.5
    front_matter_downweight: float = 0.3
    reference_downweight: float = 0.3
    rewrite_enabled: bool = True
    rewrite_meta_guard_enabled: bool = True
    rewrite_use_llm: bool = False
    rewrite_parallel_candidates_enabled: bool = True
    rewrite_arbitration_enabled: bool = True
    rewrite_arbitration_min_delta: float = 0.03
    rewrite_legacy_strategy_enabled: bool = False
    rewrite_entity_preservation_min_ratio: float = 0.6
    rewrite_llm_provider: str = "siliconflow"
    rewrite_llm_model: str = "Pro/deepseek-ai/DeepSeek-V3.2"
    rewrite_llm_api_base: str = "https://api.siliconflow.cn/v1"
    rewrite_llm_api_key_env: str = "SILICONFLOW_API_KEY"
    rewrite_llm_fallback_provider: str = "siliconflow"
    rewrite_llm_fallback_model: str = ""
    rewrite_llm_fallback_api_base: str = ""
    rewrite_llm_fallback_api_key_env: str = ""
    answer_use_llm: bool = False
    answer_llm_provider: str = "siliconflow"
    answer_llm_model: str = "Pro/deepseek-ai/DeepSeek-V3.2"
    answer_llm_api_base: str = "https://api.siliconflow.cn/v1"
    answer_llm_api_key_env: str = "SILICONFLOW_API_KEY"
    answer_llm_fallback_provider: str = "siliconflow"
    answer_llm_fallback_model: str = ""
    answer_llm_fallback_api_base: str = ""
    answer_llm_fallback_api_key_env: str = ""
    embedding_provider: str = "siliconflow"
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_api_base: str = "https://api.siliconflow.cn/v1"
    embedding_api_key_env: str = "SILICONFLOW_API_KEY"
    embedding_fallback_provider: str = "siliconflow"
    embedding_fallback_model: str = ""
    embedding_fallback_api_base: str = ""
    embedding_fallback_api_key_env: str = ""
    rerank_provider: str = "siliconflow"
    rerank_model: str = "Qwen/Qwen3-Reranker-8B"
    rerank_api_base: str = "https://api.siliconflow.cn/v1"
    rerank_api_key_env: str = "SILICONFLOW_API_KEY"
    rerank_fallback_provider: str = "siliconflow"
    rerank_fallback_model: str = ""
    rerank_fallback_api_base: str = ""
    rerank_fallback_api_key_env: str = ""
    llm_timeout_ms: int = 12000
    answer_llm_timeout_ms: int = 30000
    answer_stream_enabled: bool = False
    llm_max_retries: int = 1
    llm_fallback_enabled: bool = True
    llm_use_litellm_sdk: bool = True
    llm_use_legacy_client: bool = False
    llm_router_retry: int = 1
    llm_router_cooldown_sec: int = 60
    llm_router_failure_threshold: int = 2
    max_context_tokens: int = 6000
    rewrite_max_keywords: int = 12
    evidence_policy_enforced: bool = True
    sufficiency_gate_enabled: bool = True
    sufficiency_topic_match_threshold: float = 0.15
    sufficiency_semantic_policy: str = "balanced"
    sufficiency_semantic_threshold_strict: float = 0.35
    sufficiency_semantic_threshold_balanced: float = 0.25
    sufficiency_semantic_threshold_explore: float = 0.15
    sufficiency_key_element_min_coverage: float = 1.0
    sufficiency_judge_use_llm: bool = True
    sufficiency_judge_llm_provider: str = "siliconflow"
    sufficiency_judge_llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    sufficiency_judge_llm_api_base: str = "https://api.siliconflow.cn/v1"
    sufficiency_judge_llm_api_key_env: str = "SILICONFLOW_API_KEY"
    sufficiency_judge_llm_timeout_ms: int = 6000
    assistant_mode_enabled: bool = True
    assistant_mode_force_legacy_gate: bool = False
    assistant_mode_clarify_limit: int = 2
    assistant_mode_force_partial_answer_on_limit: bool = True
    session_store_backend: str = "redis"
    session_redis_url: str = "redis://localhost:6379/0"
    session_redis_ttl_sec: int = 86400
    session_redis_key_prefix: str = "rag"
    session_redis_fallback_to_file: bool = True
    session_recent_turns_window: int = 3
    session_memory_summary_enabled: bool = True
    session_memory_semantic_enabled: bool = True
    ui_legacy_layout_default: bool = False
    intent_router_enabled: bool = False
    intent_router_semantic_enabled: bool = True
    intent_control_min_confidence: float = 0.75
    style_control_reuse_last_topic: bool = True
    style_control_max_turn_distance: int = 3
    planner_enabled: bool = True
    planner_use_llm: bool = False
    planner_provider: str = "siliconflow"
    planner_model: str = "Pro/deepseek-ai/DeepSeek-V3.2"
    planner_api_base: str = "https://api.siliconflow.cn/v1"
    planner_api_key_env: str = "SILICONFLOW_API_KEY"
    planner_timeout_ms: int = 6000
    planner_max_steps: int = 3
    planner_max_papers: int = 20
    planner_summary_min_papers: int = 2
    index_incremental_enabled: bool = False
    index_incremental_strategy: str = "rebuild"
    dense_backend: str = "embedding"
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    graph_path: str = "data/processed/graph.json"
    graph_entity_llm_provider: str = "siliconflow"
    graph_entity_llm_base_url: str = "https://api.siliconflow.cn/v1"
    graph_entity_llm_api_key_env: str = "SILICONFLOW_API_KEY"
    graph_entity_llm_model: str = "Pro/deepseek-ai/DeepSeek-V3.2"
    graph_entity_llm_timeout_ms: int = 12000
    graph_entity_llm_max_concurrency: int = 4
    graph_entity_llm_max_retries: int = 1
    graph_expand_alpha: float = 2.0
    graph_expand_max_candidates: int = 200
    graph_expand_author_keywords: list[str] = field(
        default_factory=lambda: [
            "author",
            "authors",
            "affiliation",
            "institute",
            "institution",
            "university",
            "corresponding",
            "email",
            "作者",
            "单位",
            "机构",
            "通讯作者",
            "邮箱",
        ]
    )
    graph_expand_reference_keywords: list[str] = field(
        default_factory=lambda: [
            "reference",
            "citation",
            "source",
            "appendix",
            "validate",
            "verification",
            "scale",
            "questionnaire",
            "引用",
            "出处",
            "参考文献",
            "验证",
            "量表",
        ]
    )
    rewrite_synonyms: dict[str, list[str]] = field(
        default_factory=lambda: {
            "citation": ["reference", "cited", "bibliography"],
            "reference": ["citation", "bibliography", "source"],
            "method": ["approach", "technique"],
            "dataset": ["corpus", "benchmark"],
            "evaluation": ["metric", "assessment"],
            "准确率": ["accuracy", "precision"],
            "召回率": ["recall"],
            "引用": ["reference", "citation"],
            "方法": ["method", "approach"],
            "实验": ["experiment", "evaluation"],
        }
    )
    rewrite_meta_patterns: list[str] = field(
        default_factory=lambda: [
            r"\bwhy (?:does|did)? .*?(?:lack|without|missing).*(?:evidence|proof)s?\b",
            r"\black of evidences?\b",
            r"\bnot enough evidences?\b",
            r"\bwhy (?:no|not)\b.*\b(answer|evidence)\b",
            r"为什么.*(?:没|没有).*(?:证据|回答|答全)",
            r"你没回答全",
            r"再找找",
            r"补充证据",
            r"没有证据",
            r"没找到证据",
            r"回答不完整",
            r"\bstill no proof\b",
            r"\bno proof\b",
            r"find more concrete components",
        ]
    )
    rewrite_meta_noise_terms: list[str] = field(
        default_factory=lambda: [
            "lack",
            "evidence",
            "evidences",
            "proof",
            "为什么",
            "没证据",
            "没有证据",
            "没回答全",
            "答全",
            "再找找",
        ]
    )


def _coerce_with_default(value: Any, default_value: Any) -> Any:
    if isinstance(default_value, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value) if value is not None else default_value
    if isinstance(default_value, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default_value
    if isinstance(default_value, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default_value
    return value if value is not None else default_value


def _merge_defaults(data: dict[str, Any]) -> PipelineConfig:
    defaults = PipelineConfig()
    kwargs: dict[str, Any] = {}
    defaults_dict = asdict(defaults)
    raw_embedding = data.get("embedding", {})
    if not isinstance(raw_embedding, dict):
        raw_embedding = {}
    raw_rerank = data.get("rerank", {})
    if not isinstance(raw_rerank, dict):
        raw_rerank = {}

    def _pick_stage_value(
        *,
        stage: str,
        field_key: str,
        legacy: dict[str, Any],
        legacy_key: str,
        default_value: Any,
    ) -> Any:
        prefixed_key = f"{stage}_{field_key}"
        if prefixed_key in data and data.get(prefixed_key) is not None:
            return _coerce_with_default(data.get(prefixed_key), default_value)
        if legacy_key in legacy and legacy.get(legacy_key) is not None:
            return _coerce_with_default(legacy.get(legacy_key), default_value)
        return default_value

    for key, default_value in defaults_dict.items():
        if key == "embedding":
            merged_embedding = {}
            for emb_key, emb_default in asdict(EmbeddingConfig()).items():
                if emb_key == "provider":
                    merged_embedding[emb_key] = _pick_stage_value(
                        stage="embedding",
                        field_key="provider",
                        legacy=raw_embedding,
                        legacy_key="provider",
                        default_value=emb_default,
                    )
                elif emb_key == "base_url":
                    merged_embedding[emb_key] = _pick_stage_value(
                        stage="embedding",
                        field_key="api_base",
                        legacy=raw_embedding,
                        legacy_key="base_url",
                        default_value=emb_default,
                    )
                elif emb_key == "model":
                    merged_embedding[emb_key] = _pick_stage_value(
                        stage="embedding",
                        field_key="model",
                        legacy=raw_embedding,
                        legacy_key="model",
                        default_value=emb_default,
                    )
                elif emb_key == "api_key_env":
                    merged_embedding[emb_key] = _pick_stage_value(
                        stage="embedding",
                        field_key="api_key_env",
                        legacy=raw_embedding,
                        legacy_key="api_key_env",
                        default_value=emb_default,
                    )
                else:
                    merged_embedding[emb_key] = _coerce_with_default(raw_embedding.get(emb_key), emb_default)
            kwargs[key] = EmbeddingConfig(**merged_embedding)
            continue
        if key == "rerank":
            merged_rerank = {}
            for rr_key, rr_default in asdict(RerankConfig()).items():
                if rr_key == "provider":
                    merged_rerank[rr_key] = _pick_stage_value(
                        stage="rerank",
                        field_key="provider",
                        legacy=raw_rerank,
                        legacy_key="provider",
                        default_value=rr_default,
                    )
                elif rr_key == "base_url":
                    merged_rerank[rr_key] = _pick_stage_value(
                        stage="rerank",
                        field_key="api_base",
                        legacy=raw_rerank,
                        legacy_key="base_url",
                        default_value=rr_default,
                    )
                elif rr_key == "model":
                    merged_rerank[rr_key] = _pick_stage_value(
                        stage="rerank",
                        field_key="model",
                        legacy=raw_rerank,
                        legacy_key="model",
                        default_value=rr_default,
                    )
                elif rr_key == "api_key_env":
                    merged_rerank[rr_key] = _pick_stage_value(
                        stage="rerank",
                        field_key="api_key_env",
                        legacy=raw_rerank,
                        legacy_key="api_key_env",
                        default_value=rr_default,
                    )
                else:
                    merged_rerank[rr_key] = _coerce_with_default(raw_rerank.get(rr_key), rr_default)
            kwargs[key] = RerankConfig(**merged_rerank)
            continue
        if key == "embedding_provider":
            kwargs[key] = _pick_stage_value(
                stage="embedding",
                field_key="provider",
                legacy=raw_embedding,
                legacy_key="provider",
                default_value=default_value,
            )
            continue
        if key == "embedding_model":
            kwargs[key] = _pick_stage_value(
                stage="embedding",
                field_key="model",
                legacy=raw_embedding,
                legacy_key="model",
                default_value=default_value,
            )
            continue
        if key == "embedding_api_base":
            kwargs[key] = _pick_stage_value(
                stage="embedding",
                field_key="api_base",
                legacy=raw_embedding,
                legacy_key="base_url",
                default_value=default_value,
            )
            continue
        if key == "embedding_api_key_env":
            kwargs[key] = _pick_stage_value(
                stage="embedding",
                field_key="api_key_env",
                legacy=raw_embedding,
                legacy_key="api_key_env",
                default_value=default_value,
            )
            continue
        if key == "rerank_provider":
            kwargs[key] = _pick_stage_value(
                stage="rerank",
                field_key="provider",
                legacy=raw_rerank,
                legacy_key="provider",
                default_value=default_value,
            )
            continue
        if key == "rerank_model":
            kwargs[key] = _pick_stage_value(
                stage="rerank",
                field_key="model",
                legacy=raw_rerank,
                legacy_key="model",
                default_value=default_value,
            )
            continue
        if key == "rerank_api_base":
            kwargs[key] = _pick_stage_value(
                stage="rerank",
                field_key="api_base",
                legacy=raw_rerank,
                legacy_key="base_url",
                default_value=default_value,
            )
            continue
        if key == "rerank_api_key_env":
            kwargs[key] = _pick_stage_value(
                stage="rerank",
                field_key="api_key_env",
                legacy=raw_rerank,
                legacy_key="api_key_env",
                default_value=default_value,
            )
            continue
        kwargs[key] = _coerce_with_default(data.get(key), default_value)
    return PipelineConfig(**kwargs)


def validate_config(config: PipelineConfig) -> tuple[PipelineConfig, list[str]]:
    warnings: list[str] = []
    validated = PipelineConfig(**{k: v for k, v in asdict(config).items() if k != "embedding"})
    if isinstance(config.embedding, EmbeddingConfig):
        validated.embedding = EmbeddingConfig(**asdict(config.embedding))
    elif isinstance(config.embedding, dict):
        validated.embedding = EmbeddingConfig(**{
            k: config.embedding.get(k, getattr(EmbeddingConfig(), k))
            for k in asdict(EmbeddingConfig()).keys()
        })
    else:
        validated.embedding = EmbeddingConfig()
    if isinstance(config.rerank, RerankConfig):
        validated.rerank = RerankConfig(**asdict(config.rerank))
    elif isinstance(config.rerank, dict):
        validated.rerank = RerankConfig(**{
            k: config.rerank.get(k, getattr(RerankConfig(), k))
            for k in asdict(RerankConfig()).keys()
        })
    else:
        validated.rerank = RerankConfig()
    defaults = PipelineConfig()

    if not 300 <= validated.chunk_size <= 500:
        warnings.append(
            f"Invalid chunk_size={validated.chunk_size}; fallback to {defaults.chunk_size} "
            "(must be between 300 and 500)."
        )
        validated.chunk_size = defaults.chunk_size

    if validated.style_control_max_turn_distance <= 0:
        warnings.append(
            "Invalid style_control_max_turn_distance="
            f"{validated.style_control_max_turn_distance}; fallback to "
            f"{defaults.style_control_max_turn_distance} (must be > 0)."
        )
        validated.style_control_max_turn_distance = defaults.style_control_max_turn_distance
    if validated.rewrite_arbitration_min_delta < 0:
        warnings.append(
            "Invalid rewrite_arbitration_min_delta="
            f"{validated.rewrite_arbitration_min_delta}; fallback to {defaults.rewrite_arbitration_min_delta}."
        )
        validated.rewrite_arbitration_min_delta = defaults.rewrite_arbitration_min_delta
    if validated.intent_control_min_confidence < 0 or validated.intent_control_min_confidence > 1:
        warnings.append(
            "Invalid intent_control_min_confidence="
            f"{validated.intent_control_min_confidence}; fallback to "
            f"{defaults.intent_control_min_confidence} (must satisfy 0 <= value <= 1)."
        )
        validated.intent_control_min_confidence = defaults.intent_control_min_confidence
    if validated.assistant_mode_clarify_limit <= 0:
        warnings.append(
            "Invalid assistant_mode_clarify_limit="
            f"{validated.assistant_mode_clarify_limit}; fallback to "
            f"{defaults.assistant_mode_clarify_limit} (must be > 0)."
        )
        validated.assistant_mode_clarify_limit = defaults.assistant_mode_clarify_limit
    if validated.session_store_backend not in {"redis", "file"}:
        warnings.append(
            "Invalid session_store_backend="
            f"{validated.session_store_backend}; fallback to {defaults.session_store_backend}."
        )
        validated.session_store_backend = defaults.session_store_backend
    if not isinstance(validated.session_redis_url, str) or not validated.session_redis_url.strip():
        warnings.append("Invalid session_redis_url; fallback to defaults.")
        validated.session_redis_url = defaults.session_redis_url
    if validated.session_redis_ttl_sec < 0:
        warnings.append(
            "Invalid session_redis_ttl_sec="
            f"{validated.session_redis_ttl_sec}; fallback to {defaults.session_redis_ttl_sec} (must be >= 0)."
        )
        validated.session_redis_ttl_sec = defaults.session_redis_ttl_sec
    if not isinstance(validated.session_redis_key_prefix, str) or not validated.session_redis_key_prefix.strip():
        warnings.append("Invalid session_redis_key_prefix; fallback to defaults.")
        validated.session_redis_key_prefix = defaults.session_redis_key_prefix
    if validated.session_recent_turns_window <= 0:
        warnings.append(
            "Invalid session_recent_turns_window="
            f"{validated.session_recent_turns_window}; fallback to {defaults.session_recent_turns_window} (must be > 0)."
        )
        validated.session_recent_turns_window = defaults.session_recent_turns_window

    if validated.overlap < 0 or validated.overlap >= validated.chunk_size:
        warnings.append(
            f"Invalid overlap={validated.overlap}; fallback to {defaults.overlap} "
            "(must satisfy 0 <= overlap < chunk_size)."
        )
        validated.overlap = defaults.overlap
        if validated.overlap >= validated.chunk_size:
            validated.chunk_size = defaults.chunk_size

    if validated.marker_timeout_sec <= 0:
        warnings.append(
            f"Invalid marker_timeout_sec={validated.marker_timeout_sec}; "
            f"fallback to {defaults.marker_timeout_sec} (must be > 0)."
        )
        validated.marker_timeout_sec = defaults.marker_timeout_sec

    if validated.title_confidence_threshold < 0 or validated.title_confidence_threshold > 1:
        warnings.append(
            f"Invalid title_confidence_threshold={validated.title_confidence_threshold}; "
            f"fallback to {defaults.title_confidence_threshold} (must satisfy 0 <= value <= 1)."
        )
        validated.title_confidence_threshold = defaults.title_confidence_threshold

    if not isinstance(validated.title_blacklist_patterns, list):
        warnings.append("Invalid title_blacklist_patterns; fallback to defaults.")
        validated.title_blacklist_patterns = list(defaults.title_blacklist_patterns)
    else:
        normalized_patterns = [str(item).strip() for item in validated.title_blacklist_patterns if str(item).strip()]
        if not normalized_patterns:
            warnings.append("Empty title_blacklist_patterns; fallback to defaults.")
            normalized_patterns = list(defaults.title_blacklist_patterns)
        validated.title_blacklist_patterns = normalized_patterns

    if validated.table_list_downweight <= 0 or validated.table_list_downweight > 1:
        warnings.append(
            f"Invalid table_list_downweight={validated.table_list_downweight}; "
            f"fallback to {defaults.table_list_downweight} (must satisfy 0 < value <= 1)."
        )
        validated.table_list_downweight = defaults.table_list_downweight

    if validated.front_matter_downweight <= 0 or validated.front_matter_downweight > 1:
        warnings.append(
            f"Invalid front_matter_downweight={validated.front_matter_downweight}; "
            f"fallback to {defaults.front_matter_downweight} (must satisfy 0 < value <= 1)."
        )
        validated.front_matter_downweight = defaults.front_matter_downweight

    if validated.reference_downweight <= 0 or validated.reference_downweight > 1:
        warnings.append(
            f"Invalid reference_downweight={validated.reference_downweight}; "
            f"fallback to {defaults.reference_downweight} (must satisfy 0 < value <= 1)."
        )
        validated.reference_downweight = defaults.reference_downweight

    if validated.rewrite_max_keywords <= 0:
        warnings.append(
            f"Invalid rewrite_max_keywords={validated.rewrite_max_keywords}; "
            f"fallback to {defaults.rewrite_max_keywords} (must be > 0)."
        )
        validated.rewrite_max_keywords = defaults.rewrite_max_keywords
    if validated.rewrite_entity_preservation_min_ratio < 0 or validated.rewrite_entity_preservation_min_ratio > 1:
        warnings.append(
            "Invalid rewrite_entity_preservation_min_ratio="
            f"{validated.rewrite_entity_preservation_min_ratio}; fallback to "
            f"{defaults.rewrite_entity_preservation_min_ratio} (must satisfy 0 <= value <= 1)."
        )
        validated.rewrite_entity_preservation_min_ratio = defaults.rewrite_entity_preservation_min_ratio

    if not isinstance(validated.rewrite_llm_provider, str) or not validated.rewrite_llm_provider.strip():
        warnings.append("Invalid rewrite_llm_provider; fallback to defaults.")
        validated.rewrite_llm_provider = defaults.rewrite_llm_provider
    if not isinstance(validated.rewrite_llm_model, str) or not validated.rewrite_llm_model.strip():
        warnings.append("Invalid rewrite_llm_model; fallback to defaults.")
        validated.rewrite_llm_model = defaults.rewrite_llm_model
    if not isinstance(validated.rewrite_llm_api_base, str) or not validated.rewrite_llm_api_base.strip():
        warnings.append("Invalid rewrite_llm_api_base; fallback to defaults.")
        validated.rewrite_llm_api_base = defaults.rewrite_llm_api_base
    if not isinstance(validated.rewrite_llm_api_key_env, str) or not validated.rewrite_llm_api_key_env.strip():
        warnings.append("Invalid rewrite_llm_api_key_env; fallback to defaults.")
        validated.rewrite_llm_api_key_env = defaults.rewrite_llm_api_key_env
    if not isinstance(validated.rewrite_llm_fallback_provider, str) or not validated.rewrite_llm_fallback_provider.strip():
        warnings.append("Invalid rewrite_llm_fallback_provider; fallback to defaults.")
        validated.rewrite_llm_fallback_provider = defaults.rewrite_llm_fallback_provider
    if not isinstance(validated.rewrite_llm_fallback_model, str):
        warnings.append("Invalid rewrite_llm_fallback_model; fallback to defaults.")
        validated.rewrite_llm_fallback_model = defaults.rewrite_llm_fallback_model
    if not isinstance(validated.rewrite_llm_fallback_api_base, str):
        warnings.append("Invalid rewrite_llm_fallback_api_base; fallback to defaults.")
        validated.rewrite_llm_fallback_api_base = defaults.rewrite_llm_fallback_api_base
    if not isinstance(validated.rewrite_llm_fallback_api_key_env, str):
        warnings.append("Invalid rewrite_llm_fallback_api_key_env; fallback to defaults.")
        validated.rewrite_llm_fallback_api_key_env = defaults.rewrite_llm_fallback_api_key_env
    if not isinstance(validated.answer_llm_provider, str) or not validated.answer_llm_provider.strip():
        warnings.append("Invalid answer_llm_provider; fallback to defaults.")
        validated.answer_llm_provider = defaults.answer_llm_provider
    if not isinstance(validated.answer_llm_model, str) or not validated.answer_llm_model.strip():
        warnings.append("Invalid answer_llm_model; fallback to defaults.")
        validated.answer_llm_model = defaults.answer_llm_model
    if not isinstance(validated.answer_llm_api_base, str) or not validated.answer_llm_api_base.strip():
        warnings.append("Invalid answer_llm_api_base; fallback to defaults.")
        validated.answer_llm_api_base = defaults.answer_llm_api_base
    if not isinstance(validated.answer_llm_api_key_env, str) or not validated.answer_llm_api_key_env.strip():
        warnings.append("Invalid answer_llm_api_key_env; fallback to defaults.")
        validated.answer_llm_api_key_env = defaults.answer_llm_api_key_env
    if not isinstance(validated.answer_llm_fallback_provider, str) or not validated.answer_llm_fallback_provider.strip():
        warnings.append("Invalid answer_llm_fallback_provider; fallback to defaults.")
        validated.answer_llm_fallback_provider = defaults.answer_llm_fallback_provider
    if not isinstance(validated.answer_llm_fallback_model, str):
        warnings.append("Invalid answer_llm_fallback_model; fallback to defaults.")
        validated.answer_llm_fallback_model = defaults.answer_llm_fallback_model
    if not isinstance(validated.answer_llm_fallback_api_base, str):
        warnings.append("Invalid answer_llm_fallback_api_base; fallback to defaults.")
        validated.answer_llm_fallback_api_base = defaults.answer_llm_fallback_api_base
    if not isinstance(validated.answer_llm_fallback_api_key_env, str):
        warnings.append("Invalid answer_llm_fallback_api_key_env; fallback to defaults.")
        validated.answer_llm_fallback_api_key_env = defaults.answer_llm_fallback_api_key_env
    if not isinstance(validated.embedding_provider, str) or not validated.embedding_provider.strip():
        warnings.append("Invalid embedding_provider; fallback to defaults.")
        validated.embedding_provider = defaults.embedding_provider
    if not isinstance(validated.embedding_model, str) or not validated.embedding_model.strip():
        warnings.append("Invalid embedding_model; fallback to defaults.")
        validated.embedding_model = defaults.embedding_model
    if not isinstance(validated.embedding_api_base, str) or not validated.embedding_api_base.strip():
        warnings.append("Invalid embedding_api_base; fallback to defaults.")
        validated.embedding_api_base = defaults.embedding_api_base
    if not isinstance(validated.embedding_api_key_env, str) or not validated.embedding_api_key_env.strip():
        warnings.append("Invalid embedding_api_key_env; fallback to defaults.")
        validated.embedding_api_key_env = defaults.embedding_api_key_env
    if not isinstance(validated.embedding_fallback_provider, str) or not validated.embedding_fallback_provider.strip():
        warnings.append("Invalid embedding_fallback_provider; fallback to defaults.")
        validated.embedding_fallback_provider = defaults.embedding_fallback_provider
    if not isinstance(validated.embedding_fallback_model, str):
        warnings.append("Invalid embedding_fallback_model; fallback to defaults.")
        validated.embedding_fallback_model = defaults.embedding_fallback_model
    if not isinstance(validated.embedding_fallback_api_base, str):
        warnings.append("Invalid embedding_fallback_api_base; fallback to defaults.")
        validated.embedding_fallback_api_base = defaults.embedding_fallback_api_base
    if not isinstance(validated.embedding_fallback_api_key_env, str):
        warnings.append("Invalid embedding_fallback_api_key_env; fallback to defaults.")
        validated.embedding_fallback_api_key_env = defaults.embedding_fallback_api_key_env
    if not isinstance(validated.rerank_provider, str) or not validated.rerank_provider.strip():
        warnings.append("Invalid rerank_provider; fallback to defaults.")
        validated.rerank_provider = defaults.rerank_provider
    if not isinstance(validated.rerank_model, str) or not validated.rerank_model.strip():
        warnings.append("Invalid rerank_model; fallback to defaults.")
        validated.rerank_model = defaults.rerank_model
    if not isinstance(validated.rerank_api_base, str) or not validated.rerank_api_base.strip():
        warnings.append("Invalid rerank_api_base; fallback to defaults.")
        validated.rerank_api_base = defaults.rerank_api_base
    if not isinstance(validated.rerank_api_key_env, str) or not validated.rerank_api_key_env.strip():
        warnings.append("Invalid rerank_api_key_env; fallback to defaults.")
        validated.rerank_api_key_env = defaults.rerank_api_key_env
    if not isinstance(validated.rerank_fallback_provider, str) or not validated.rerank_fallback_provider.strip():
        warnings.append("Invalid rerank_fallback_provider; fallback to defaults.")
        validated.rerank_fallback_provider = defaults.rerank_fallback_provider
    if not isinstance(validated.rerank_fallback_model, str):
        warnings.append("Invalid rerank_fallback_model; fallback to defaults.")
        validated.rerank_fallback_model = defaults.rerank_fallback_model
    if not isinstance(validated.rerank_fallback_api_base, str):
        warnings.append("Invalid rerank_fallback_api_base; fallback to defaults.")
        validated.rerank_fallback_api_base = defaults.rerank_fallback_api_base
    if not isinstance(validated.rerank_fallback_api_key_env, str):
        warnings.append("Invalid rerank_fallback_api_key_env; fallback to defaults.")
        validated.rerank_fallback_api_key_env = defaults.rerank_fallback_api_key_env
    if validated.llm_router_retry < 0:
        warnings.append(
            f"Invalid llm_router_retry={validated.llm_router_retry}; "
            f"fallback to {defaults.llm_router_retry} (must be >= 0)."
        )
        validated.llm_router_retry = defaults.llm_router_retry
    if validated.llm_router_cooldown_sec < 0:
        warnings.append(
            f"Invalid llm_router_cooldown_sec={validated.llm_router_cooldown_sec}; "
            f"fallback to {defaults.llm_router_cooldown_sec} (must be >= 0)."
        )
        validated.llm_router_cooldown_sec = defaults.llm_router_cooldown_sec
    if validated.llm_router_failure_threshold <= 0:
        warnings.append(
            f"Invalid llm_router_failure_threshold={validated.llm_router_failure_threshold}; "
            f"fallback to {defaults.llm_router_failure_threshold} (must be > 0)."
        )
        validated.llm_router_failure_threshold = defaults.llm_router_failure_threshold
    if validated.llm_timeout_ms <= 0:
        warnings.append(
            f"Invalid llm_timeout_ms={validated.llm_timeout_ms}; "
            f"fallback to {defaults.llm_timeout_ms} (must be > 0)."
        )
        validated.llm_timeout_ms = defaults.llm_timeout_ms
    if validated.answer_llm_timeout_ms <= 0:
        warnings.append(
            f"Invalid answer_llm_timeout_ms={validated.answer_llm_timeout_ms}; "
            f"fallback to {defaults.answer_llm_timeout_ms} (must be > 0)."
        )
        validated.answer_llm_timeout_ms = defaults.answer_llm_timeout_ms
    if validated.llm_max_retries < 0:
        warnings.append(
            f"Invalid llm_max_retries={validated.llm_max_retries}; "
            f"fallback to {defaults.llm_max_retries} (must be >= 0)."
        )
        validated.llm_max_retries = defaults.llm_max_retries
    if validated.max_context_tokens <= 0:
        warnings.append(
            f"Invalid max_context_tokens={validated.max_context_tokens}; "
            f"fallback to {defaults.max_context_tokens} (must be > 0)."
        )
        validated.max_context_tokens = defaults.max_context_tokens
    if validated.sufficiency_topic_match_threshold < 0 or validated.sufficiency_topic_match_threshold > 1:
        warnings.append(
            f"Invalid sufficiency_topic_match_threshold={validated.sufficiency_topic_match_threshold}; "
            f"fallback to {defaults.sufficiency_topic_match_threshold} (must satisfy 0 <= value <= 1)."
        )
        validated.sufficiency_topic_match_threshold = defaults.sufficiency_topic_match_threshold
    if validated.sufficiency_semantic_policy not in {"strict", "balanced", "explore"}:
        warnings.append(
            "Invalid sufficiency_semantic_policy="
            f"{validated.sufficiency_semantic_policy}; fallback to {defaults.sufficiency_semantic_policy}."
        )
        validated.sufficiency_semantic_policy = defaults.sufficiency_semantic_policy
    for field_name in (
        "sufficiency_semantic_threshold_strict",
        "sufficiency_semantic_threshold_balanced",
        "sufficiency_semantic_threshold_explore",
    ):
        val = float(getattr(validated, field_name))
        default_val = float(getattr(defaults, field_name))
        if val < 0 or val > 1:
            warnings.append(
                f"Invalid {field_name}={val}; fallback to {default_val} "
                "(must satisfy 0 <= value <= 1)."
            )
            setattr(validated, field_name, default_val)
    if validated.sufficiency_key_element_min_coverage < 0 or validated.sufficiency_key_element_min_coverage > 1:
        warnings.append(
            f"Invalid sufficiency_key_element_min_coverage={validated.sufficiency_key_element_min_coverage}; "
            f"fallback to {defaults.sufficiency_key_element_min_coverage} (must satisfy 0 <= value <= 1)."
        )
        validated.sufficiency_key_element_min_coverage = defaults.sufficiency_key_element_min_coverage
    if not isinstance(validated.sufficiency_judge_llm_provider, str) or not validated.sufficiency_judge_llm_provider.strip():
        warnings.append("Invalid sufficiency_judge_llm_provider; fallback to defaults.")
        validated.sufficiency_judge_llm_provider = defaults.sufficiency_judge_llm_provider
    if not isinstance(validated.sufficiency_judge_llm_model, str) or not validated.sufficiency_judge_llm_model.strip():
        warnings.append("Invalid sufficiency_judge_llm_model; fallback to defaults.")
        validated.sufficiency_judge_llm_model = defaults.sufficiency_judge_llm_model
    if not isinstance(validated.sufficiency_judge_llm_api_base, str) or not validated.sufficiency_judge_llm_api_base.strip():
        warnings.append("Invalid sufficiency_judge_llm_api_base; fallback to defaults.")
        validated.sufficiency_judge_llm_api_base = defaults.sufficiency_judge_llm_api_base
    if not isinstance(validated.sufficiency_judge_llm_api_key_env, str) or not validated.sufficiency_judge_llm_api_key_env.strip():
        warnings.append("Invalid sufficiency_judge_llm_api_key_env; fallback to defaults.")
        validated.sufficiency_judge_llm_api_key_env = defaults.sufficiency_judge_llm_api_key_env
    if validated.sufficiency_judge_llm_timeout_ms <= 0:
        warnings.append(
            f"Invalid sufficiency_judge_llm_timeout_ms={validated.sufficiency_judge_llm_timeout_ms}; "
            f"fallback to {defaults.sufficiency_judge_llm_timeout_ms} (must be > 0)."
        )
        validated.sufficiency_judge_llm_timeout_ms = defaults.sufficiency_judge_llm_timeout_ms

    if validated.dense_backend not in {"embedding", "tfidf"}:
        warnings.append(
            f"Invalid dense_backend={validated.dense_backend}; "
            f"fallback to {defaults.dense_backend} (must be embedding|tfidf)."
        )
        validated.dense_backend = defaults.dense_backend

    rr = validated.rerank
    rr_defaults = defaults.rerank
    rr.provider = str(validated.rerank_provider).strip() or rr.provider
    rr.base_url = str(validated.rerank_api_base).strip() or rr.base_url
    rr.model = str(validated.rerank_model).strip() or rr.model
    rr.api_key_env = str(validated.rerank_api_key_env).strip() or rr.api_key_env
    if not isinstance(rr.provider, str) or not rr.provider.strip():
        warnings.append("Invalid rerank.provider; fallback to defaults.")
        rr.provider = rr_defaults.provider
    if not isinstance(rr.base_url, str) or not rr.base_url.strip():
        warnings.append("Invalid rerank.base_url; fallback to defaults.")
        rr.base_url = rr_defaults.base_url
    if not isinstance(rr.model, str) or not rr.model.strip():
        warnings.append("Invalid rerank.model; fallback to defaults.")
        rr.model = rr_defaults.model
    if not isinstance(rr.api_key_env, str) or not rr.api_key_env.strip():
        warnings.append("Invalid rerank.api_key_env; fallback to defaults.")
        rr.api_key_env = rr_defaults.api_key_env
    if rr.top_n <= 0:
        warnings.append(
            f"Invalid rerank.top_n={rr.top_n}; fallback to {rr_defaults.top_n} (must be > 0)."
        )
        rr.top_n = rr_defaults.top_n
    if rr.timeout_ms <= 0:
        warnings.append(
            f"Invalid rerank.timeout_ms={rr.timeout_ms}; fallback to {rr_defaults.timeout_ms} (must be > 0)."
        )
        rr.timeout_ms = rr_defaults.timeout_ms
    if rr.max_retries < 0:
        warnings.append(
            f"Invalid rerank.max_retries={rr.max_retries}; fallback to {rr_defaults.max_retries} (must be >= 0)."
        )
        rr.max_retries = rr_defaults.max_retries
    validated.rerank = rr

    emb = validated.embedding
    emb_defaults = defaults.embedding
    emb.provider = str(validated.embedding_provider).strip() or emb.provider
    emb.base_url = str(validated.embedding_api_base).strip() or emb.base_url
    emb.model = str(validated.embedding_model).strip() or emb.model
    emb.api_key_env = str(validated.embedding_api_key_env).strip() or emb.api_key_env
    if emb.batch_size <= 0:
        warnings.append(
            f"Invalid embedding.batch_size={emb.batch_size}; "
            f"fallback to {emb_defaults.batch_size} (must be > 0)."
        )
        emb.batch_size = emb_defaults.batch_size
    if not isinstance(emb.provider, str) or not emb.provider.strip():
        warnings.append("Invalid embedding.provider; fallback to defaults.")
        emb.provider = emb_defaults.provider
    if not isinstance(emb.base_url, str) or not emb.base_url.strip():
        warnings.append("Invalid embedding.base_url; fallback to defaults.")
        emb.base_url = emb_defaults.base_url
    if not isinstance(emb.model, str) or not emb.model.strip():
        warnings.append("Invalid embedding.model; fallback to defaults.")
        emb.model = emb_defaults.model
    if not isinstance(emb.api_key_env, str) or not emb.api_key_env.strip():
        warnings.append("Invalid embedding.api_key_env; fallback to defaults.")
        emb.api_key_env = emb_defaults.api_key_env
    if not isinstance(emb.cache_path, str) or not emb.cache_path.strip():
        warnings.append("Invalid embedding.cache_path; fallback to defaults.")
        emb.cache_path = emb_defaults.cache_path
    if not isinstance(emb.failure_log_path, str) or not emb.failure_log_path.strip():
        warnings.append("Invalid embedding.failure_log_path; fallback to defaults.")
        emb.failure_log_path = emb_defaults.failure_log_path
    if emb.max_requests_per_minute <= 0:
        warnings.append(
            f"Invalid embedding.max_requests_per_minute={emb.max_requests_per_minute}; "
            f"fallback to {emb_defaults.max_requests_per_minute} (must be > 0)."
        )
        emb.max_requests_per_minute = emb_defaults.max_requests_per_minute
    if emb.max_concurrent_requests <= 0:
        warnings.append(
            f"Invalid embedding.max_concurrent_requests={emb.max_concurrent_requests}; "
            f"fallback to {emb_defaults.max_concurrent_requests} (must be > 0)."
        )
        emb.max_concurrent_requests = emb_defaults.max_concurrent_requests
    if emb.max_retries < 0:
        warnings.append(
            f"Invalid embedding.max_retries={emb.max_retries}; "
            f"fallback to {emb_defaults.max_retries} (must be >= 0)."
        )
        emb.max_retries = emb_defaults.max_retries
    if emb.backoff_base_ms <= 0:
        warnings.append(
            f"Invalid embedding.backoff_base_ms={emb.backoff_base_ms}; "
            f"fallback to {emb_defaults.backoff_base_ms} (must be > 0)."
        )
        emb.backoff_base_ms = emb_defaults.backoff_base_ms
    if emb.backoff_max_ms <= 0:
        warnings.append(
            f"Invalid embedding.backoff_max_ms={emb.backoff_max_ms}; "
            f"fallback to {emb_defaults.backoff_max_ms} (must be > 0)."
        )
        emb.backoff_max_ms = emb_defaults.backoff_max_ms
    if emb.backoff_max_ms < emb.backoff_base_ms:
        warnings.append(
            "Invalid embedding backoff range; fallback to defaults "
            f"({emb_defaults.backoff_base_ms}-{emb_defaults.backoff_max_ms} ms)."
        )
        emb.backoff_base_ms = emb_defaults.backoff_base_ms
        emb.backoff_max_ms = emb_defaults.backoff_max_ms
    if emb.max_tokens_per_chunk <= 0:
        warnings.append(
            f"Invalid embedding.max_tokens_per_chunk={emb.max_tokens_per_chunk}; "
            f"fallback to {emb_defaults.max_tokens_per_chunk} (must be > 0)."
        )
        emb.max_tokens_per_chunk = emb_defaults.max_tokens_per_chunk
    if emb.over_limit_strategy not in {"truncate", "split"}:
        warnings.append(
            f"Invalid embedding.over_limit_strategy={emb.over_limit_strategy}; "
            f"fallback to {emb_defaults.over_limit_strategy} (must be truncate|split)."
        )
        emb.over_limit_strategy = emb_defaults.over_limit_strategy
    if emb.max_failed_chunk_ids <= 0:
        warnings.append(
            f"Invalid embedding.max_failed_chunk_ids={emb.max_failed_chunk_ids}; "
            f"fallback to {emb_defaults.max_failed_chunk_ids} (must be > 0)."
        )
        emb.max_failed_chunk_ids = emb_defaults.max_failed_chunk_ids
    if emb.max_skipped_chunk_ids <= 0:
        warnings.append(
            f"Invalid embedding.max_skipped_chunk_ids={emb.max_skipped_chunk_ids}; "
            f"fallback to {emb_defaults.max_skipped_chunk_ids} (must be > 0)."
        )
        emb.max_skipped_chunk_ids = emb_defaults.max_skipped_chunk_ids
    validated.embedding = emb

    if validated.graph_expand_alpha < 0:
        warnings.append(
            f"Invalid graph_expand_alpha={validated.graph_expand_alpha}; "
            f"fallback to {defaults.graph_expand_alpha} (must be >= 0)."
        )
        validated.graph_expand_alpha = defaults.graph_expand_alpha

    if validated.graph_expand_max_candidates <= 0:
        warnings.append(
            f"Invalid graph_expand_max_candidates={validated.graph_expand_max_candidates}; "
            f"fallback to {defaults.graph_expand_max_candidates} (must be > 0)."
        )
        validated.graph_expand_max_candidates = defaults.graph_expand_max_candidates

    if not isinstance(validated.graph_path, str) or not validated.graph_path.strip():
        warnings.append(f"Invalid graph_path={validated.graph_path}; fallback to {defaults.graph_path}.")
        validated.graph_path = defaults.graph_path

    if not isinstance(validated.graph_entity_llm_provider, str) or not validated.graph_entity_llm_provider.strip():
        warnings.append("Invalid graph_entity_llm_provider; fallback to defaults.")
        validated.graph_entity_llm_provider = defaults.graph_entity_llm_provider
    if not isinstance(validated.graph_entity_llm_base_url, str) or not validated.graph_entity_llm_base_url.strip():
        warnings.append("Invalid graph_entity_llm_base_url; fallback to defaults.")
        validated.graph_entity_llm_base_url = defaults.graph_entity_llm_base_url
    if not isinstance(validated.graph_entity_llm_api_key_env, str) or not validated.graph_entity_llm_api_key_env.strip():
        warnings.append("Invalid graph_entity_llm_api_key_env; fallback to defaults.")
        validated.graph_entity_llm_api_key_env = defaults.graph_entity_llm_api_key_env
    if not isinstance(validated.graph_entity_llm_model, str) or not validated.graph_entity_llm_model.strip():
        warnings.append("Invalid graph_entity_llm_model; fallback to defaults.")
        validated.graph_entity_llm_model = defaults.graph_entity_llm_model
    if validated.graph_entity_llm_timeout_ms <= 0:
        warnings.append(
            f"Invalid graph_entity_llm_timeout_ms={validated.graph_entity_llm_timeout_ms}; "
            f"fallback to {defaults.graph_entity_llm_timeout_ms} (must be > 0)."
        )
        validated.graph_entity_llm_timeout_ms = defaults.graph_entity_llm_timeout_ms
    if validated.graph_entity_llm_max_concurrency <= 0:
        warnings.append(
            f"Invalid graph_entity_llm_max_concurrency={validated.graph_entity_llm_max_concurrency}; "
            f"fallback to {defaults.graph_entity_llm_max_concurrency} (must be > 0)."
        )
        validated.graph_entity_llm_max_concurrency = defaults.graph_entity_llm_max_concurrency
    if validated.graph_entity_llm_max_retries < 0:
        warnings.append(
            f"Invalid graph_entity_llm_max_retries={validated.graph_entity_llm_max_retries}; "
            f"fallback to {defaults.graph_entity_llm_max_retries} (must be >= 0)."
        )
        validated.graph_entity_llm_max_retries = defaults.graph_entity_llm_max_retries

    if not isinstance(validated.graph_expand_author_keywords, list) or not validated.graph_expand_author_keywords:
        warnings.append("Invalid graph_expand_author_keywords; fallback to defaults.")
        validated.graph_expand_author_keywords = defaults.graph_expand_author_keywords
    else:
        validated.graph_expand_author_keywords = [str(x).strip() for x in validated.graph_expand_author_keywords if str(x).strip()]
        if not validated.graph_expand_author_keywords:
            validated.graph_expand_author_keywords = defaults.graph_expand_author_keywords

    if not isinstance(validated.graph_expand_reference_keywords, list) or not validated.graph_expand_reference_keywords:
        warnings.append("Invalid graph_expand_reference_keywords; fallback to defaults.")
        validated.graph_expand_reference_keywords = defaults.graph_expand_reference_keywords
    else:
        validated.graph_expand_reference_keywords = [
            str(x).strip() for x in validated.graph_expand_reference_keywords if str(x).strip()
        ]
        if not validated.graph_expand_reference_keywords:
            validated.graph_expand_reference_keywords = defaults.graph_expand_reference_keywords

    if not isinstance(validated.rewrite_synonyms, dict):
        warnings.append("Invalid rewrite_synonyms; fallback to defaults (must be mapping).")
        validated.rewrite_synonyms = defaults.rewrite_synonyms
    else:
        normalized: dict[str, list[str]] = {}
        for key, val in validated.rewrite_synonyms.items():
            if not isinstance(key, str):
                continue
            if isinstance(val, list):
                normalized[key] = [str(v) for v in val if str(v).strip()]
            elif isinstance(val, str) and val.strip():
                normalized[key] = [val.strip()]
        validated.rewrite_synonyms = normalized or defaults.rewrite_synonyms

    if not isinstance(validated.rewrite_meta_patterns, list) or not validated.rewrite_meta_patterns:
        warnings.append("Invalid rewrite_meta_patterns; fallback to defaults (must be non-empty list).")
        validated.rewrite_meta_patterns = defaults.rewrite_meta_patterns
    else:
        validated.rewrite_meta_patterns = [str(x).strip() for x in validated.rewrite_meta_patterns if str(x).strip()]
        if not validated.rewrite_meta_patterns:
            warnings.append("Invalid rewrite_meta_patterns; fallback to defaults (must contain valid strings).")
            validated.rewrite_meta_patterns = defaults.rewrite_meta_patterns

    if not isinstance(validated.rewrite_meta_noise_terms, list):
        warnings.append("Invalid rewrite_meta_noise_terms; fallback to defaults (must be list).")
        validated.rewrite_meta_noise_terms = defaults.rewrite_meta_noise_terms
    else:
        validated.rewrite_meta_noise_terms = [
            str(x).strip() for x in validated.rewrite_meta_noise_terms if str(x).strip()
        ] or defaults.rewrite_meta_noise_terms

    required_envs: set[str] = set()
    if validated.rewrite_use_llm:
        required_envs.add(validated.rewrite_llm_api_key_env)
        if validated.rewrite_llm_fallback_model:
            required_envs.add(validated.rewrite_llm_fallback_api_key_env or validated.rewrite_llm_api_key_env)
    if validated.answer_use_llm:
        required_envs.add(validated.answer_llm_api_key_env)
        if validated.answer_llm_fallback_model:
            required_envs.add(validated.answer_llm_fallback_api_key_env or validated.answer_llm_api_key_env)
    missing_envs = sorted(env for env in required_envs if env and not os.getenv(env))
    if missing_envs:
        warnings.append(
            "LLM route API key env missing while LLM path is enabled: "
            + ", ".join(missing_envs)
            + "; runtime will fallback to rules/template."
        )

    return validated, warnings


def load_and_validate_config(path: str | Path = DEFAULT_CONFIG_PATH) -> tuple[PipelineConfig, list[str]]:
    warnings: list[str] = []
    cfg_path = Path(path)
    if not cfg_path.exists():
        warnings.append(f"Config file not found: {cfg_path}. Using defaults.")
        return PipelineConfig(), warnings

    try:
        raw_data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"Failed to parse YAML config {cfg_path}: {exc}. Using defaults.")
        return PipelineConfig(), warnings

    if raw_data is None:
        raw_data = {}
    if not isinstance(raw_data, dict):
        warnings.append(f"Config root must be a mapping in {cfg_path}. Using defaults.")
        return PipelineConfig(), warnings

    merged = _merge_defaults(raw_data)
    runtime_cfg, runtime_err = load_runtime_llm_config()
    if runtime_err:
        warnings.append(f"Runtime LLM config ignored: {runtime_err}. Falling back to static config.")
    elif runtime_cfg is not None:
        answer_env = f"{RUNTIME_LLM_API_KEY_ENV}_ANSWER"
        embedding_env = f"{RUNTIME_LLM_API_KEY_ENV}_EMBEDDING"
        rerank_env = f"{RUNTIME_LLM_API_KEY_ENV}_RERANK"
        rewrite_env = f"{RUNTIME_LLM_API_KEY_ENV}_REWRITE"
        graph_entity_env = f"{RUNTIME_LLM_API_KEY_ENV}_GRAPH_ENTITY"
        os.environ[answer_env] = runtime_cfg.answer.api_key
        os.environ[embedding_env] = runtime_cfg.embedding.api_key
        os.environ[rerank_env] = runtime_cfg.rerank.api_key
        os.environ[rewrite_env] = runtime_cfg.rewrite.api_key
        os.environ[graph_entity_env] = runtime_cfg.graph_entity.api_key

        merged.answer_llm_provider = runtime_cfg.answer.provider
        merged.answer_llm_api_base = runtime_cfg.answer.api_base
        merged.answer_llm_model = runtime_cfg.answer.model
        merged.answer_llm_api_key_env = answer_env

        merged.embedding_provider = runtime_cfg.embedding.provider
        merged.embedding_api_base = runtime_cfg.embedding.api_base
        merged.embedding_model = runtime_cfg.embedding.model
        merged.embedding_api_key_env = embedding_env

        merged.rerank_provider = runtime_cfg.rerank.provider
        merged.rerank_api_base = runtime_cfg.rerank.api_base
        merged.rerank_model = runtime_cfg.rerank.model
        merged.rerank_api_key_env = rerank_env

        merged.rewrite_llm_provider = runtime_cfg.rewrite.provider
        merged.rewrite_llm_api_base = runtime_cfg.rewrite.api_base
        merged.rewrite_llm_model = runtime_cfg.rewrite.model
        merged.rewrite_llm_api_key_env = rewrite_env

        merged.graph_entity_llm_provider = runtime_cfg.graph_entity.provider
        merged.graph_entity_llm_base_url = runtime_cfg.graph_entity.api_base
        merged.graph_entity_llm_api_key_env = graph_entity_env
        merged.graph_entity_llm_model = runtime_cfg.graph_entity.model

    validated, rule_warnings = validate_config(merged)
    warnings.extend(rule_warnings)
    return validated, warnings


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> PipelineConfig:
    config, _ = load_and_validate_config(path)
    return config
