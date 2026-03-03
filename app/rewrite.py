from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import PipelineConfig
from app.llm_diagnostics import build_llm_diagnostics
from app.llm_client import call_chat_completion
from app.llm_routing import build_stage_policy, classify_error_category

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:-[0-9]+)?\b")
METRIC_RE = re.compile(r"\b(?:F1|BLEU|ROUGE|AUC|mAP|Top-?1|Top-?5|accuracy|precision|recall)\b", re.IGNORECASE)
FORMULA_RE = re.compile(r"[A-Za-z]+\s*[=<>]\s*[-+*/A-Za-z0-9_.]+")
EN_STOPWORDS = {
    "what",
    "how",
    "main",
    "contribution",
    "paper",
    "work",
    "authors",
    "study",
}
ZH_STOPWORDS = {"什么", "怎么", "主要", "贡献", "作者", "本文"}

EN_FILLER_PATTERNS = [
    r"^\s*(can you|could you|would you|please)\b",
    r"\b(can you|could you|would you|please)\b",
    r"\bhelp me\b",
    r"\bI want to know\b",
    r"\bwhat is\b",
    r"\bhow can I\b",
]
ZH_FILLER_PATTERNS = [
    r"请问",
    r"能不能",
    r"帮我",
    r"我想知道",
    r"是什么",
]
DEFAULT_META_PATTERNS = [
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
DEFAULT_META_NOISE_TERMS = {
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
}
FACT_FOCUS_TERMS = [
    "detailed architecture",
    "internal components",
    "mechanism",
    "experiment setup",
    "metrics definition",
]
FACT_FOCUS_TERMS_ZH = ["详细架构", "内部组件", "机制", "实验设置", "指标定义"]
CONTROL_INTENT_TYPES = {"style_control", "format_control", "continuation_control"}
OPEN_SUMMARY_HINTS = (
    "总结",
    "概览",
    "方向",
    "重点",
    "下一步",
    "overview",
    "summarize",
    "summary",
    "next question",
)


@dataclass
class RewriteResult:
    question: str
    rewritten_query: str
    rewrite_rule_query: str
    rewrite_llm_query: str | None
    keywords_entities: dict[str, list[str]]
    strategy_hits: list[str]
    llm_used: bool = False
    llm_fallback: bool = False
    llm_diagnostics: dict[str, Any] | None = None
    rewrite_meta_detected: bool = False
    rewrite_guard_applied: bool = False
    rewrite_guard_strategy: str = "none"
    rewrite_notes: str | None = None
    rewrite_quality_score: float = 1.0
    rewrite_entity_preservation_ratio: float = 1.0
    rewrite_entity_lost_terms: list[str] | None = None
    rewrite_candidate_scores: dict[str, Any] | None = None
    rewrite_selected_by: str = "legacy_preference"


@dataclass
class RewriteGuardResult:
    standalone_query: str
    rewrite_meta_detected: bool
    rewrite_guard_applied: bool
    rewrite_guard_strategy: str
    rewrite_notes: str | None = None


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split())


def is_open_summary_intent_query(text: str) -> bool:
    lowered = _normalize_spaces(text).lower()
    if not lowered:
        return False
    return any(term in lowered for term in OPEN_SUMMARY_HINTS)


def _extract_preserved_terms(question: str) -> list[str]:
    terms: list[str] = []
    for regex in (ACRONYM_RE, METRIC_RE, FORMULA_RE):
        for m in regex.finditer(question):
            value = m.group(0).strip()
            if value and value not in terms:
                terms.append(value)
    for value in _extract_fidelity_terms(question):
        token = value.strip()
        if not token or token in terms:
            continue
        has_digit = bool(re.search(r"\d", token))
        has_acronym = bool(re.search(r"[A-Z]{2,}", token))
        is_simple_title = bool(re.fullmatch(r"[A-Z][a-z]+", token))
        has_mixed_case = bool(re.search(r"[A-Z]", token) and re.search(r"[a-z]", token) and not is_simple_title)
        if has_digit or has_acronym or has_mixed_case:
            terms.append(token)
    return terms


