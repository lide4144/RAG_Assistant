from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FINAL_INTERACTION_AUTHORITIES = {"planner", "planner_policy"}
FINAL_USER_VISIBLE_POSTURES = {
    "execute",
    "clarify",
    "partial_answer",
    "refuse",
    "delegate",
}
CONSTRAINT_SEVERITIES = {"info", "warning", "high"}

# Paper lifecycle statuses that indicate a paper is ready for retrieval/QA
PAPER_READY_STATUSES = {"ready"}
PAPER_FAILED_STATUSES = {"failed"}
PAPER_REBUILD_PENDING_STATUSES = {"rebuild_pending"}
PAPER_PROCESSING_STATUSES = {
    "dedup",
    "import",
    "parse",
    "clean",
    "index",
    "graph_build",
}


@dataclass(frozen=True)
class AssistantModeDecisionPolicyResult:
    decision: str
    decision_reason: str
    clarify_questions: list[str]
    assistant_mode_used: bool
    clarify_limit_hit: bool
    forced_partial_answer: bool


@dataclass(frozen=True)
class AssistantModeClarifyOverride:
    applied: bool
    decision: str
    decision_reason: str
    clarify_questions: list[str]
    answer: str | None
    answer_citations: list[dict[str, Any]] | None
    final_refuse_source: str | None


@dataclass(frozen=True)
class FinalInteractionDecision:
    decision: str
    user_visible_posture: str
    final_interaction_authority: str
    interaction_decision_source: str
    decision_reason: str
    clarify_questions: list[str]
    final_refuse_source: str | None
    guardrail_blocked: bool
    posture_override_forbidden: bool
    kernel_constraint_summary: list[dict[str, Any]]


def build_constraint_envelope(
    *,
    constraint_type: str,
    reason_code: str,
    severity: str,
    retryable: bool,
    blocking_scope: str,
    user_safe_summary: str,
    evidence_snapshot: dict[str, Any] | None = None,
    citation_status: str | None = None,
    failed_dependency: str | None = None,
    suggested_next_actions: list[str] | None = None,
    guardrail_blocked: bool = False,
    allows_partial_answer: bool = False,
    clarify_questions: list[str] | None = None,
) -> dict[str, Any]:
    normalized_severity = str(severity or "warning").strip().lower()
    if normalized_severity not in CONSTRAINT_SEVERITIES:
        normalized_severity = "warning"
    return {
        "constraint_type": str(constraint_type or "unspecified").strip()
        or "unspecified",
        "reason_code": str(reason_code or "unspecified").strip() or "unspecified",
        "severity": normalized_severity,
        "retryable": bool(retryable),
        "blocking_scope": str(blocking_scope or "response").strip() or "response",
        "user_safe_summary": str(user_safe_summary or "").strip(),
        "evidence_snapshot": dict(evidence_snapshot or {}),
        "citation_status": str(citation_status or "not_evaluated").strip()
        or "not_evaluated",
        "failed_dependency": (
            str(failed_dependency).strip() if failed_dependency else None
        ),
        "suggested_next_actions": [
            str(item).strip()
            for item in list(suggested_next_actions or [])
            if str(item).strip()
        ],
        "guardrail_blocked": bool(guardrail_blocked),
        "allows_partial_answer": bool(allows_partial_answer),
        "clarify_questions": [
            str(item).strip()
            for item in list(clarify_questions or [])
            if str(item).strip()
        ][:1],
    }


