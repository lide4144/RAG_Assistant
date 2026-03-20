from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import PipelineConfig
from app.evidence_judge import judge_semantic_evidence
from app.sufficiency import run_sufficiency_gate


class SufficiencySemanticPolicyTests(unittest.TestCase):
    def _evidence(self) -> list[dict]:
        return [
            {
                "paper_id": "p1",
                "paper_title": "Transformer",
                "evidence": [
                    {"chunk_id": "p1:1", "quote": "Transformer background discussion.", "content_type": "body"},
                    {"chunk_id": "p1:2", "quote": "General architecture review without metric details.", "content_type": "body"},
                ],
            }
        ]

    def test_policy_threshold_is_exposed_from_llm_judge_output(self) -> None:
        cfg = PipelineConfig()
        cfg.sufficiency_semantic_policy = "explore"
        cfg.sufficiency_semantic_threshold_explore = 0.0
        cfg.sufficiency_judge_use_llm = True
        cfg.sufficiency_judge_llm_api_key_env = "SILICONFLOW_API_KEY"

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "fake-key"}):
            with patch(
                "app.evidence_judge.call_chat_completion",
                return_value=type(
                    "Result",
                    (),
                    {
                        "ok": True,
                        "content": '{"decision_hint":"answer","missing_aspects":[],"covered_aspects":["方法"],"topic_aligned":true,"allows_partial_answer":false,"confidence":"high"}',
                    },
                )(),
            ):
                report = run_sufficiency_gate(
                    question="Transformer deployment boundary",
                    query_used="Transformer deployment boundary",
                    scope_mode="normal",
                    evidence_grouped=self._evidence(),
                    config=cfg,
                )
        self.assertEqual(report.get("semantic_policy"), "explore")
        self.assertEqual(float(report.get("semantic_threshold")), 0.0)
        self.assertEqual(report.get("judge_source"), "semantic_evidence_judge_llm_v1")

    def test_judge_prefers_llm_path_when_available(self) -> None:
        cfg = PipelineConfig()
        cfg.sufficiency_judge_use_llm = True
        cfg.sufficiency_judge_llm_api_key_env = "SILICONFLOW_API_KEY"

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "fake-key"}):
            with patch(
                "app.evidence_judge.call_chat_completion",
                return_value=type(
                    "Result",
                    (),
                    {
                        "ok": True,
                        "content": '{"decision_hint":"partial","missing_aspects":["实验结果"],"covered_aspects":["方法"],"topic_aligned":true,"allows_partial_answer":true,"confidence":"high"}',
                    },
                )(),
            ) as mocked_call:
                report = judge_semantic_evidence(
                    question="请总结方法和实验结果",
                    topic_query_text="方法 实验结果",
                    evidence_grouped=self._evidence(),
                    config=cfg,
                )
        mocked_call.assert_called_once()
        self.assertEqual(report.get("judge_source"), "semantic_evidence_judge_llm_v1")
        self.assertEqual(report.get("decision_hint"), "partial")
        self.assertTrue(report.get("allows_partial_answer"))

    def test_judge_returns_error_when_llm_fails(self) -> None:
        cfg = PipelineConfig()
        cfg.sufficiency_judge_use_llm = True
        cfg.sufficiency_judge_llm_api_key_env = "SILICONFLOW_API_KEY"

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "fake-key"}):
            with patch(
                "app.evidence_judge.call_chat_completion",
                return_value=type("Result", (), {"ok": False, "content": None})(),
            ):
                report = judge_semantic_evidence(
                    question="Transformer architecture",
                    topic_query_text="Transformer architecture",
                    evidence_grouped=self._evidence(),
                    config=cfg,
                )
        self.assertEqual(report.get("judge_source"), "semantic_evidence_judge_llm_v1")
        self.assertEqual(report.get("judge_status"), "error")
        self.assertEqual(report.get("decision_hint"), "uncertain")
        self.assertIn("judge_llm_call_failed", report.get("output_warnings", []))

    def test_sufficiency_gate_blocks_on_judge_system_error(self) -> None:
        cfg = PipelineConfig()
        cfg.sufficiency_judge_use_llm = True
        cfg.sufficiency_judge_llm_api_key_env = "SILICONFLOW_API_KEY"

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "fake-key"}):
            with patch(
                "app.evidence_judge.call_chat_completion",
                return_value=type("Result", (), {"ok": False, "content": None})(),
            ):
                report = run_sufficiency_gate(
                    question="Transformer architecture",
                    query_used="Transformer architecture",
                    scope_mode="normal",
                    evidence_grouped=self._evidence(),
                    config=cfg,
                )
        self.assertEqual(report.get("decision"), "refuse")
        self.assertEqual(report.get("reason_code"), "judge_system_error")
        self.assertEqual(report.get("judge_status"), "error")
        self.assertIn("judge_llm_call_failed", report.get("output_warnings", []))
        self.assertIn("judge_system_error", report.get("output_warnings", []))


if __name__ == "__main__":
    unittest.main()