def _extract_fidelity_terms(question: str) -> list[str]:
    terms: list[str] = []
    # model / dataset / named entities
    for token in TOKEN_RE.findall(question or ""):
        value = str(token).strip()
        if not value:
            continue
        if re.fullmatch(r"(19|20)\d{2}", value):
            if value not in terms:
                terms.append(value)
            continue
        if len(value) >= 3 and (ACRONYM_RE.search(value) or re.search(r"[A-Za-z][A-Za-z0-9_\-/]+", value)):
            if value not in terms:
                terms.append(value)
    return terms[:12]


def _strip_filler(question: str) -> str:
    text = question
    for pattern in EN_FILLER_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    for pattern in ZH_FILLER_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"[?？!！]+", " ", text)
    return _normalize_spaces(text)


def _contains_meta_question(text: str, meta_patterns: list[str] | None = None) -> bool:
    lowered = (text or "").lower()
    for pattern in (meta_patterns or DEFAULT_META_PATTERNS):
        if re.search(pattern, lowered):
            return True
    return False


def _looks_like_mechanical_concat(text: str) -> bool:
    tokens = [t.lower() for t in TOKEN_RE.findall(text or "")]
    if len(tokens) < 4:
        return False
    if len(tokens) % 2 == 0:
        half = len(tokens) // 2
        if half >= 2 and tokens[:half] == tokens[half:]:
            return True
    return bool(re.search(r"(.{8,})\s+\1", _normalize_spaces(text), flags=re.IGNORECASE))


def _remove_meta_noise_tokens(text: str, meta_noise_terms: list[str] | set[str] | None = None) -> str:
    cleaned = text
    for term in (meta_noise_terms or DEFAULT_META_NOISE_TERMS):
        cleaned = re.sub(rf"\b{re.escape(term)}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[，。！？?!.]+", " ", cleaned)
    return _normalize_spaces(cleaned)


def apply_state_aware_rewrite_guard(
    *,
    user_input: str,
    standalone_query: str,
    entities_from_history: list[str] | None = None,
    last_turn_decision: str | None = None,
    last_turn_warnings: list[str] | None = None,
    meta_patterns: list[str] | None = None,
    meta_noise_terms: list[str] | set[str] | None = None,
) -> RewriteGuardResult:
    normalized = _normalize_spaces(standalone_query)
    if not normalized:
        return RewriteGuardResult(
            standalone_query="paper overview",
            rewrite_meta_detected=False,
            rewrite_guard_applied=True,
            rewrite_guard_strategy="empty_input_fallback",
            rewrite_notes="empty_standalone_query",
        )

    history_entities = [str(x).strip() for x in (entities_from_history or []) if str(x).strip()]
    warnings = [str(x).strip() for x in (last_turn_warnings or []) if str(x).strip()]
    meta_detected = _contains_meta_question(user_input, meta_patterns) or _contains_meta_question(
        normalized, meta_patterns
    )
    has_insufficient_warning = "insufficient_evidence_for_answer" in warnings

    if not meta_detected and not _looks_like_mechanical_concat(normalized):
        return RewriteGuardResult(
            standalone_query=normalized,
            rewrite_meta_detected=False,
            rewrite_guard_applied=False,
            rewrite_guard_strategy="no_guard",
            rewrite_notes=None,
        )

    repaired_query = normalized
    notes: list[str] = []
    strategy = "mechanical_concat_cleanup"

    if meta_detected:
        strategy = "meta_question_to_fact_query"
        focus_terms = FACT_FOCUS_TERMS_ZH if re.search(r"[\u4e00-\u9fff]", normalized) else FACT_FOCUS_TERMS
        if has_insufficient_warning:
            strategy = "meta_question_insufficient_evidence_repair"
        if history_entities:
            anchor = " ".join(history_entities[:2])
            repaired_query = f"{anchor} {' '.join(focus_terms[:3])}".strip()
        else:
            cleaned = _remove_meta_noise_tokens(normalized, meta_noise_terms)
            repaired_query = cleaned or ("paper method architecture details" if not re.search(r"[\u4e00-\u9fff]", normalized) else "论文 方法 架构 细节")
            strategy = "meta_question_no_entity_fallback"
            notes.append("history_entities_missing")
        notes.append(f"last_turn_decision={last_turn_decision or 'none'}")
        if has_insufficient_warning:
            notes.append("prior_warning=insufficient_evidence_for_answer")

    if _looks_like_mechanical_concat(repaired_query):
        lowered_tokens = [t for t in TOKEN_RE.findall(repaired_query)]
        if len(lowered_tokens) % 2 == 0 and len(lowered_tokens) >= 4:
            half = len(lowered_tokens) // 2
            if [t.lower() for t in lowered_tokens[:half]] == [t.lower() for t in lowered_tokens[half:]]:
                repaired_query = _normalize_spaces(" ".join(lowered_tokens[:half]))
            else:
                parts = re.split(r"[?？。.!]", repaired_query)
                repaired_query = _normalize_spaces(parts[-1] if parts and parts[-1].strip() else parts[0] if parts else repaired_query)
        else:
            parts = re.split(r"[?？。.!]", repaired_query)
            repaired_query = _normalize_spaces(parts[-1] if parts and parts[-1].strip() else parts[0] if parts else repaired_query)
        notes.append("mechanical_concat_trimmed")

    repaired_query = _remove_meta_noise_tokens(repaired_query, meta_noise_terms)
    if history_entities and all(e.lower() not in repaired_query.lower() for e in history_entities[:1]):
        repaired_query = f"{history_entities[0]} {repaired_query}".strip()
        notes.append("entity_reinserted")

    if not repaired_query:
        repaired_query = "paper overview"
        notes.append("guard_fallback_paper_overview")

    return RewriteGuardResult(
        standalone_query=repaired_query,
        rewrite_meta_detected=meta_detected,
        rewrite_guard_applied=True,
        rewrite_guard_strategy=strategy,
        rewrite_notes="; ".join(notes) if notes else None,
    )


