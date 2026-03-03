from __future__ import annotations

import os
import re
import math
from typing import Any

from app.embedding_api import EmbeddingAPIError, fetch_embeddings

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")

NOISY_CONTENT_TYPES = {"front_matter", "reference"}
KEY_ELEMENT_NUMERIC_TERMS = (
    "多少",
    "几",
    "数值",
    "比例",
    "准确率",
    "召回率",
    "f1",
    "f-1",
    "precision",
    "recall",
    "rate",
    "score",
    "percent",
    "%",
    "number",
)
KEY_ELEMENT_METHOD_TERMS = (
    "方法",
    "机制",
    "流程",
    "步骤",
    "算法",
    "原理",
    "how",
    "method",
    "mechanism",
    "approach",
    "pipeline",
)
KEY_ELEMENT_SCOPE_TERMS = (
    "哪篇",
    "哪个",
    "标题",
    "谁",
    "作者",
    "年份",
    "会议",
    "title",
    "author",
    "year",
    "conference",
)
KEY_ELEMENT_EXPERIMENT_CONDITION_TERMS = (
    "实验条件",
    "实验设置",
    "评测设置",
    "设置下",
    "条件下",
    "condition",
    "setting",
    "under what",
    "under which",
    "benchmark setting",
)
KEY_ELEMENT_SUBJECT_CONSTRAINT_TERMS = (
    "主体",
    "对象",
    "受试者",
    "样本",
    "人群",
    "患者",
    "学生",
    "用户",
    "participant",
    "subject",
    "cohort",
    "population",
    "group",
)
QUESTION_TYPE_DEFINITION_TERMS = (
    "what is",
    "what does",
    "定义",
    "含义",
    "是什么",
    "是指",
)
QUESTION_TYPE_NUMERIC_TERMS = (
    "how much",
    "how many",
    "to what extent",
    "提升了多少",
    "提高了多少",
    "幅度",
)
QUESTION_TYPE_METHOD_TERMS = (
    "how does",
    "how do",
    "workflow",
    "procedure",
    "principle",
    "如何",
    "怎么",
    "机制",
)
QUESTION_TYPE_FACT_CHECK_TERMS = (
    "is it true",
    "true or false",
    "fact check",
    "是否",
    "是不是",
    "是否成立",
    "真实吗",
)
QUESTION_TYPE_REQUIRED_SLOTS: dict[str, set[str]] = {
    "definition": set(),
    "numeric": {"numeric"},
    "method": {"method"},
    "fact_check": {"scope"},
}


def _extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z0-9_])\d+(?:\.\d+)?%?(?![A-Za-z0-9_])", text or ""))


def _tokenize_for_matching(text: str) -> set[str]:
    tokens = {tok.lower() for tok in TOKEN_RE.findall(text or "") if tok.strip()}
    stop = {
        "the",
        "is",
        "are",
        "a",
        "an",
        "of",
        "and",
        "to",
        "in",
        "for",
        "with",
        "what",
        "which",
        "this",
        "that",
        "这些",
        "那些",
        "什么",
        "哪个",
        "哪些",
        "如何",
        "怎么",
        "请问",
        "帮我",
    }
    return {tok for tok in tokens if tok not in stop and len(tok) > 1}


def _collect_evidence_text(evidence_grouped: list[dict[str, Any]]) -> str:
    segments: list[str] = []
    for group in evidence_grouped:
        title = str(group.get("paper_title", "")).strip()
        if title:
            segments.append(title)
        for item in group.get("evidence", []):
            quote = str(item.get("quote", "")).strip()
            if quote:
                segments.append(quote)
    return " ".join(segments)


def _to_semantic_vec(text: str) -> dict[str, float]:
    vec: dict[str, float] = {}
    lowered = (text or "").lower()
    for token in _tokenize_for_matching(lowered):
        vec[token] = vec.get(token, 0.0) + 1.0
        if len(token) >= 3:
            for i in range(0, len(token) - 2):
                ngram = token[i : i + 3]
                vec[f"tri:{ngram}"] = vec.get(f"tri:{ngram}", 0.0) + 0.25
    return vec


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_similarity_score_fallback(question: str, evidence_grouped: list[dict[str, Any]]) -> float:
    q_vec = _to_semantic_vec(question)
    e_vec = _to_semantic_vec(_collect_evidence_text(evidence_grouped))
    return _cosine_similarity(q_vec, e_vec)


