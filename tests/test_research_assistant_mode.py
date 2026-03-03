from __future__ import annotations

import unittest

from app.qa import _build_assistant_summary_answer, _filter_candidates_by_topic
from app.retrieve import RetrievalCandidate


class ResearchAssistantModeTests(unittest.TestCase):
    def test_topic_scope_filters_candidates(self) -> None:
        candidates = [
            RetrievalCandidate(chunk_id="c1", score=1.0, paper_id="p1"),
            RetrievalCandidate(chunk_id="c2", score=0.9, paper_id="p2"),
        ]
        kept, dropped = _filter_candidates_by_topic(candidates, {"p2"})
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].paper_id, "p2")
        self.assertEqual(dropped, 1)

    def test_assistant_summary_answer_has_three_blocks(self) -> None:
        answer, citations, suggestions, ready = _build_assistant_summary_answer(
            question="请给我研究灵感",
            evidence_grouped=[
                {
                    "paper_id": "p1",
                    "paper_title": "Paper One",
                    "evidence": [{"chunk_id": "c1", "section_page": "p.1", "quote": "method and result"}],
                },
                {
                    "paper_id": "p2",
                    "paper_title": "Paper Two",
                    "evidence": [{"chunk_id": "c2", "section_page": "p.2", "quote": "experiment details"}],
                },
                {
                    "paper_id": "p3",
                    "paper_title": "Paper Three",
                    "evidence": [{"chunk_id": "c3", "section_page": "p.3", "quote": "future work"}],
                },
            ],
            min_topics=3,
        )
        self.assertTrue(ready)
        self.assertGreaterEqual(len(citations), 3)
        self.assertIn("主题", answer)
        self.assertIn("建议下一步追问", answer)
        self.assertGreaterEqual(len(suggestions), 1)


if __name__ == "__main__":
    unittest.main()
