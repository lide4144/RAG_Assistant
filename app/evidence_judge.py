from __future__ import annotations

import json
import os
import re
from typing import Any

from app.llm_client import call_chat_completion

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")
STOPWORDS = {
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
    "these",
    "those",
    "please",
    "请",
    "请问",
    "帮我",
    "什么",
    "哪个",
    "哪些",
    "如何",
    "怎么",
}
JUDGE_SYSTEM_PROMPT = (
    "You are a semantic evidence judge for a RAG sufficiency gate. "
    "You must assess whether the supplied evidence answers the user question. "
    "Return only one JSON object with keys: decision_hint, missing_aspects, covered_aspects, "
    "topic_aligned, allows_partial_answer, confidence. "
    "decision_hint must be one of answer, partial, mismatch, uncertain. "
    "Do not include markdown fences."
)


def _tokenize_for_matching(text: str) -> list[str]:
    tokens = [tok.lower() for tok in TOKEN_RE.findall(text or "") if tok.strip()]
    return [tok for tok in tokens if tok not in STOPWORDS and len(tok) > 1]


def _extract_anchor_terms(text: str, *, max_terms: int = 8) -> list[str]:
    anchors = sorted(set(_tokenize_for_matching(text)), key=lambda item: (-len(item), item))
    return anchors[:max_terms]


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _judge_error(
    *,
    config: Any,
    topic_query_text: str,
    evidence_grouped: list[dict[str, Any]],
    warning: str,
    status: str,
) -> dict[str, Any]:
    semantic_policy = str(getattr(config, "sufficiency_semantic_policy", "balanced") or "balanced").strip().lower()
    if semantic_policy not in {"strict", "balanced", "explore"}:
        semantic_policy = "balanced"
    thresholds = {
        "strict": float(getattr(config, "sufficiency_semantic_threshold_strict", 0.35)),
        "balanced": float(getattr(config, "sufficiency_semantic_threshold_balanced", 0.25)),
        "explore": float(getattr(config, "sufficiency_semantic_threshold_explore", 0.15)),
    }
    return {
        "decision_hint": "uncertain",
        "judge_status": status,
        "judge_source": "semantic_evidence_judge_llm_v1",
        "confidence": "low",
        "coverage_summary": {
            "topic_aligned": False,
            "covered_aspects": [],
            "missing_aspects": [],
            "matched_anchors": _extract_anchor_terms(topic_query_text),
            "anchor_count": len(_extract_anchor_terms(topic_query_text)),
            "evidence_groups": len(evidence_grouped),
        },
        "missing_aspects": [],
        "allows_partial_answer": False,
        "semantic_policy": semantic_policy,
        "semantic_threshold": thresholds.get(semantic_policy, thresholds["balanced"]),
        "output_warnings": [warning],
    }


