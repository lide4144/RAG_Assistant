from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
        if force_partial_answer_on_limit and clarify_streak_before_turn >= clarify_limit:
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
            updated_questions = ["你更希望我先展开哪一部分（方法、实验结果或应用场景）？"]
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
        if "assistant_summary_clarify_limit_force_partial_answer" not in triggered_rules:
            triggered_rules.append("assistant_summary_clarify_limit_force_partial_answer")
        sufficiency_gate["triggered_rules"] = triggered_rules

    return AssistantModeDecisionPolicyResult(
        decision=decision,
        decision_reason=decision_reason,
        clarify_questions=updated_questions,
        assistant_mode_used=assistant_mode_used,
        clarify_limit_hit=clarify_limit_hit,
        forced_partial_answer=forced_partial_answer,
    )


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
