from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.ideas import can_transition, create_draft, list_cards, save_card, update_card_status


class IdeaCardTests(unittest.TestCase):
    def test_card_save_and_status_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "ideas_cards.json"
            draft = create_draft(
                title="想法A",
                research_question="问题A",
                method_outline="方法A",
                next_experiments=["实验1"],
                evidence=[{"chunk_id": "c:1", "paper_id": "p1", "section_page": "p.1", "quote": "证据"}],
                source_session_id="s-1",
                source_turn_idx=0,
                topic="专题A",
            )
            saved = save_card(draft, store)
            self.assertEqual(saved.get("status"), "draft")
            cards = list_cards(store)
            self.assertEqual(len(cards), 1)

            ok, err = update_card_status(str(saved["card_id"]), "shortlisted", store)
            self.assertTrue(ok)
            self.assertEqual(err, "")
            cards2 = list_cards(store)
            self.assertEqual(cards2[0].get("status"), "shortlisted")

    def test_status_transition_must_follow_flow(self) -> None:
        self.assertTrue(can_transition("draft", "shortlisted"))
        self.assertFalse(can_transition("draft", "validated"))


if __name__ == "__main__":
    unittest.main()