def _expand_keywords(
    base_terms: list[str], synonyms: dict[str, list[str]], max_keywords: int
) -> tuple[list[str], list[str], bool]:
    keywords: list[str] = []
    entities: list[str] = []
    expanded_count = 0

    normalized_synonyms = {k.lower(): v for k, v in synonyms.items()}

    def _normalize_token(token: str) -> str:
        token_norm = token.lower().strip()
        singular_candidates: list[str] = []
        if token_norm.endswith("ies") and len(token_norm) > 3:
            singular_candidates.append(token_norm[:-3] + "y")
        if token_norm.endswith("es") and len(token_norm) > 2:
            singular_candidates.append(token_norm[:-2])
        if token_norm.endswith("s") and len(token_norm) > 1:
            singular_candidates.append(token_norm[:-1])
        for candidate in singular_candidates:
            if candidate in normalized_synonyms:
                return candidate
        return token_norm

    for term in base_terms:
        key = _normalize_token(term)
        if key in EN_STOPWORDS or key in ZH_STOPWORDS:
            continue
        if key and key not in keywords:
            keywords.append(key)
        if re.search(r"[\u4e00-\u9fff]", key):
            fragments = [
                frag
                for frag in re.split(r"[的和与及、，。；：:！？!?（）()《》“”\"'\\s]+", key)
                if frag
            ]
            for frag in fragments:
                if frag in normalized_synonyms and frag not in keywords:
                    keywords.append(frag)

    for term in list(keywords):
        expanded = normalized_synonyms.get(term, [])
        for ext in expanded:
            ext_key = ext.lower().strip()
            if ext_key and ext_key not in keywords:
                keywords.append(ext_key)
                expanded_count += 1
        if len(keywords) >= max_keywords:
            break

    # entities: acronym/formula-like tokens
    for term in base_terms:
        if ACRONYM_RE.search(term) or FORMULA_RE.search(term):
            entities.append(term)

    return keywords[:max_keywords], entities[:max_keywords], expanded_count > 0


def _validate_llm_rewrite(
    *,
    question: str,
    llm_query: str,
    preserved_terms: list[str],
    meta_patterns: list[str] | None = None,
) -> tuple[bool, str | None]:
    q = llm_query.strip()
    if not q:
        return False, "llm_empty_response_fallback_to_rules"
    if _contains_meta_question(q, meta_patterns):
        return False, "llm_polluted_status_query_fallback_to_rules"
    for term in preserved_terms:
        if term.lower() not in q.lower():
            return False, "llm_term_loss_fallback_to_rules"
    original_tokens = {
        t.lower()
        for t in TOKEN_RE.findall(question)
        if t.strip() and t.lower() not in EN_STOPWORDS and t.lower() not in ZH_STOPWORDS
    }
    rewritten_tokens = {
        t.lower()
        for t in TOKEN_RE.findall(q)
        if t.strip() and t.lower() not in EN_STOPWORDS and t.lower() not in ZH_STOPWORDS
    }
    if original_tokens:
        overlap = len(original_tokens.intersection(rewritten_tokens)) / max(1, len(original_tokens))
        if overlap < 0.2:
            return False, "llm_intent_drift_fallback_to_rules"
    if len(rewritten_tokens) > 0 and len(original_tokens) > 0:
        novel_ratio = len(rewritten_tokens - original_tokens) / max(1, len(rewritten_tokens))
        if novel_ratio > 0.8:
            return False, "llm_out_of_scope_fallback_to_rules"
    return True, None


