from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.paper_store import ensure_store_current, list_papers, load_topics, sync_store_from_exports


class PaperStoreTests(unittest.TestCase):
    def test_sync_store_repairs_temp_path_and_exports_stable_papers_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            processed = base / "processed"
            raw_imported = base / "raw" / "imported"
            indexes = base / "indexes"
            processed.mkdir(parents=True, exist_ok=True)
            raw_imported.mkdir(parents=True, exist_ok=True)
            indexes.mkdir(parents=True, exist_ok=True)

            stable_pdf = raw_imported / "paper.pdf"
            stable_pdf.write_bytes(b"%PDF-1.4 stable")
            fingerprint = hashlib.sha1(stable_pdf.read_bytes()).hexdigest()

            (processed / "papers.json").write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "p1",
                            "title": "Paper One",
                            "path": "/tmp/tmp123/input/paper.pdf",
                            "source_type": "pdf",
                            "source_uri": f"pdf://sha1/{fingerprint}",
                            "imported_at": "2026-04-11T00:00:00Z",
                            "status": "active",
                            "fingerprint": fingerprint,
                            "ingest_metadata": {"file_name": "paper.pdf"},
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (processed / "chunks.jsonl").write_text(
                json.dumps({"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "text": "hello"}) + "\n",
                encoding="utf-8",
            )
            (processed / "chunks_clean.jsonl").write_text(
                json.dumps({"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "text": "hello", "clean_text": "hello"}) + "\n",
                encoding="utf-8",
            )
            (processed / "paper_summary.json").write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "p1",
                            "title": "Paper One",
                            "one_paragraph_summary": "summary",
                            "key_points": ["summary"],
                            "keywords": ["paper"],
                            "source_uri": f"pdf://sha1/{fingerprint}",
                            "summary_version": "v1",
                            "chunk_snapshot_hash": "snap-1",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (processed / "structure_index.json").write_text(
                json.dumps(
                    {
                        "papers": [
                            {
                                "paper_id": "p1",
                                "structure_parse_status": "ready",
                                "structure_parse_reason": "",
                                "sections": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (base / "library_topics.json").write_text(json.dumps({"专题A": ["p1"]}, ensure_ascii=False, indent=2), encoding="utf-8")
            (indexes / "bm25_index.json").write_text("{}", encoding="utf-8")

            store_path = sync_store_from_exports(
                processed_dir=processed,
                topics_path=base / "library_topics.json",
                stable_source_path_by_fingerprint={fingerprint: str(stable_pdf)},
            )

            rows = list_papers(db_path=store_path, limit=10, include_stage_statuses=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["storage_path"], str(stable_pdf))
            self.assertEqual(rows[0]["path"], str(stable_pdf))
            self.assertEqual(rows[0]["status"], "ready")
            self.assertIn("专题A", rows[0]["topics"])
            self.assertTrue(any(item["stage"] == "index" for item in rows[0]["stage_statuses"]))

            exported = json.loads((processed / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(exported[0]["storage_path"], str(stable_pdf))
            self.assertEqual(exported[0]["path"], str(stable_pdf))

    def test_ensure_store_current_bootstraps_from_existing_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            processed = base / "processed"
            processed.mkdir(parents=True, exist_ok=True)
            (processed / "papers.json").write_text(
                json.dumps(
                    [{"paper_id": "p1", "title": "Paper One", "path": "paper.pdf", "source_type": "pdf", "source_uri": "paper.pdf"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (base / "library_topics.json").write_text(json.dumps({"专题A": ["p1"]}, ensure_ascii=False), encoding="utf-8")

            store_path = ensure_store_current(processed_dir=processed, topics_path=base / "library_topics.json")

            self.assertTrue(store_path.exists())
            self.assertEqual(load_topics(db_path=store_path), {"专题A": ["p1"]})


if __name__ == "__main__":
    unittest.main()
