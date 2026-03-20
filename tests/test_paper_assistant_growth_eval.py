from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.eval_paper_assistant_growth import (
    EvalSample,
    RunRow,
    StrategyMetrics,
    decision_from_report,
    evaluate_gates,
    render_report,
    summarize,
    validate_comparable_configs,
)


class PaperAssistantGrowthEvalTests(unittest.TestCase):
    def test_decision_source_prefers_final_user_visible_posture(self) -> None:
        report = {"decision": "clarify", "final_decision": "answer_with_evidence", "final_user_visible_posture": "execute"}
        self.assertEqual(decision_from_report(report), "answer")

        report = {"decision": "answer", "final_user_visible_posture": "partial_answer"}
        self.assertEqual(decision_from_report(report), "answer")

        report = {"decision": "answer", "final_user_visible_posture": "clarify"}
        self.assertEqual(decision_from_report(report), "clarify")

        report = {"decision": "refuse", "final_decision": "answer_with_evidence"}
        self.assertEqual(decision_from_report(report), "refuse")

    def test_config_comparable_allows_only_legacy_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            legacy = base / "legacy.yaml"
            growth = base / "growth.yaml"
            legacy.write_text(
                "assistant_mode_force_legacy_gate: true\n"
                "assistant_mode_enabled: true\n"
                "intent_router_enabled: true\n",
                encoding="utf-8",
            )
            growth.write_text(
                "assistant_mode_force_legacy_gate: false\n"
                "assistant_mode_enabled: true\n"
                "intent_router_enabled: true\n",
                encoding="utf-8",
            )
            ok, errors, _, _ = validate_comparable_configs(legacy, growth)
            self.assertTrue(ok)
            self.assertEqual(errors, [])

            growth.write_text(
                "assistant_mode_force_legacy_gate: false\n"
                "assistant_mode_enabled: false\n"
                "intent_router_enabled: true\n",
                encoding="utf-8",
            )
            ok2, errors2, _, _ = validate_comparable_configs(legacy, growth)
            self.assertFalse(ok2)
            self.assertTrue(any("assistant_mode_enabled" in err for err in errors2))

    def test_growth_gate_pass_and_fail_cases(self) -> None:
        samples = [
            EvalSample("A1", "a", 1, "q", "A_open_summary", True, False),
            EvalSample("A2", "a2", 1, "q", "A_open_summary", True, False),
            EvalSample("B1", "b", 1, "q", "B_multi_turn", True, False),
            EvalSample("B2", "b", 2, "q", "B_multi_turn", True, False),
            EvalSample("B3", "b", 3, "q", "B_multi_turn", True, False),
            EvalSample("C1", "c", 1, "q", "C_control_mixed", False, False),
            EvalSample("D1", "d", 1, "q", "D_ooc", False, True),
        ]

        legacy_rows = [
            RunRow("legacy", samples[0], "r1", "refuse", "", [], 0, False, "sufficiency_gate", "retrieval_query", "user_query"),
            RunRow("legacy", samples[1], "r2", "refuse", "", [], 0, False, "sufficiency_gate", "retrieval_query", "user_query"),
            RunRow("legacy", samples[2], "r3", "clarify", "", [], 1, False, None, "retrieval_query", "user_query"),
            RunRow("legacy", samples[3], "r4", "clarify", "", [], 2, False, None, "retrieval_query", "user_query"),
            RunRow("legacy", samples[4], "r5", "refuse", "", [], 2, False, "sufficiency_gate", "retrieval_query", "user_query"),
            RunRow("legacy", samples[5], "r6", "clarify", "", [], 0, False, None, "style_control", "user_query"),
            RunRow("legacy", samples[6], "r7", "refuse", "", [], 0, False, "sufficiency_gate", "retrieval_query", "user_query"),
        ]

        growth_rows_pass = [
            RunRow("growth", samples[0], "r1", "answer", "ok", [{"chunk_id": "c1"}], 0, False, None, "retrieval_query", "user_query"),
            RunRow("growth", samples[1], "r2", "answer", "ok", [{"chunk_id": "c2"}], 0, False, None, "retrieval_query", "user_query"),
            RunRow("growth", samples[2], "r3", "clarify", "", [], 1, False, None, "retrieval_query", "user_query"),
            RunRow("growth", samples[3], "r4", "answer", "ok", [{"chunk_id": "c3"}], 1, False, None, "retrieval_query", "user_query"),
            RunRow("growth", samples[4], "r5", "answer", "低置信", [{"chunk_id": "c4"}], 1, True, None, "retrieval_query", "user_query"),
            RunRow("growth", samples[5], "r6", "answer", "ok", [{"chunk_id": "c5"}], 0, False, None, "retrieval_query", "anchor_query"),
            RunRow("growth", samples[6], "r7", "refuse", "", [], 0, False, "sufficiency_gate", "retrieval_query", "user_query"),
        ]

        legacy_metrics: StrategyMetrics = summarize(legacy_rows)
        growth_metrics_pass: StrategyMetrics = summarize(growth_rows_pass)
        ok, errors = evaluate_gates(legacy_metrics, growth_metrics_pass)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

        growth_rows_fail = list(growth_rows_pass)
        growth_rows_fail[0] = RunRow(
            "growth", samples[0], "r1", "refuse", "", [], 0, False, "sufficiency_gate", "retrieval_query", "user_query"
        )
        growth_metrics_fail: StrategyMetrics = summarize(growth_rows_fail)
        ok2, errors2 = evaluate_gates(legacy_metrics, growth_metrics_fail)
        self.assertFalse(ok2)
        self.assertGreaterEqual(len(errors2), 1)

    def test_render_report_includes_spoken_dataset_section(self) -> None:
        base_sample = EvalSample("A1", "s1", 1, "q", "A_open_summary", True, False)
        legacy_metrics = summarize(
            [RunRow("legacy", base_sample, "r1", "refuse", "", [], 0, False, "sufficiency_gate", "retrieval_query", "user_query")]
        )
        growth_metrics = summarize(
            [RunRow("growth", base_sample, "r2", "answer", "ok", [{"chunk_id": "c1"}], 0, False, None, "retrieval_query", "user_query")]
        )
        report = render_report(
            legacy_cfg="configs/paper_assistant_growth_legacy.yaml",
            growth_cfg="configs/paper_assistant_growth.yaml",
            samples_path="reports/paper_assistant_questions_v1.jsonl",
            legacy_metrics=legacy_metrics,
            growth_metrics=growth_metrics,
            gate_ok=True,
            gate_errors=[],
            config_errors=[],
            spoken_samples_path="reports/paper_assistant_questions_spoken_v1.jsonl",
            spoken_legacy_metrics=legacy_metrics,
            spoken_growth_metrics=growth_metrics,
            spoken_gate_ok=False,
            spoken_gate_errors=["spoken gate fail"],
            enforce_spoken_gate=False,
        )
        self.assertIn("## 口语问题集对比", report)
        self.assertIn("口语问题集: `reports/paper_assistant_questions_spoken_v1.jsonl`", report)
        self.assertIn("口语门禁是否阻断发布: 否（观测项）", report)


if __name__ == "__main__":
    unittest.main()