def _repair_llm_query_with_constraints(
    *,
    llm_query: str,
    preserved_terms: list[str],
) -> tuple[str, bool]:
    repaired = _normalize_spaces(llm_query)
    changed = False
    for term in preserved_terms:
        if term.lower() not in repaired.lower():
            repaired = f"{repaired} {term}".strip()
            changed = True
    return repaired, changed


def evaluate_rewrite_quality(
    *,
    question: str,
    rewritten_query: str,
) -> tuple[float, float, list[str]]:
    src_terms = _extract_fidelity_terms(question)
    if not src_terms:
        return 1.0, 1.0, []
    lowered_rewrite = rewritten_query.lower()
    kept = [t for t in src_terms if t.lower() in lowered_rewrite]
    lost = [t for t in src_terms if t.lower() not in lowered_rewrite]
    preservation_ratio = len(kept) / max(1, len(src_terms))
    src_tokens = {t.lower() for t in TOKEN_RE.findall(question) if t.strip()}
    dst_tokens = {t.lower() for t in TOKEN_RE.findall(rewritten_query) if t.strip()}
    overlap = len(src_tokens.intersection(dst_tokens)) / max(1, len(src_tokens))
    quality = 0.6 * preservation_ratio + 0.4 * overlap
    return round(quality, 4), round(preservation_ratio, 4), lost[:8]


