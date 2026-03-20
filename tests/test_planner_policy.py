from __future__ import annotations

import unittest

from types import SimpleNamespace

from app.planner_policy import (
    apply_assistant_mode_decision_policy,
    build_constraint_envelope,
    prefer_assistant_mode_clarify,
    resolve_final_interaction_decision,
)


class PlannerPolicyTests(unittest.TestCase):
    def test_assistant_mode_refuse_becomes_clarify_before_limit(self) -> None:
        sufficiency_gate = {
            "decision": "refuse",
            "reason": "evidence too weak",
            "clarify_questions": [],
            "clarify_limit_hit": False,
            "forced_partial_answer": False,
            "triggered_rules": [],
        }

        result = apply_assistant_mode_decision_policy(
            assistant_mode_enabled=True,
            open_summary_intent=True,
            assistant_mode_force_legacy_gate=False,
            decision="refuse",
            clarify_questions=[],
            sufficiency_gate=sufficiency_gate,
            force_partial_answer_on_limit=True,
            clarify_streak_before_turn=0,
            clarify_limit=2,
        )

        self.assertEqual(result.decision, "clarify")
        self.assertTrue(result.assistant_mode_used)
        self.assertEqual(result.clarify_questions, ["你更希望我先展开哪一部分（方法、实验结果或应用场景）？"])
        self.assertEqual(sufficiency_gate["decision"], "clarify")

    def test_assistant_mode_refuse_becomes_forced_partial_answer_at_limit(self) -> None:
        sufficiency_gate = {
            "decision": "refuse",
            "reason": "evidence too weak",
            "clarify_questions": [],
            "clarify_limit_hit": False,
            "forced_partial_answer": False,
            "triggered_rules": [],
        }

        result = apply_assistant_mode_decision_policy(
            assistant_mode_enabled=True,
            open_summary_intent=True,
            assistant_mode_force_legacy_gate=False,
            decision="refuse",
            clarify_questions=[],
            sufficiency_gate=sufficiency_gate,
            force_partial_answer_on_limit=True,
            clarify_streak_before_turn=2,
            clarify_limit=2,
        )

        self.assertEqual(result.decision, "answer")
        self.assertTrue(result.clarify_limit_hit)
        self.assertTrue(result.forced_partial_answer)
        self.assertIn("assistant_mode_refuse_forced_partial_answer", sufficiency_gate["triggered_rules"])

    def test_prefer_assistant_mode_clarify_returns_structured_override(self) -> None:
        result = prefer_assistant_mode_clarify(
            assistant_mode_used=True,
            clarify_limit_hit=False,
            decision="refuse",
            refuse_reason="关键结论缺少可追溯证据，触发证据门控。",
            final_refuse_source="evidence_policy_gate",
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.decision, "clarify")
        self.assertEqual(result.answer_citations, [])
        self.assertIsNone(result.final_refuse_source)

    def test_resolve_final_interaction_decision_emits_partial_answer_contract(self) -> None:
        planner_result = SimpleNamespace(decision_result="local_execute")
        constraint = build_constraint_envelope(
            constraint_type="partial_answer",
            reason_code="clarify_limit_reached_force_partial_answer",
            severity="warning",
            retryable=True,
            blocking_scope="full_answer",
            user_safe_summary="连续澄清达到上限。",
            allows_partial_answer=True,
        )
        result = resolve_final_interaction_decision(
            planner_result=planner_result,
            proposed_decision="answer",
            decision_reason="连续澄清达到上限，改为低置信可追溯回答。",
            clarify_questions=[],
            final_refuse_source=None,
            constraint_envelopes=[constraint],
            forced_partial_answer=True,
        )

        self.assertEqual(result.user_visible_posture, "partial_answer")
        self.assertEqual(result.final_interaction_authority, "planner_policy")
        self.assertEqual(result.interaction_decision_source, "planner_policy:partial_answer")
        self.assertEqual(result.kernel_constraint_summary[0]["reason_code"], "clarify_limit_reached_force_partial_answer")


if __name__ == "__main__":
    unittest.main()
