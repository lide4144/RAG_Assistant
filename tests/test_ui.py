from __future__ import annotations

import unittest

from app.ui import (
    _apply_session_reset_history_guard,
    _assistant_mode_inspector_lines,
    _build_citation_slots,
    _decision_alert_kind,
    _source_badge_html,
)


class UITests(unittest.TestCase):
    def test_build_citation_slots_marks_unmapped_citations_invalid(self) -> None:
        slots = _build_citation_slots("答案见 [1] 和 [3]", [{"chunk_id": "c:1"}])
        self.assertEqual(slots, [{"citation_idx": 1, "valid": True}, {"citation_idx": 3, "valid": False}])

    def test_source_badge_highlights_graph_expand(self) -> None:
        badge = _source_badge_html("graph_expand")
        self.assertIn("graph_expand", badge)
        self.assertIn("#f97316", badge)

    def test_decision_alert_kind_for_refuse_and_clarify(self) -> None:
        self.assertEqual(_decision_alert_kind("refuse"), "error")
        self.assertEqual(_decision_alert_kind("clarify"), "warning")
        self.assertIsNone(_decision_alert_kind("answer"))

    def test_apply_session_reset_history_guard_adds_warning_on_leak(self) -> None:
        report, warn = _apply_session_reset_history_guard(
            {"history_used_turns": 2, "output_warnings": []},
            expect_zero_history_turn=True,
        )
        self.assertIsNotNone(warn)
        self.assertIn("session_reset_history_leak_suspected", report.get("output_warnings", []))

    def test_assistant_mode_inspector_lines_include_limit_fields(self) -> None:
        lines = _assistant_mode_inspector_lines(
            {
                "assistant_mode_used": True,
                "clarify_count": 2,
                "clarify_limit_hit": True,
                "forced_partial_answer": True,
            },
            {},
        )
        rendered = "\n".join(lines)
        self.assertIn("clarify_limit_hit", rendered)
        self.assertIn("forced_partial_answer", rendered)
        self.assertIn("`True`", rendered)


if __name__ == "__main__":
    unittest.main()