def _apply_llm_rewrite(
    *,
    question: str,
    base_query: str,
    config: PipelineConfig,
    preserved_terms: list[str],
    scope_mode: str | None,
    meta_patterns: list[str] | None = None,
) -> tuple[str | None, bool, bool, str, dict[str, Any] | None]:
    if scope_mode == "clarify_scope":
        return None, False, False, "llm_skipped_clarify_scope", None
    if not config.rewrite_use_llm:
        return None, False, False, "llm_disabled", None
    if not config.llm_fallback_enabled:
        return None, False, False, "llm_fallback_disabled_skip_llm", None
    policy = build_stage_policy(config, stage="rewrite")
    api_key = policy.primary.resolve_api_key()
    if not api_key and not policy.fallback:
        warning = "llm_missing_api_key_fallback_to_rules"
        return (
            None,
            False,
            True,
            warning,
            build_llm_diagnostics(
                stage="rewrite",
                provider=config.rewrite_llm_provider,
                model=config.rewrite_llm_model,
                reason="missing_api_key",
                fallback_warning=warning,
                attempts_used=0,
                max_retries=config.llm_max_retries,
                elapsed_ms=0,
                provider_used=None,
                model_used=None,
                fallback_reason="missing_api_key",
                error_category="other",
            ),
        )

    system_prompt = (
        "You rewrite search queries for retrieval. "
        "Never concatenate prior and current questions mechanically. "
        "For meta-questions about missing evidence/answer quality, rewrite into factual retrieval goals. "
        "Preserve entities/acronyms/metrics/formulas and avoid unrelated tasks. "
        "Output only one rewritten query string without explanation."
    )
    user_prompt = (
        f"Original question:\n{question}\n\n"
        f"Rule-based query:\n{base_query}\n\n"
        "Return a concise retrieval query."
    )
    result = call_chat_completion(
        provider=policy.primary.provider,
        model=policy.primary.model,
        api_key=api_key,
        api_base=policy.primary.api_base,
        fallback_provider=(policy.fallback.provider if policy.fallback else None),
        fallback_model=(policy.fallback.model if policy.fallback else None),
        fallback_api_key=(policy.fallback.resolve_api_key() if policy.fallback else None),
        fallback_api_base=(policy.fallback.api_base if policy.fallback else None),
        router_retry=policy.max_retries,
        router_cooldown_sec=policy.cooldown_seconds,
        router_failure_threshold=policy.failure_threshold,
        use_litellm_sdk=policy.use_litellm_sdk,
        use_legacy_client=policy.use_legacy_client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_ms=config.llm_timeout_ms,
        max_retries=config.llm_max_retries,
        temperature=0.0,
    )
    if not result.ok:
        reason_map = {
            "rate_limit": "llm_rate_limit_fallback_to_rules",
            "timeout": "llm_timeout_fallback_to_rules",
            "empty_response": "llm_empty_response_fallback_to_rules",
            "missing_api_key": "llm_missing_api_key_fallback_to_rules",
        }
        warning = reason_map.get(result.reason or "", "llm_error_fallback_to_rules")
        return (
            None,
            False,
            True,
            warning,
            build_llm_diagnostics(
                stage="rewrite",
                provider=config.rewrite_llm_provider,
                model=config.rewrite_llm_model,
                reason=str(result.reason or "unknown_error"),
                fallback_warning=warning,
                status_code=getattr(result, "status_code", None),
                attempts_used=getattr(result, "attempts_used", 0),
                max_retries=getattr(result, "max_retries", config.llm_max_retries),
                elapsed_ms=getattr(result, "elapsed_ms", 0),
                timestamp=getattr(result, "timestamp", None),
                provider_used=getattr(result, "provider_used", None),
                model_used=getattr(result, "model_used", None),
                fallback_reason=getattr(result, "fallback_reason", None) or str(result.reason or ""),
                error_category=getattr(result, "error_category", None)
                or classify_error_category(getattr(result, "reason", None), getattr(result, "status_code", None)),
            ),
        )

    llm_query = (result.content or "").strip()
    valid, validation_reason = _validate_llm_rewrite(
        question=question,
        llm_query=llm_query,
        preserved_terms=preserved_terms,
        meta_patterns=meta_patterns,
    )
    if not valid:
        if validation_reason in {"llm_term_loss_fallback_to_rules", "llm_intent_drift_fallback_to_rules"}:
            repaired_query, changed = _repair_llm_query_with_constraints(
                llm_query=llm_query,
                preserved_terms=preserved_terms,
            )
            if changed:
                valid_after_repair, _ = _validate_llm_rewrite(
                    question=question,
                    llm_query=repaired_query,
                    preserved_terms=preserved_terms,
                    meta_patterns=meta_patterns,
                )
                if valid_after_repair:
                    return repaired_query, True, False, "llm_rewrite_repaired_with_constraints", None
        warning = validation_reason or "llm_query_validation_failed_fallback_to_rules"
        return (
            None,
            False,
            True,
            warning,
            build_llm_diagnostics(
                stage="rewrite",
                provider=config.rewrite_llm_provider,
                model=config.rewrite_llm_model,
                reason="validation_failed",
                fallback_warning=warning,
                status_code=getattr(result, "status_code", None),
                attempts_used=getattr(result, "attempts_used", 0),
                max_retries=getattr(result, "max_retries", config.llm_max_retries),
                elapsed_ms=getattr(result, "elapsed_ms", 0),
                timestamp=getattr(result, "timestamp", None),
                provider_used=getattr(result, "provider_used", None),
                model_used=getattr(result, "model_used", None),
                fallback_reason=getattr(result, "fallback_reason", None) or "validation_failed",
                error_category="other",
            ),
        )
    return llm_query, True, False, "llm_rewrite_applied", None


