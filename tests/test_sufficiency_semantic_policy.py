from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import PipelineConfig
from app.sufficiency import run_sufficiency_gate


class SufficiencySemanticPolicyTests(unittest.TestCase):
    def _evidence(self) -> list[dict]:
        return [
            {
                "paper_id": "p1",
                "paper_title": "Transformer",
                "evidence": [
                    {"quote": "General literature review and related work section.", "content_type": "body"},
                    {"quote": "Background discussion without concrete method details.", "content_type": "body"},
                ],
            }
        ]

    def test_policy_threshold_switches_decision(self) -> None:
        cfg_strict = PipelineConfig()
        cfg_strict.embedding.enabled = False
        cfg_strict.sufficiency_topic_match_threshold = 0.95
        cfg_strict.sufficiency_semantic_policy = "strict"
        cfg_strict.sufficiency_semantic_threshold_strict = 0.75
        cfg_strict.sufficiency_semantic_threshold_balanced = 0.2
        cfg_strict.sufficiency_semantic_threshold_explore = 0.1

        strict_report = run_sufficiency_gate(
            question="这篇论文是什么",
            query_used="这篇论文是什么",
            scope_mode="normal",
            evidence_grouped=self._evidence(),
            config=cfg_strict,
        )
        self.assertEqual(strict_report.get("semantic_policy"), "strict")
        self.assertIn(strict_report.get("decision"), {"refuse", "clarify"})

        cfg_explore = PipelineConfig()
        cfg_explore.embedding.enabled = False
        cfg_explore.sufficiency_topic_match_threshold = 0.95
        cfg_explore.sufficiency_semantic_policy = "explore"
        cfg_explore.sufficiency_semantic_threshold_strict = 0.75
        cfg_explore.sufficiency_semantic_threshold_balanced = 0.2
        cfg_explore.sufficiency_semantic_threshold_explore = 0.0

        explore_report = run_sufficiency_gate(
            question="这篇论文是什么",
            query_used="这篇论文是什么",
            scope_mode="normal",
            evidence_grouped=self._evidence(),
            config=cfg_explore,
        )
        self.assertEqual(explore_report.get("semantic_policy"), "explore")
        self.assertEqual(explore_report.get("decision"), "answer")

    def test_embedding_semantic_path_used_when_enabled(self) -> None:
        cfg = PipelineConfig()
        cfg.embedding.enabled = True
        cfg.embedding.api_key_env = "SILICONFLOW_API_KEY"
        cfg.embedding.base_url = "https://api.siliconflow.cn/v1"
        cfg.embedding.model = "BAAI/bge-large-zh-v1.5"
        cfg.sufficiency_topic_match_threshold = 0.95
        cfg.sufficiency_semantic_policy = "explore"
        cfg.sufficiency_semantic_threshold_explore = 0.0

        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "fake-key"}):
            with patch(
                "app.sufficiency.fetch_embeddings",
                return_value=[[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
            ) as mocked_fetch:
                report = run_sufficiency_gate(
                    question="这篇论文是什么",
                    query_used="这篇论文是什么",
                    scope_mode="normal",
                    evidence_grouped=self._evidence(),
                    config=cfg,
                )
        mocked_fetch.assert_called_once()
        self.assertGreater(float(report.get("semantic_similarity_score") or 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