def _dense_cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_similarity_scores(
    *,
    question: str,
    query_used_text: str,
    evidence_grouped: list[dict[str, Any]],
    config: Any,
) -> tuple[float, float]:
    evidence_text = _collect_evidence_text(evidence_grouped)
    embedding_cfg = getattr(config, "embedding", None)
    embedding_enabled = bool(getattr(embedding_cfg, "enabled", False))
    if embedding_enabled and evidence_text.strip():
        api_env = str(getattr(embedding_cfg, "api_key_env", "")).strip()
        api_key = os.environ.get(api_env, "").strip() if api_env else ""
        if api_key:
            try:
                vectors = fetch_embeddings(
                    [question, query_used_text, evidence_text],
                    base_url=str(getattr(embedding_cfg, "base_url", "")),
                    model=str(getattr(embedding_cfg, "model", "")),
                    api_key_env=api_env,
                )
                if len(vectors) == 3:
                    return (
                        _dense_cosine_similarity(vectors[0], vectors[2]),
                        _dense_cosine_similarity(vectors[1], vectors[2]),
                    )
            except EmbeddingAPIError:
                pass
    return (
        _semantic_similarity_score_fallback(question, evidence_grouped),
        _semantic_similarity_score_fallback(query_used_text, evidence_grouped),
    )


def _policy_threshold(config: Any) -> tuple[str, float]:
    policy = str(getattr(config, "sufficiency_semantic_policy", "balanced") or "balanced").strip().lower()
    if policy not in {"strict", "balanced", "explore"}:
        policy = "balanced"
    thresholds = {
        "strict": float(getattr(config, "sufficiency_semantic_threshold_strict", 0.35)),
        "balanced": float(getattr(config, "sufficiency_semantic_threshold_balanced", 0.25)),
        "explore": float(getattr(config, "sufficiency_semantic_threshold_explore", 0.15)),
    }
    threshold = thresholds.get(policy, thresholds["balanced"])
    return policy, threshold


def _is_insufficient_evidence(
    evidence_grouped: list[dict[str, Any]],
    *,
    min_evidence: int = 2,
) -> bool:
    flat: list[dict[str, Any]] = []
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            if isinstance(item, dict):
                flat.append(item)
    if len(flat) < min_evidence:
        return True
    noisy_only = all((item.get("content_type", "body") or "body").lower() in NOISY_CONTENT_TYPES for item in flat)
    return noisy_only


def _topic_match_score(question: str, evidence_grouped: list[dict[str, Any]]) -> float:
    q_tokens = _tokenize_for_matching(question)
    if not q_tokens:
        return 1.0
    e_tokens = _tokenize_for_matching(_collect_evidence_text(evidence_grouped))
    if not e_tokens:
        return 0.0
    return len(q_tokens.intersection(e_tokens)) / max(1, len(q_tokens))


def _has_topic_cluster_signal(question: str, evidence_grouped: list[dict[str, Any]]) -> bool:
    q_tokens = _tokenize_for_matching(question)
    if not q_tokens:
        return False
    for group in evidence_grouped:
        snippets = group.get("evidence", [])
        if len(snippets) < 2:
            continue
        group_text = " ".join(str(item.get("quote", "")).strip() for item in snippets if isinstance(item, dict))
        overlap = q_tokens.intersection(_tokenize_for_matching(group_text))
        if any(len(tok) >= 4 for tok in overlap):
            return True
    return False


def _classify_question_types(question: str) -> set[str]:
    lowered = (question or "").lower()
    q_types: set[str] = set()
    if any(term in lowered for term in QUESTION_TYPE_DEFINITION_TERMS):
        q_types.add("definition")
    if any(term in lowered for term in QUESTION_TYPE_NUMERIC_TERMS):
        q_types.add("numeric")
    if any(term in lowered for term in QUESTION_TYPE_METHOD_TERMS):
        q_types.add("method")
    if any(term in lowered for term in QUESTION_TYPE_FACT_CHECK_TERMS) or re.search(r"\bis\s+.+\btrue\b", lowered):
        q_types.add("fact_check")
    return q_types


