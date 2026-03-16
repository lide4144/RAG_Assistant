from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.planner_shadow_review import save_shadow_review


class PlannerShadowReviewTests(unittest.TestCase):
    def test_save_shadow_review_persists_all_allowed_labels(self) -> None:
        labels = ("llm_better", "rule_better", "tie", "both_bad")

        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            for idx, label in enumerate(labels, start=1):
                payload = save_shadow_review(
                    trace_id=f"trace-{idx}",
                    label=label,
                    reviewer="qa-reviewer",
                    notes=f"review for {label}",
                    planner_source_mode="shadow_compare",
                    base_dir=base_dir,
                )
                self.assertEqual(payload["label"], label)
                latest_path = base_dir / "planner_shadow_reviews" / f"trace-{idx}.json"
                self.assertTrue(latest_path.exists())
                stored = json.loads(latest_path.read_text(encoding="utf-8"))
                self.assertEqual(stored["label"], label)
                self.assertEqual(stored["reviewer"], "qa-reviewer")
                self.assertEqual(stored["planner_source_mode"], "shadow_compare")

            history_path = base_dir / "planner_shadow_reviews" / "reviews.jsonl"
            self.assertTrue(history_path.exists())
            history_rows = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([row["label"] for row in history_rows], list(labels))


if __name__ == "__main__":
    unittest.main()
