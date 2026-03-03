from __future__ import annotations

import unittest

from scripts.eval_research_assistant_workflow import evaluate


class ResearchAssistantWorkflowEvalTests(unittest.TestCase):
    def test_evaluate_completion_rate_and_first_card_time(self) -> None:
        events = [
            {"session_id": "s1", "action": "import_success", "count": 5, "ts": 0},
            {"session_id": "s1", "action": "ask_question", "ts": 30},
            {"session_id": "s1", "action": "save_idea_card", "ts": 90},
            {"session_id": "s2", "action": "import_success", "count": 3, "ts": 0},
            {"session_id": "s2", "action": "ask_question", "ts": 10},
        ]
        report = evaluate(events)
        self.assertEqual(report["sessions_total"], 2)
        self.assertEqual(report["sessions_completed"], 1)
        self.assertAlmostEqual(report["completion_rate"], 0.5)
        self.assertEqual(report["avg_first_card_seconds"], 90.0)


if __name__ == "__main__":
    unittest.main()
