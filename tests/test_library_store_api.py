from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.kernel_api import app
from app.paper_store import init_paper_store, set_vector_backend_state, upsert_paper, upsert_stage_status, assign_topic


class LibraryStoreApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_library_papers_endpoint_returns_store_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed"
            processed.mkdir(parents=True, exist_ok=True)
            db_path = processed / "paper_store.sqlite3"
            init_paper_store(db_path)
            upsert_paper(
                {
                    "paper_id": "p1",
                    "title": "Paper One",
                    "path": "/data/raw/imported/paper1.pdf",
                    "storage_path": "/data/raw/imported/paper1.pdf",
                    "source_type": "pdf",
                    "source_uri": "pdf://sha1/a",
                    "status": "ready",
                    "imported_at": "2026-04-11T00:00:00Z",
                },
                db_path=db_path,
            )
            upsert_stage_status(paper_id="p1", stage="index", state="succeeded", db_path=db_path)
            assign_topic("专题A", "p1", db_path=db_path)

            with patch("app.kernel_api.ensure_store_current", return_value=db_path):
                response = self.client.get("/api/library/papers")
                detail = self.client.get("/api/library/papers/p1")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload[0]["paper_id"], "p1")
            self.assertEqual(payload[0]["status"], "ready")
            self.assertIn("专题A", payload[0]["topics"])

            self.assertEqual(detail.status_code, 200)
            detail_payload = detail.json()
            self.assertEqual(detail_payload["paper_id"], "p1")
            self.assertTrue(any(item["stage"] == "index" for item in detail_payload["stage_statuses"]))

    def test_import_latest_exposes_papers_and_vector_backend(self) -> None:
        with patch("app.kernel_api.load_papers", return_value=[]), patch("app.kernel_api._load_vector_backend_summary", return_value={"backend_name": "file", "status": "ready", "metadata": {"index_path": "x"}}):
            payload = self.client.get("/api/library/import-latest").json()

        self.assertIn("papers", payload)
        self.assertIn("vector_backend", payload)
        self.assertEqual(payload["vector_backend"]["backend_name"], "file")

    def test_import_latest_recent_items_include_paper_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = base / "runs" / "import_001"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "ingest_report.json").write_text(
                json.dumps(
                    {
                        "import_summary": {"added": 1, "skipped": 0, "failed": 0, "total_candidates": 1},
                        "import_outcomes": [{"paper_id": "p1", "title": "Paper One", "status": "added", "reason": "new_paper"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with (
                patch("app.kernel_api.RUNS_DIR", base / "runs"),
                patch("app.kernel_api.load_papers", return_value=[{"paper_id": "p1"}]),
                patch(
                    "app.kernel_api._load_store_papers",
                    return_value=[{"paper_id": "p1", "title": "Paper One", "status": "ready", "storage_path": "/data/p1.pdf"}],
                ),
                patch("app.kernel_api._load_vector_backend_summary", return_value=None),
                patch("app.kernel_api._read_latest_pipeline_status", return_value=None),
            ):
                payload = self.client.get("/api/library/import-latest").json()

        self.assertEqual(payload["recent_items"][0]["paper_id"], "p1")
        self.assertEqual(payload["recent_items"][0]["paper_status"], "ready")
        self.assertEqual(payload["recent_items"][0]["name"], "Paper One")

    def test_vector_backend_endpoint_uses_store_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed"
            processed.mkdir(parents=True, exist_ok=True)
            db_path = processed / "paper_store.sqlite3"
            init_paper_store(db_path)
            set_vector_backend_state(backend_name="file", status="ready", metadata={"index_path": "data/indexes/vec_index_embed.json"}, db_path=db_path)

            with patch("app.kernel_api.ensure_store_current", return_value=db_path):
                response = self.client.get("/api/library/vector-backend")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["backend_name"], "file")
        self.assertEqual(payload["status"], "ready")

    def test_delete_library_paper_marks_deleted_and_prunes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            processed = base / "processed"
            indexes = base / "indexes"
            processed.mkdir(parents=True, exist_ok=True)
            indexes.mkdir(parents=True, exist_ok=True)
            db_path = processed / "paper_store.sqlite3"
            init_paper_store(db_path)
            upsert_paper(
                {
                    "paper_id": "p1",
                    "title": "Paper One",
                    "path": str(base / "raw" / "paper1.pdf"),
                    "storage_path": str(base / "raw" / "paper1.pdf"),
                    "source_type": "pdf",
                    "source_uri": "pdf://sha1/a",
                    "status": "ready",
                    "imported_at": "2026-04-11T00:00:00Z",
                },
                db_path=db_path,
            )
            upsert_stage_status(paper_id="p1", stage="index", state="succeeded", db_path=db_path)
            assign_topic("专题A", "p1", db_path=db_path)
            (processed / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper One"}], ensure_ascii=False), encoding="utf-8")
            (processed / "chunks.jsonl").write_text(json.dumps({"chunk_id": "p1:1", "paper_id": "p1", "text": "x", "page_start": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
            (processed / "chunks_clean.jsonl").write_text(json.dumps({"chunk_id": "p1:1", "paper_id": "p1", "text": "x", "clean_text": "x", "page_start": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
            (processed / "paper_summary.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper One"}], ensure_ascii=False), encoding="utf-8")
            (processed / "structure_index.json").write_text(json.dumps({"papers": [{"paper_id": "p1", "sections": []}]}, ensure_ascii=False), encoding="utf-8")
            (base / "library_topics.json").write_text(json.dumps({"专题A": ["p1"]}, ensure_ascii=False), encoding="utf-8")

            with patch("app.kernel_api.DATA_DIR", base):
                response = self.client.post("/api/library/papers/p1/delete")
                detail = self.client.get("/api/library/papers/p1")
                listing = self.client.get("/api/library/papers")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "deleted")
            self.assertTrue(payload["vector_backend"]["requires_rebuild"])
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["status"], "deleted")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json(), [])
            self.assertEqual(json.loads((processed / "papers.json").read_text(encoding="utf-8")), [])
            self.assertEqual((processed / "chunks.jsonl").read_text(encoding="utf-8").strip(), "")
            self.assertEqual(json.loads((base / "library_topics.json").read_text(encoding="utf-8")), {})

    def test_retry_library_paper_moves_failed_paper_to_rebuild_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            processed = base / "processed"
            processed.mkdir(parents=True, exist_ok=True)
            db_path = processed / "paper_store.sqlite3"
            init_paper_store(db_path)
            upsert_paper(
                {
                    "paper_id": "p1",
                    "title": "Paper One",
                    "path": str(base / "raw" / "paper1.pdf"),
                    "storage_path": str(base / "raw" / "paper1.pdf"),
                    "source_type": "pdf",
                    "source_uri": "pdf://sha1/a",
                    "status": "failed",
                    "error_message": "index failed",
                    "imported_at": "2026-04-11T00:00:00Z",
                },
                db_path=db_path,
            )
            upsert_stage_status(paper_id="p1", stage="index", state="failed", error_message="index failed", db_path=db_path)

            with patch("app.kernel_api.DATA_DIR", base):
                response = self.client.post("/api/library/papers/p1/retry")
                detail = self.client.get("/api/library/papers/p1")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "rebuild_pending")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["status"], "rebuild_pending")


if __name__ == "__main__":
    unittest.main()