def summarize_constraint_envelopes(
    envelopes: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for envelope in list(envelopes or []):
        if not isinstance(envelope, dict):
            continue
        row = {
            "constraint_type": str(
                envelope.get("constraint_type") or "unspecified"
            ).strip()
            or "unspecified",
            "reason_code": str(envelope.get("reason_code") or "unspecified").strip()
            or "unspecified",
            "severity": str(envelope.get("severity") or "warning").strip() or "warning",
            "guardrail_blocked": bool(envelope.get("guardrail_blocked", False)),
            "blocking_scope": str(envelope.get("blocking_scope") or "response").strip()
            or "response",
        }
        if row not in rows:
            rows.append(row)
    return rows


def resolve_final_interaction_decision(
    *,
    planner_result: Any,
    proposed_decision: str,
    decision_reason: str,
    clarify_questions: list[str],
    final_refuse_source: str | None,
    constraint_envelopes: list[dict[str, Any]] | None = None,
    forced_partial_answer: bool = False,
    posture_override_forbidden: bool = False,
) -> FinalInteractionDecision:
    decision = str(proposed_decision or "answer").strip() or "answer"
    source = "planner_policy:default"
    guardrail_blocked = any(
        bool(item.get("guardrail_blocked", False))
        for item in list(constraint_envelopes or [])
        if isinstance(item, dict)
    )
    if (
        getattr(planner_result, "decision_result", "") == "clarify"
        and decision == "clarify"
    ):
        source = "planner:clarify"
    elif final_refuse_source == "evidence_policy_gate":
        source = "planner_policy:evidence_policy_gate"
    elif final_refuse_source == "sufficiency_gate":
        source = "planner_policy:sufficiency_gate"
    elif decision == "clarify":
        source = "planner_policy:clarify"
    elif forced_partial_answer:
        source = "planner_policy:partial_answer"
    elif getattr(planner_result, "decision_result", "") in {
        "delegate_web",
        "delegate_research_assistant",
    }:
        source = f"planner:{getattr(planner_result, 'decision_result', 'delegate')}"
    else:
        source = "planner:execute"

    if decision == "clarify":
        posture = "clarify"
    elif decision == "refuse":
        posture = "refuse"
    elif getattr(planner_result, "decision_result", "") in {
        "delegate_web",
        "delegate_research_assistant",
    }:
        posture = "delegate"
    elif forced_partial_answer:
        posture = "partial_answer"
    else:
        posture = "execute"

    authority = "planner" if source.startswith("planner:") else "planner_policy"
    return FinalInteractionDecision(
        decision=decision,
        user_visible_posture=posture,
        final_interaction_authority=authority,
        interaction_decision_source=source,
        decision_reason=str(decision_reason or "").strip(),
        clarify_questions=[
            str(item).strip()
            for item in list(clarify_questions or [])
            if str(item).strip()
        ][:1],
        final_refuse_source=(
            str(final_refuse_source).strip() if final_refuse_source else None
        ),
        guardrail_blocked=guardrail_blocked,
        posture_override_forbidden=bool(posture_override_forbidden),
        kernel_constraint_summary=summarize_constraint_envelopes(constraint_envelopes),
    )


def apply_assistant_mode_decision_policy(
    *,
    assistant_mode_enabled: bool,
    open_summary_intent: bool,
    assistant_mode_force_legacy_gate: bool,
    decision: str,
    clarify_questions: list[str],
    sufficiency_gate: dict[str, Any],
    force_partial_answer_on_limit: bool,
    clarify_streak_before_turn: int,
    clarify_limit: int,
) -> AssistantModeDecisionPolicyResult:
    assistant_mode_used = False
    clarify_limit_hit = bool(sufficiency_gate.get("clarify_limit_hit", False))
    forced_partial_answer = bool(sufficiency_gate.get("forced_partial_answer", False))
    decision_reason = str(sufficiency_gate.get("reason", "")).strip()
    updated_questions = list(clarify_questions)

    if (
        assistant_mode_enabled
        and open_summary_intent
        and not assistant_mode_force_legacy_gate
        and decision == "refuse"
    ):
        assistant_mode_used = True
        if (
            force_partial_answer_on_limit
            and clarify_streak_before_turn >= clarify_limit
        ):
            decision = "answer"
            decision_reason = "助理模式下连续澄清达到上限，改为低置信可追溯回答。"
            clarify_limit_hit = True
            forced_partial_answer = True
            updated_questions = []
            triggered_rules = list(sufficiency_gate.get("triggered_rules", []) or [])
            if "assistant_mode_refuse_forced_partial_answer" not in triggered_rules:
                triggered_rules.append("assistant_mode_refuse_forced_partial_answer")
            sufficiency_gate["triggered_rules"] = triggered_rules
            sufficiency_gate["decision"] = "answer"
            sufficiency_gate["reason"] = decision_reason
            sufficiency_gate["clarify_questions"] = []
            sufficiency_gate["clarify_limit_hit"] = True
            sufficiency_gate["forced_partial_answer"] = True
        else:
            decision = "clarify"
            decision_reason = "助理模式下优先最小澄清而非直接拒答。"
            updated_questions = [
                "你更希望我先展开哪一部分（方法、实验结果或应用场景）？"
            ]
            sufficiency_gate["decision"] = "clarify"
            sufficiency_gate["reason"] = decision_reason
            sufficiency_gate["clarify_questions"] = list(updated_questions)
            sufficiency_gate["clarify_limit_hit"] = clarify_limit_hit
            sufficiency_gate["forced_partial_answer"] = forced_partial_answer

    if (
        assistant_mode_enabled
        and open_summary_intent
        and not assistant_mode_force_legacy_gate
        and decision == "answer"
        and force_partial_answer_on_limit
        and clarify_streak_before_turn >= clarify_limit
        and not forced_partial_answer
    ):
        clarify_limit_hit = True
        forced_partial_answer = True
        sufficiency_gate["clarify_limit_hit"] = True
        sufficiency_gate["forced_partial_answer"] = True
        triggered_rules = list(sufficiency_gate.get("triggered_rules", []) or [])
        if (
            "assistant_summary_clarify_limit_force_partial_answer"
            not in triggered_rules
        ):
            triggered_rules.append(
                "assistant_summary_clarify_limit_force_partial_answer"
            )
        sufficiency_gate["triggered_rules"] = triggered_rules

    return AssistantModeDecisionPolicyResult(
        decision=decision,
        decision_reason=decision_reason,
        clarify_questions=updated_questions,
        assistant_mode_used=assistant_mode_used,
        clarify_limit_hit=clarify_limit_hit,
        forced_partial_answer=forced_partial_answer,
    )


def filter_papers_by_lifecycle_status(
    papers: list[dict[str, Any]],
    *,
    include_statuses: set[str] | None = None,
    exclude_statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter papers by their lifecycle status.

    Args:
        papers: List of paper dictionaries
        include_statuses: Only include papers with these statuses (default: ready papers)
        exclude_statuses: Exclude papers with these statuses

    Returns:
        Filtered list of papers
    """
    if include_statuses is None:
        include_statuses = PAPER_READY_STATUSES

    filtered = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        status = str(paper.get("status", "")).strip().lower()

        if exclude_statuses and status in exclude_statuses:
            continue
        if include_statuses and status not in include_statuses:
            continue
        filtered.append(paper)

    return filtered


def categorize_papers_by_status(
    papers: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Categorize papers by their lifecycle status.

    Args:
        papers: List of paper dictionaries

    Returns:
        Dictionary with status categories as keys
    """
    categories: dict[str, list[dict[str, Any]]] = {
        "ready": [],
        "failed": [],
        "rebuild_pending": [],
        "processing": [],
        "other": [],
    }

    for paper in papers:
        if not isinstance(paper, dict):
            continue
        status = str(paper.get("status", "")).strip().lower()

        if status in PAPER_READY_STATUSES:
            categories["ready"].append(paper)
        elif status in PAPER_FAILED_STATUSES:
            categories["failed"].append(paper)
        elif status in PAPER_REBUILD_PENDING_STATUSES:
            categories["rebuild_pending"].append(paper)
        elif status in PAPER_PROCESSING_STATUSES:
            categories["processing"].append(paper)
        else:
            categories["other"].append(paper)

    return categories


def build_paper_status_summary(
    papers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a summary of paper statuses for planner observability.

    Args:
        papers: List of paper dictionaries

    Returns:
        Summary dictionary with counts and details
    """
    categories = categorize_papers_by_status(papers)

    failed_details = [
        {
            "paper_id": p.get("paper_id"),
            "title": p.get("title"),
            "error_message": p.get("error_message", ""),
        }
        for p in categories["failed"]
    ]

    rebuild_pending_details = [
        {
            "paper_id": p.get("paper_id"),
            "title": p.get("title"),
        }
        for p in categories["rebuild_pending"]
    ]

    return {
        "total_count": len(papers),
        "ready_count": len(categories["ready"]),
        "failed_count": len(categories["failed"]),
        "rebuild_pending_count": len(categories["rebuild_pending"]),
        "processing_count": len(categories["processing"]),
        "other_count": len(categories["other"]),
        "failed_details": failed_details,
        "rebuild_pending_details": rebuild_pending_details,
    }


def prefer_assistant_mode_clarify(
    *,
    assistant_mode_used: bool,
    clarify_limit_hit: bool,
    decision: str,
    refuse_reason: str,
    final_refuse_source: str | None,
) -> AssistantModeClarifyOverride:
    if not assistant_mode_used or clarify_limit_hit:
        return AssistantModeClarifyOverride(
            applied=False,
            decision=decision,
            decision_reason=refuse_reason,
            clarify_questions=[],
            answer=None,
            answer_citations=None,
            final_refuse_source=final_refuse_source,
        )
    clarify_questions = ["你更希望我先展开哪一部分（方法、实验结果或应用场景）？"]
    return AssistantModeClarifyOverride(
        applied=True,
        decision="clarify",
        decision_reason=f"{refuse_reason} 助理模式下优先最小澄清。",
        clarify_questions=clarify_questions,
        answer="为确保回答基于充分证据，请先澄清以下问题：\n1. " + clarify_questions[0],
        answer_citations=[],
        final_refuse_source=None,
    )
