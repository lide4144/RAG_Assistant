from __future__ import annotations

import unittest

from app.qa import semantic_route_intent


class IntentSemanticRouterTests(unittest.TestCase):
    def test_semantic_route_detects_continuation_variant(self) -> None:
        intent, confidence, source, params = semantic_route_intent("沿着刚才那个问题继续讲下去")
        self.assertEqual(intent, "continuation_control")
        self.assertEqual(source, "semantic_model")
        self.assertGreater(confidence, 0.5)
        self.assertTrue(params.get("continuation"))

    def test_semantic_route_extracts_format_params(self) -> None:
        intent, confidence, source, params = semantic_route_intent("能改成 markdown 表格展示吗")
        self.assertEqual(intent, "format_control")
        self.assertEqual(source, "semantic_model")
        self.assertGreater(confidence, 0.5)
        self.assertEqual(params.get("format"), "table")


if __name__ == "__main__":
    unittest.main()