def _required_key_elements(question: str, *, open_summary_intent: bool = False) -> set[str]:
    lowered = (question or "").lower()
    required: set[str] = set()
    for q_type in _classify_question_types(question):
        required.update(QUESTION_TYPE_REQUIRED_SLOTS.get(q_type, set()))
    if not open_summary_intent and (
        re.search(r"\b\d+(?:\.\d+)?\b", lowered) or any(term in lowered for term in KEY_ELEMENT_NUMERIC_TERMS)
    ):
        required.add("numeric")
    if any(term in lowered for term in KEY_ELEMENT_METHOD_TERMS):
        required.add("method")
    if any(term in lowered for term in KEY_ELEMENT_SCOPE_TERMS):
        required.add("scope")
    if any(term in lowered for term in KEY_ELEMENT_EXPERIMENT_CONDITION_TERMS):
        required.add("experiment_condition")
    if any(term in lowered for term in KEY_ELEMENT_SUBJECT_CONSTRAINT_TERMS):
        required.add("subject_constraint")
    return required


def _covered_key_elements(evidence_grouped: list[dict[str, Any]]) -> set[str]:
    evidence_text = _collect_evidence_text(evidence_grouped)
    lowered = evidence_text.lower()
    covered: set[str] = set()
    if _extract_numbers(evidence_text):
        covered.add("numeric")
    if any(term in lowered for term in KEY_ELEMENT_METHOD_TERMS):
        covered.add("method")
    if any(term in lowered for term in KEY_ELEMENT_SCOPE_TERMS):
        covered.add("scope")
    if any(term in lowered for term in KEY_ELEMENT_EXPERIMENT_CONDITION_TERMS):
        covered.add("experiment_condition")
    if any(term in lowered for term in KEY_ELEMENT_SUBJECT_CONSTRAINT_TERMS):
        covered.add("subject_constraint")
    return covered


def _build_clarify_questions(question: str, missing_elements: list[str]) -> list[str]:
    prompts: list[str] = []
    for element in missing_elements:
        if element == "numeric":
            prompts.append("您希望我回答哪项具体数值或指标（例如准确率、召回率、F1）？")
        elif element == "method":
            prompts.append("您更关注方法的哪部分细节（流程、关键步骤或机制）？")
        elif element == "scope":
            prompts.append("请指定论文线索（标题、作者、年份或会议）以便定位证据。")
        elif element == "experiment_condition":
            prompts.append("请说明您关心的实验条件（如数据集、评测设置或对比基线）。")
        elif element == "subject_constraint":
            prompts.append("请说明您关注的主体限定（如人群、样本范围或特定对象）。")
    if not prompts:
        prompts.append(f"请补充问题“{question}”所需的论文或实验线索。")
    return prompts[:1]


