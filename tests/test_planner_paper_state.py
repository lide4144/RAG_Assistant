"""Tests for Planner paper state awareness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.paper_store import (
    ensure_store_current,
    init_paper_store,
    list_papers,
    upsert_paper,
    update_paper,
)
from app.planner_policy import (
    filter_papers_by_lifecycle_status,
    categorize_papers_by_status,
    build_paper_status_summary,
    PAPER_READY_STATUSES,
)
from app.capability_planner import execute_catalog_lookup


class PlannerPaperStateTests(unittest.TestCase):
    def test_filter_papers_by_lifecycle_status_ready(self) -> None:
        papers = [
            {"paper_id": "p1", "status": "ready"},
            {"paper_id": "p2", "status": "failed"},
            {"paper_id": "p3", "status": "rebuild_pending"},
        ]
        ready_papers = filter_papers_by_lifecycle_status(
            papers, include_statuses={"ready"}
        )
        self.assertEqual(len(ready_papers), 1)
        self.assertEqual(ready_papers[0]["paper_id"], "p1")

    def test_categorize_papers_by_status(self) -> None:
        papers = [
            {"paper_id": "p1", "status": "ready"},
            {"paper_id": "p2", "status": "failed"},
            {"paper_id": "p3", "status": "rebuild_pending"},
            {"paper_id": "p4", "status": "parse"},  # Processing status
        ]
        categories = categorize_papers_by_status(papers)
        self.assertEqual(len(categories["ready"]), 1)
        self.assertEqual(len(categories["failed"]), 1)
        self.assertEqual(len(categories["rebuild_pending"]), 1)
        self.assertEqual(len(categories["processing"]), 1)
        self.assertEqual(len(categories["other"]), 0)

    def test_build_paper_status_summary(self) -> None:
        papers = [
            {"paper_id": "p1", "status": "ready", "title": "Paper 1"},
            {
                "paper_id": "p2",
                "status": "failed",
                "title": "Paper 2",
                "error_message": "Parse error",
            },
            {"paper_id": "p3", "status": "rebuild_pending", "title": "Paper 3"},
        ]
        summary = build_paper_status_summary(papers)
        self.assertEqual(summary["total_count"], 3)
        self.assertEqual(summary["ready_count"], 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["rebuild_pending_count"], 1)
        self.assertEqual(len(summary["failed_details"]), 1)
        self.assertEqual(summary["failed_details"][0]["error_message"], "Parse error")

    def test_execute_catalog_lookup_with_status_filter(self) -> None:
        # This test verifies the status_filter parameter is accepted
        # Actual filtering depends on database availability
        result = execute_catalog_lookup(
            query="NonExistentPaper12345",
            max_papers=10,
            status_filter="ready",
        )

        # Should be short_circuit since no papers match
        self.assertEqual(result["status_filter"], "ready")
        self.assertIn("status_summary", result)

    def test_execute_catalog_lookup_fallback_on_empty(self) -> None:
        # This test verifies empty results handling
        result = execute_catalog_lookup(
            query="NonExistentPaper12345",
            max_papers=10,
            status_filter="ready",
        )

        # Check status filter is recorded
        self.assertEqual(result["status_filter"], "ready")


if __name__ == "__main__":
    unittest.main()
