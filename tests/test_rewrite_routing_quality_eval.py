from __future__ import annotations

import unittest

from scripts.eval_rewrite_routing_quality import evaluate_samples


class RewriteRoutingQualityEvalTests(unittest.TestCase):
    def test_evaluate_samples_passes_when_thresholds_met(self) -> None:
        samples = [
            {
                "id": "s1",
                "query": "沿着刚才那个问题继续讲下去",
                "expected_intent": "continuation_control",
                "entities": [],
            },
            {
                "id": "s2",
                "query": "BERT 在 GLUE 上表现如何？",
                "expected_intent": "retrieval_query",
                "entities": ["BERT", "GLUE"],
            },
        ]
        result = evaluate_samples(samples, rewrite_entity_keep_rate_min=0.5, route_accuracy_min=0.5)
        self.assertTrue(result["passed"])
        self.assertEqual(result["alerts"], [])
        self.assertGreaterEqual(float(result["route_accuracy"]), 0.5)

    def test_evaluate_samples_emits_alerts_when_thresholds_not_met(self) -> None:
        samples = [
            {
                "id": "s1",
                "query": "普通检索问题",
                "expected_intent": "style_control",
                "entities": ["BERT"],
                "baseline_query": "普通检索问题",
            }
        ]
        result = evaluate_samples(samples, rewrite_entity_keep_rate_min=1.0, route_accuracy_min=1.0)
        self.assertFalse(result["passed"])
        self.assertTrue(result["alerts"])
        joined = " ".join(result["alerts"])
        self.assertIn("route_accuracy_below_threshold", joined)


if __name__ == "__main__":
    unittest.main()