def run_sufficiency_gate(
    *,
    question: str,
    query_used: str | None = None,
    topic_query_source: str = "user_query",
    topic_query_text: str | None = None,
    open_summary_intent: bool = False,
    scope_mode: str,
    evidence_grouped: list[dict[str, Any]],
    config: Any,
    clarify_count_for_topic: int = 0,
    clarify_limit: int = 2,
    force_partial_answer_on_limit: bool = True,
) -> dict[str, Any]:
    enabled = bool(getattr(config, "sufficiency_gate_enabled", True))
    report: dict[str, Any] = {
        "enabled": enabled,
        "decision": "answer",
        "reason": "证据充分，可进入回答。",
        "clarify_questions": [],
        "triggered_rules": [],
        "topic_match_score": 1.0,
        "topic_match_score_standalone": 1.0,
        "topic_match_score_query_used": 1.0,
        "topic_match_score_robust": 1.0,
        "semantic_similarity_score": 1.0,
        "semantic_policy": "balanced",
        "semantic_threshold": 0.25,
        "topic_query_source": topic_query_source,
        "topic_query_text": str(topic_query_text or query_used or question),
        "key_element_coverage": 1.0,
        "missing_key_elements": [],
        "missing_aspects": [],
        "clarify_count": max(0, int(clarify_count_for_topic)),
        "clarify_limit_hit": False,
        "forced_partial_answer": False,
    }

    def _finalize_clarify() -> dict[str, Any]:
        if (
            force_partial_answer_on_limit
            and clarify_limit > 0
            and int(report.get("clarify_count", 0)) >= clarify_limit
        ):
            report["decision"] = "answer"
            report["reason"] = "连续澄清达到上限，改为低置信可追溯回答。"
            report["clarify_questions"] = []
            report["clarify_limit_hit"] = True
            report["forced_partial_answer"] = True
            report["triggered_rules"].append("clarify_limit_reached_force_partial_answer")
        return report

    if not enabled:
        report["reason"] = "Sufficiency Gate 已关闭。"
        return report

    if scope_mode == "clarify_scope":
        report["decision"] = "clarify"
        report["reason"] = "问题范围不明确，需要先澄清论文范围。"
        report["clarify_questions"] = ["请提供论文标题、作者、年份或会议等线索。"]
        report["triggered_rules"].append("scope_clarify_mode")
        return _finalize_clarify()

    if _is_insufficient_evidence(evidence_grouped):
        if open_summary_intent:
            report["decision"] = "clarify"
            report["reason"] = "当前证据不足以支持开放式总结，请先补充一个核心主题线索。"
            report["clarify_questions"] = ["你最关心哪一类主题（方法、实验结果、应用场景）？"]
            report["triggered_rules"].append("insufficient_evidence_minimal_clarify")
            return _finalize_clarify()
        report["decision"] = "refuse"
        report["reason"] = "证据数量或质量不足，无法可靠回答。"
        report["triggered_rules"].append("insufficient_evidence_count_or_quality")
        return report

    topic_threshold = float(getattr(config, "sufficiency_topic_match_threshold", 0.15))
    semantic_policy, semantic_threshold = _policy_threshold(config)
    query_used_text = str(topic_query_text or query_used or "").strip() or question
    topic_score_standalone = _topic_match_score(question, evidence_grouped)
    topic_score_query_used = _topic_match_score(query_used_text, evidence_grouped)
    topic_score_robust = max(topic_score_standalone, topic_score_query_used)
    semantic_standalone, semantic_query_used = _semantic_similarity_scores(
        question=question,
        query_used_text=query_used_text,
        evidence_grouped=evidence_grouped,
        config=config,
    )
    semantic_score = max(semantic_standalone, semantic_query_used, topic_score_robust)
    report["topic_match_score_standalone"] = topic_score_standalone
    report["topic_match_score_query_used"] = topic_score_query_used
    report["topic_match_score_robust"] = topic_score_robust
    report["topic_match_score"] = topic_score_robust
    report["semantic_similarity_score"] = semantic_score
    report["semantic_policy"] = semantic_policy
    report["semantic_threshold"] = semantic_threshold
    if topic_score_robust < topic_threshold:
        if open_summary_intent:
            report["decision"] = "clarify"
            report["reason"] = "证据与当前主题相关性不足，请先明确一个优先主题。"
            report["clarify_questions"] = ["你想先聚焦哪个主题方向？"]
            report["triggered_rules"].append("topic_mismatch_minimal_clarify")
            return _finalize_clarify()
        if _has_topic_cluster_signal(question, evidence_grouped) or _has_topic_cluster_signal(query_used_text, evidence_grouped):
            report["decision"] = "clarify"
            report["reason"] = "检测到同主题论文簇命中，但缺少足够主题约束；请先明确一个聚焦方向。"
            report["clarify_questions"] = ["你想先聚焦该主题的哪个方面（方法、实验结果或应用场景）？"]
            report["triggered_rules"].append("topic_mismatch_cluster_minimal_clarify")
            return _finalize_clarify()
    if semantic_score < semantic_threshold and topic_score_robust < topic_threshold:
        report["decision"] = "refuse"
        report["reason"] = "证据与问题主题不匹配，相关性不足。"
        report["triggered_rules"].append("topic_mismatch")
        return report

    required = _required_key_elements(question, open_summary_intent=open_summary_intent)
    covered = _covered_key_elements(evidence_grouped)
    missing = sorted(required - covered)
    coverage = 1.0 if not required else (len(required) - len(missing)) / len(required)
    report["key_element_coverage"] = coverage
    report["missing_key_elements"] = missing
    report["missing_aspects"] = list(missing)
    min_coverage = float(getattr(config, "sufficiency_key_element_min_coverage", 1.0))
    if missing and coverage < min_coverage:
        report["decision"] = "clarify"
        report["reason"] = f"证据缺少关键要素：{', '.join(missing)}。"
        report["clarify_questions"] = _build_clarify_questions(question, missing)
        report["triggered_rules"].append("missing_key_elements")
        return _finalize_clarify()

    return report
