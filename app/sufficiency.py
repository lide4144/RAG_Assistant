from __future__ import annotations

from typing import Any

from app.evidence_judge import judge_semantic_evidence
from app.planner_policy import build_constraint_envelope

NOISY_CONTENT_TYPES = {"front_matter", "reference"}


def _flatten_evidence(evidence_grouped: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            if isinstance(item, dict):
                flat.append(item)
    return flat


def _is_insufficient_evidence(
    evidence_grouped: list[dict[str, Any]],
    *,
    min_evidence: int = 2,
) -> bool:
    flat = _flatten_evidence(evidence_grouped)
    if len(flat) < min_evidence:
        return True
    noisy_only = all((item.get("content_type", "body") or "body").lower() in NOISY_CONTENT_TYPES for item in flat)
    return noisy_only


def _has_traceable_evidence(evidence_grouped: list[dict[str, Any]]) -> bool:
    for item in _flatten_evidence(evidence_grouped):
        if str(item.get("quote", "")).strip():
            return True
    return False


def _build_clarify_questions(question: str, missing_aspects: list[str]) -> list[str]:
    prompts: list[str] = []
    for aspect in missing_aspects:
        cleaned = str(aspect or "").strip(" ，,。；;？?")
        if cleaned:
            prompts.append(f"请补充你最关心的这一方面：{cleaned}")
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
        "reason_code": "ready_to_answer",
        "severity": "info",
        "clarify_questions": [],
        "output_warnings": [],
        "triggered_rules": [],
        "allows_partial_answer": False,
        "guardrail_blocked": False,
        "constraints_envelope": None,
        "semantic_policy": "balanced",
        "semantic_threshold": 0.25,
        "topic_query_source": topic_query_source,
        "topic_query_text": str(topic_query_text or query_used or question),
        "missing_aspects": [],
        "coverage_summary": {},
        "judge_source": None,
        "judge_status": "not_run",
        "validator_source": "deterministic_validator_v1",
        "validator_summary": {"passed": True, "checks": []},
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
            report["reason_code"] = "clarify_limit_reached_force_partial_answer"
            report["severity"] = "warning"
            report["clarify_questions"] = []
            report["clarify_limit_hit"] = True
            report["forced_partial_answer"] = True
            report["allows_partial_answer"] = True
            report["triggered_rules"].append("clarify_limit_reached_force_partial_answer")
            report["output_warnings"].append("clarify_limit_reached_force_partial_answer")
            report["constraints_envelope"] = build_constraint_envelope(
                constraint_type="partial_answer",
                reason_code="clarify_limit_reached_force_partial_answer",
                severity="warning",
                retryable=True,
                blocking_scope="full_answer",
                user_safe_summary=report["reason"],
                evidence_snapshot={"evidence_groups": len(evidence_grouped)},
                suggested_next_actions=["继续补充更具体的论文线索或实验指标。"],
                allows_partial_answer=True,
            )
        return report

    if not enabled:
        report["reason"] = "Sufficiency Gate 已关闭。"
        return report

    if scope_mode == "clarify_scope":
        report["decision"] = "clarify"
        report["reason"] = "问题范围不明确，需要先澄清论文范围。"
        report["reason_code"] = "scope_clarify_mode"
        report["severity"] = "warning"
        report["clarify_questions"] = ["请提供论文标题、作者、年份或会议等线索。"]
        report["triggered_rules"].append("scope_clarify_mode")
        report["output_warnings"].append("scope_clarify_mode")
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="scope_missing",
            reason_code="scope_clarify_mode",
            severity="warning",
            retryable=True,
            blocking_scope="query_scope",
            user_safe_summary=report["reason"],
            evidence_snapshot={"evidence_groups": len(evidence_grouped)},
            suggested_next_actions=report["clarify_questions"],
            clarify_questions=report["clarify_questions"],
        )
        return _finalize_clarify()

    if _is_insufficient_evidence(evidence_grouped):
        report["validator_summary"] = {"passed": False, "checks": ["evidence_count_or_quality"]}
        if open_summary_intent:
            report["decision"] = "clarify"
            report["reason"] = "当前证据不足以支持开放式总结，请先补充一个核心主题线索。"
            report["reason_code"] = "insufficient_evidence_minimal_clarify"
            report["severity"] = "warning"
            report["clarify_questions"] = ["你最关心哪一类主题（方法、实验结果、应用场景）？"]
            report["triggered_rules"].append("insufficient_evidence_minimal_clarify")
            report["output_warnings"].append("insufficient_evidence_minimal_clarify")
            report["constraints_envelope"] = build_constraint_envelope(
                constraint_type="evidence_insufficient",
                reason_code="insufficient_evidence_minimal_clarify",
                severity="warning",
                retryable=True,
                blocking_scope="full_answer",
                user_safe_summary=report["reason"],
                evidence_snapshot={"evidence_groups": len(evidence_grouped)},
                suggested_next_actions=report["clarify_questions"],
                clarify_questions=report["clarify_questions"],
            )
            return _finalize_clarify()
        report["decision"] = "refuse"
        report["reason"] = "证据数量或质量不足，无法可靠回答。"
        report["reason_code"] = "insufficient_evidence_count_or_quality"
        report["severity"] = "high"
        report["guardrail_blocked"] = True
        report["triggered_rules"].append("insufficient_evidence_count_or_quality")
        report["output_warnings"].append("insufficient_evidence_count_or_quality")
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="evidence_insufficient",
            reason_code="insufficient_evidence_count_or_quality",
            severity="high",
            retryable=True,
            blocking_scope="full_answer",
            user_safe_summary=report["reason"],
            evidence_snapshot={"evidence_groups": len(evidence_grouped)},
            suggested_next_actions=["补充论文标题、作者、年份或更明确的问题范围。"],
            guardrail_blocked=True,
        )
        return report

    if not _has_traceable_evidence(evidence_grouped):
        report["decision"] = "refuse"
        report["reason"] = "当前证据缺少可追溯引用，无法稳定进入回答。"
        report["reason_code"] = "traceable_evidence_missing"
        report["severity"] = "high"
        report["guardrail_blocked"] = True
        report["triggered_rules"].append("traceable_evidence_missing")
        report["output_warnings"].append("traceable_evidence_missing")
        report["validator_summary"] = {"passed": False, "checks": ["traceable_evidence_missing"]}
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="evidence_insufficient",
            reason_code="traceable_evidence_missing",
            severity="high",
            retryable=True,
            blocking_scope="full_answer",
            user_safe_summary=report["reason"],
            evidence_snapshot={"evidence_groups": len(evidence_grouped)},
            suggested_next_actions=["补充可追溯的正文证据片段。"],
            guardrail_blocked=True,
        )
        return report

    query_used_text = str(topic_query_text or query_used or "").strip() or question
    judge = judge_semantic_evidence(
        question=question,
        topic_query_text=query_used_text,
        evidence_grouped=evidence_grouped,
        config=config,
    )
    semantic_threshold = judge.get("semantic_threshold")
    report["semantic_policy"] = str(judge.get("semantic_policy") or "balanced")
    report["semantic_threshold"] = float(semantic_threshold if semantic_threshold is not None else 0.25)
    report["missing_aspects"] = [str(x).strip() for x in judge.get("missing_aspects", []) if str(x).strip()]
    report["coverage_summary"] = judge.get("coverage_summary") or {}
    report["judge_source"] = judge.get("judge_source")
    report["judge_status"] = str(judge.get("judge_status") or "ok")
    report["output_warnings"] = [str(x).strip() for x in (judge.get("output_warnings") or []) if str(x).strip()]

    if report["judge_status"] in {"error", "unavailable"}:
        report["decision"] = "refuse"
        report["reason"] = "语义证据判别服务失败，当前无法安全回答。"
        report["reason_code"] = "judge_system_error"
        report["severity"] = "high"
        report["guardrail_blocked"] = True
        report["triggered_rules"].append("judge_system_error")
        report["output_warnings"].append("judge_system_error")
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="semantic_judge_error",
            reason_code="judge_system_error",
            severity="high",
            retryable=True,
            blocking_scope="full_answer",
            user_safe_summary=report["reason"],
            evidence_snapshot={"judge_status": report["judge_status"], "judge_source": report["judge_source"]},
            suggested_next_actions=["稍后重试，或检查 judge 模型配置与 API 可用性。"],
            guardrail_blocked=True,
        )
        return report

    decision_hint = str(judge.get("decision_hint") or "answer")
    if decision_hint == "mismatch":
        if open_summary_intent:
            report["decision"] = "clarify"
            report["reason"] = "证据与当前主题不对齐，请先明确一个优先主题。"
            report["reason_code"] = "topic_mismatch_minimal_clarify"
            report["severity"] = "warning"
            report["clarify_questions"] = ["你想先聚焦哪个主题方向？"]
            report["triggered_rules"].append("topic_mismatch_minimal_clarify")
            report["output_warnings"].append("topic_mismatch_minimal_clarify")
            report["constraints_envelope"] = build_constraint_envelope(
                constraint_type="topic_mismatch",
                reason_code="topic_mismatch_minimal_clarify",
                severity="warning",
                retryable=True,
                blocking_scope="topic_alignment",
                user_safe_summary=report["reason"],
                evidence_snapshot={"coverage_summary": report["coverage_summary"]},
                suggested_next_actions=report["clarify_questions"],
                clarify_questions=report["clarify_questions"],
            )
            return _finalize_clarify()
        report["decision"] = "refuse"
        report["reason"] = "证据与问题主题不匹配，相关性不足。"
        report["reason_code"] = "topic_mismatch"
        report["severity"] = "high"
        report["guardrail_blocked"] = True
        report["triggered_rules"].append("topic_mismatch")
        report["output_warnings"].append("topic_mismatch")
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="topic_mismatch",
            reason_code="topic_mismatch",
            severity="high",
            retryable=True,
            blocking_scope="topic_alignment",
            user_safe_summary=report["reason"],
            evidence_snapshot={"coverage_summary": report["coverage_summary"]},
            suggested_next_actions=["补充论文标题、作者或更明确的主题方向。"],
            guardrail_blocked=True,
        )
        return report

    if decision_hint == "uncertain":
        if open_summary_intent:
            report["decision"] = "answer"
            report["reason"] = "语义判别存在不确定性，将仅输出当前可追溯的主题摘要。"
            report["reason_code"] = "judge_uncertain_partial_summary"
            report["severity"] = "warning"
            report["allows_partial_answer"] = True
            report["triggered_rules"].append("judge_uncertain_partial_summary")
            report["output_warnings"].append("judge_uncertain_partial_summary")
            report["constraints_envelope"] = build_constraint_envelope(
                constraint_type="partial_answer",
                reason_code="judge_uncertain_partial_summary",
                severity="warning",
                retryable=True,
                blocking_scope="full_answer",
                user_safe_summary=report["reason"],
                evidence_snapshot={"coverage_summary": report["coverage_summary"], "judge_status": report["judge_status"]},
                suggested_next_actions=["继续补充更聚焦的主题，或让我只展开其中一个方向。"],
                allows_partial_answer=True,
            )
            return report
        report["decision"] = "clarify"
        report["reason"] = "当前语义证据判别仍不确定，请补充更具体的问题焦点。"
        report["reason_code"] = "judge_uncertain"
        report["severity"] = "warning"
        report["clarify_questions"] = _build_clarify_questions(question, report["missing_aspects"])
        report["triggered_rules"].append("judge_uncertain")
        report["output_warnings"].append("judge_uncertain")
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="semantic_judge_uncertain",
            reason_code="judge_uncertain",
            severity="warning",
            retryable=True,
            blocking_scope="full_answer",
            user_safe_summary=report["reason"],
            evidence_snapshot={"coverage_summary": report["coverage_summary"], "judge_status": report["judge_status"]},
            suggested_next_actions=report["clarify_questions"],
            clarify_questions=report["clarify_questions"],
        )
        return _finalize_clarify()

    if decision_hint == "partial":
        report["decision"] = "answer"
        report["reason"] = "当前证据仅覆盖了问题的一部分，将按可追溯部分回答。"
        report["reason_code"] = "partial_coverage"
        report["severity"] = "warning"
        report["allows_partial_answer"] = True
        report["triggered_rules"].append("partial_coverage")
        report["output_warnings"].append("partial_coverage")
        report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="partial_answer",
            reason_code="partial_coverage",
            severity="warning",
            retryable=True,
            blocking_scope="full_answer",
            user_safe_summary=report["reason"],
            evidence_snapshot={"coverage_summary": report["coverage_summary"]},
            suggested_next_actions=_build_clarify_questions(question, report["missing_aspects"]),
            allows_partial_answer=True,
        )
        return report

    return report