def judge_semantic_evidence(
    *,
    question: str,
    topic_query_text: str,
    evidence_grouped: list[dict[str, Any]],
    config: Any,
) -> dict[str, Any]:
    if not bool(getattr(config, "sufficiency_judge_use_llm", True)):
        return _judge_error(
            config=config,
            topic_query_text=topic_query_text or question,
            evidence_grouped=evidence_grouped,
            warning="judge_llm_disabled",
            status="error",
        )
    api_env = str(getattr(config, "sufficiency_judge_llm_api_key_env", "")).strip()
    api_key = os.environ.get(api_env, "").strip() if api_env else ""
    if not api_key:
        return _judge_error(
            config=config,
            topic_query_text=topic_query_text or question,
            evidence_grouped=evidence_grouped,
            warning="judge_llm_missing_api_key",
            status="unavailable",
        )

    evidence_preview: list[dict[str, Any]] = []
    for group in evidence_grouped[:3]:
        snippets: list[str] = []
        for item in (group.get("evidence", []) or [])[:3]:
            quote = str((item or {}).get("quote", "")).strip()
            if quote:
                snippets.append(quote[:240])
        evidence_preview.append(
            {
                "paper_title": str(group.get("paper_title", "")).strip(),
                "snippets": snippets,
            }
        )

    user_prompt = json.dumps(
        {
            "question": question,
            "topic_query_text": topic_query_text,
            "evidence_grouped": evidence_preview,
        },
        ensure_ascii=False,
    )
    result = call_chat_completion(
        provider=str(getattr(config, "sufficiency_judge_llm_provider", "siliconflow")),
        model=str(getattr(config, "sufficiency_judge_llm_model", "")),
        api_key=api_key,
        api_base=str(getattr(config, "sufficiency_judge_llm_api_base", "")) or None,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        timeout_ms=max(1000, int(getattr(config, "sufficiency_judge_llm_timeout_ms", 6000))),
        max_retries=max(0, int(getattr(config, "llm_max_retries", 1))),
        router_retry=int(getattr(config, "llm_router_retry", 1)),
        router_cooldown_sec=int(getattr(config, "llm_router_cooldown_sec", 60)),
        router_failure_threshold=int(getattr(config, "llm_router_failure_threshold", 2)),
        use_litellm_sdk=bool(getattr(config, "llm_use_litellm_sdk", True)),
        use_legacy_client=bool(getattr(config, "llm_use_legacy_client", False)),
        temperature=0.0,
    )
    if not result.ok:
        return _judge_error(
            config=config,
            topic_query_text=topic_query_text or question,
            evidence_grouped=evidence_grouped,
            warning="judge_llm_call_failed",
            status="error",
        )
    payload = _extract_first_json_object(str(result.content or ""))
    if not isinstance(payload, dict):
        return _judge_error(
            config=config,
            topic_query_text=topic_query_text or question,
            evidence_grouped=evidence_grouped,
            warning="judge_llm_invalid_payload",
            status="error",
        )

    decision_hint = str(payload.get("decision_hint", "")).strip().lower()
    if decision_hint not in {"answer", "partial", "mismatch", "uncertain"}:
        return _judge_error(
            config=config,
            topic_query_text=topic_query_text or question,
            evidence_grouped=evidence_grouped,
            warning="judge_llm_invalid_payload",
            status="error",
        )
    missing_aspects = [str(x).strip() for x in (payload.get("missing_aspects") or []) if str(x).strip()]
    covered_aspects = [str(x).strip() for x in (payload.get("covered_aspects") or []) if str(x).strip()]
    semantic_policy = str(getattr(config, "sufficiency_semantic_policy", "balanced") or "balanced").strip().lower()
    if semantic_policy not in {"strict", "balanced", "explore"}:
        semantic_policy = "balanced"
    thresholds = {
        "strict": float(getattr(config, "sufficiency_semantic_threshold_strict", 0.35)),
        "balanced": float(getattr(config, "sufficiency_semantic_threshold_balanced", 0.25)),
        "explore": float(getattr(config, "sufficiency_semantic_threshold_explore", 0.15)),
    }
    anchors = _extract_anchor_terms(topic_query_text or question)
    return {
        "decision_hint": decision_hint,
        "judge_status": "ok" if decision_hint != "uncertain" else "uncertain",
        "judge_source": "semantic_evidence_judge_llm_v1",
        "confidence": str(payload.get("confidence") or "medium").strip().lower() or "medium",
        "coverage_summary": {
            "topic_aligned": bool(payload.get("topic_aligned", decision_hint != "mismatch")),
            "covered_aspects": covered_aspects,
            "missing_aspects": missing_aspects,
            "matched_anchors": anchors,
            "anchor_count": len(anchors),
            "evidence_groups": len(evidence_grouped),
        },
        "missing_aspects": missing_aspects,
        "allows_partial_answer": bool(payload.get("allows_partial_answer", bool(covered_aspects))),
        "semantic_policy": semantic_policy,
        "semantic_threshold": thresholds.get(semantic_policy, thresholds["balanced"]),
        "output_warnings": [],
    }
