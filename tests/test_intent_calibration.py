from __future__ import annotations

import unittest

from app.intent_calibration import calibrate_query_intent, strip_summary_cues


class IntentCalibrationTests(unittest.TestCase):
    def test_strip_summary_cues(self) -> None:
        query, removed = strip_summary_cues("this work paper overview in summary")
        self.assertNotIn("overview", query.lower())
        self.assertNotIn("summary", query.lower())
        self.assertTrue(removed)

    def test_calibration_adds_limitation_cues(self) -> None:
        result = calibrate_query_intent(
            question="这篇论文有哪些局限和未来工作？",
            rewritten_query="这篇论文有哪些局限和未来工作？",
            keywords_entities={"keywords": ["局限"], "entities": []},
            scope_mode="rewrite_scope",
            scope_reason={"has_paper_clue": False},
        )
        text = result.calibrated_query.lower()
        self.assertIn("limitations", text)
        self.assertIn("未来工作", result.calibrated_query)
        self.assertIn("limitation", result.calibration_reason["matched_intents"])
        self.assertEqual(result.calibration_reason["keywords_entities"]["keywords"], ["局限"])

    def test_calibration_without_intent_keeps_query(self) -> None:
        query = "What does this paper say"
        result = calibrate_query_intent(
            question=query,
            rewritten_query=query,
            keywords_entities={"keywords": [], "entities": []},
            scope_mode="open",
            scope_reason={"has_paper_clue": True},
        )
        self.assertIn("rule", result.calibration_reason)
        self.assertEqual(result.calibration_reason["matched_intents"], [])


if __name__ == "__main__":
    unittest.main()