def rewrite_query(
    question: str,
    config: PipelineConfig,
    scope_mode: str | None = None,
    *,
    intent_type: str = "retrieval_query",
    anchor_query: str | None = None,
    history_constraints_dropped: list[str] | None = None,
) -> RewriteResult:
    normalized_question = _normalize_spaces(question)
    fallback_query = "paper overview"
    strategy_hits: list[str] = []

    if not normalized_question:
        return RewriteResult(
            question=normalized_question,
            rewritten_query=fallback_query,
            rewrite_rule_query=fallback_query,
            rewrite_llm_query=None,
            keywords_entities={"keywords": ["paper", "overview"], "entities": []},
            strategy_hits=["empty_input_fallback"],
            rewrite_notes="empty_input_fallback",
            rewrite_entity_lost_terms=[],
        )

    if not config.rewrite_enabled:
        rewritten = normalized_question if normalized_question else fallback_query
        hits = ["rewrite_disabled"]
        if rewritten == fallback_query:
            hits.append("empty_input_fallback")
        return RewriteResult(
            question=normalized_question,
            rewritten_query=rewritten,
            rewrite_rule_query=rewritten,
            rewrite_llm_query=None,
            keywords_entities={"keywords": [], "entities": []},
            strategy_hits=hits,
            rewrite_notes=None,
        )

    if intent_type in CONTROL_INTENT_TYPES:
        anchor = _normalize_spaces(anchor_query or "")
        if anchor:
            base_terms = [m.group(0) for m in TOKEN_RE.finditer(anchor)]
            keywords, entities, _ = _expand_keywords(base_terms, config.rewrite_synonyms, config.rewrite_max_keywords)
            return RewriteResult(
                question=normalized_question,
                rewritten_query=anchor,
                rewrite_rule_query=anchor,
                rewrite_llm_query=None,
                keywords_entities={"keywords": keywords, "entities": entities},
                strategy_hits=["control_intent_anchor_query_reused"],
                llm_used=False,
                llm_fallback=False,
            llm_diagnostics=None,
            rewrite_notes="control_intent_anchor_query_reused",
            rewrite_entity_lost_terms=[],
        )
        return RewriteResult(
            question=normalized_question,
            rewritten_query=normalized_question or fallback_query,
            rewrite_rule_query=normalized_question or fallback_query,
            rewrite_llm_query=None,
            keywords_entities={"keywords": [], "entities": []},
            strategy_hits=["control_intent_without_anchor"],
            llm_used=False,
            llm_fallback=False,
            llm_diagnostics=None,
            rewrite_notes="control_intent_without_anchor",
            rewrite_entity_lost_terms=[],
        )

    preserved_terms = _extract_preserved_terms(normalized_question)
    if preserved_terms:
        strategy_hits.append("term_preservation")

    retrieval_sentence = _strip_filler(normalized_question)
    if retrieval_sentence != normalized_question:
        strategy_hits.append("question_to_retrieval_sentence")

    if not retrieval_sentence:
        retrieval_sentence = normalized_question
    if is_open_summary_intent_query(normalized_question):
        strategy_hits.append("open_summary_intent_detected")
    if history_constraints_dropped:
        strategy_hits.append("history_constraint_dropped")

    for term in preserved_terms:
        if term.lower() not in retrieval_sentence.lower():
            retrieval_sentence = f"{retrieval_sentence} {term}".strip()

    base_terms = [m.group(0) for m in TOKEN_RE.finditer(retrieval_sentence)]
    keywords, entities, expanded = _expand_keywords(base_terms, config.rewrite_synonyms, config.rewrite_max_keywords)

    if expanded:
        strategy_hits.append("keyword_expansion")

    llm_query, llm_used, llm_fallback, llm_hit, llm_diagnostics = _apply_llm_rewrite(
        question=normalized_question,
        base_query=retrieval_sentence,
        config=config,
        preserved_terms=preserved_terms,
        scope_mode=scope_mode,
        meta_patterns=config.rewrite_meta_patterns,
    )
    if llm_hit:
        strategy_hits.append(llm_hit)
    final_query = llm_query or retrieval_sentence
    rewrite_notes = llm_hit if llm_fallback else None
    if history_constraints_dropped:
        drop_notes = f"dropped_constraints={','.join(history_constraints_dropped)}"
        rewrite_notes = f"{rewrite_notes}; {drop_notes}" if rewrite_notes else drop_notes

    quality_score, preservation_ratio, lost_terms = evaluate_rewrite_quality(
        question=normalized_question,
        rewritten_query=final_query,
    )
    return RewriteResult(
        question=normalized_question,
        rewritten_query=final_query,
        rewrite_rule_query=retrieval_sentence,
        rewrite_llm_query=llm_query,
        keywords_entities={"keywords": keywords, "entities": entities},
        strategy_hits=strategy_hits,
        llm_used=llm_used,
        llm_fallback=llm_fallback,
        llm_diagnostics=llm_diagnostics,
        rewrite_notes=rewrite_notes,
        rewrite_quality_score=quality_score,
        rewrite_entity_preservation_ratio=preservation_ratio,
        rewrite_entity_lost_terms=lost_terms,
    )
