from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import app.library as library


class LibraryQuickIngestionTests(unittest.TestCase):
    def test_import_feedback_uses_user_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            with patch.object(library, "run_ingest", return_value=0), patch.object(
                library, "run_build_indexes", return_value=0
            ):
                result = library.run_import_workflow(uploaded_files=[pdf], topic="专题A")

            self.assertTrue(result["ok"])
            message = str(result.get("message", "")).lower()
            self.assertNotIn("chunk", message)
            self.assertNotIn("index", message)
            self.assertNotIn("build", message)
            self.assertIn("导入", str(result.get("message", "")))
            self.assertIsInstance(result.get("next_steps"), list)
            self.assertGreaterEqual(len(result.get("next_steps", [])), 1)

    def test_import_feedback_accepts_text_like_local_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "note.txt"
            txt.write_text("Plain text document", encoding="utf-8")

            with patch.object(library, "run_ingest", return_value=0), patch.object(
                library, "run_build_indexes", return_value=0
            ):
                result = library.run_import_workflow(uploaded_files=[txt], topic="专题A")

            self.assertTrue(result["ok"])
            self.assertEqual(result["success_count"], 1)
            self.assertEqual(result["failed_count"], 0)

    def test_import_feedback_includes_classification_and_index_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            def _fake_ingest(args) -> int:
                run_dir = Path(str(args.run_dir))
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "ingest_report.json").write_text(
                    '{"import_summary":{"added":1,"skipped":2,"conflicts":0,"failed":0},"import_outcomes":[]}',
                    encoding="utf-8",
                )
                return 0

            with patch.object(library, "run_ingest", side_effect=_fake_ingest), patch.object(
                library, "run_build_indexes", return_value=0
            ), patch("app.library.uuid.uuid4", return_value=uuid.UUID("00000000-0000-0000-0000-000000000001")):
                result = library.run_import_workflow(uploaded_files=[pdf], topic="")

            self.assertTrue(result["ok"])
            self.assertEqual(result.get("import_summary", {}).get("added"), 1)
            self.assertEqual(result.get("import_summary", {}).get("skipped"), 2)
            self.assertEqual(result.get("index_stage", {}).get("status"), "success")

    def test_import_feedback_keeps_stage_updated_at_when_index_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            def _fake_ingest(args) -> int:
                run_dir = Path(str(args.run_dir))
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "ingest_report.json").write_text(
                    '{"import_summary":{"added":1,"skipped":0,"conflicts":0,"failed":0},"import_outcomes":[]}',
                    encoding="utf-8",
                )
                return 0

            with patch.object(library, "run_ingest", side_effect=_fake_ingest), patch.object(
                library, "file_lock", side_effect=library.FileLockTimeoutError("busy")
            ):
                result = library.run_import_workflow(uploaded_files=[pdf], topic="")

            self.assertFalse(result["ok"])
            self.assertEqual(result.get("index_stage", {}).get("status"), "conflict")
            self.assertIn("updated_at", result.get("import_stage", {}))
            self.assertIn("updated_at", result.get("clean_stage", {}))
            self.assertIn("updated_at", result.get("index_stage", {}))

    def test_import_workflow_emits_batch_progress_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")
            events: list[dict] = []

            def _fake_ingest(args) -> int:
                run_dir = Path(str(args.run_dir))
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "ingest_report.json").write_text(
                    json.dumps(
                        {
                            "import_summary": {"added": 1, "skipped": 0, "conflicts": 0, "failed": 0, "total_candidates": 1},
                            "import_outcomes": [{"source_uri": str(pdf), "status": "added"}],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return 0

            with patch.object(library, "run_ingest", side_effect=_fake_ingest), patch.object(
                library, "run_build_indexes", return_value=0
            ):
                result = library.run_import_workflow(uploaded_files=[pdf], topic="", progress_callback=events.append)

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(len(events), 4)
            final_event = events[-1]
            self.assertEqual(final_event["batch_total"], 1)
            self.assertEqual(final_event["batch_completed"], 1)
            self.assertEqual(final_event["batch_failed"], 0)
            self.assertEqual(final_event["stage"], "done")
            self.assertEqual(final_event["recent_items"][0]["state"], "succeeded")

    def test_import_workflow_accepts_document_progress_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "note.txt"
            txt.write_text("Plain text document", encoding="utf-8")
            events: list[dict] = []

            def _fake_ingest(args) -> int:
                args.progress_callback(
                    {
                        "event": "document_started",
                        "paper_name": txt.name,
                        "pdf_completed": 0,
                        "pdf_failed": 0,
                    }
                )
                args.progress_callback(
                    {
                        "event": "document_finished",
                        "paper_name": txt.name,
                        "pdf_completed": 1,
                        "pdf_failed": 0,
                        "status": "parsed",
                        "reason": "base_only",
                    }
                )
                run_dir = Path(str(args.run_dir))
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "ingest_report.json").write_text(
                    json.dumps(
                        {
                            "import_summary": {"added": 1, "skipped": 0, "conflicts": 0, "failed": 0, "total_candidates": 1},
                            "import_outcomes": [{"source_uri": str(txt), "status": "added"}],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return 0

            with patch.object(library, "run_ingest", side_effect=_fake_ingest), patch.object(
                library, "run_build_indexes", return_value=0
            ):
                result = library.run_import_workflow(uploaded_files=[txt], topic="", progress_callback=events.append)

            self.assertTrue(result["ok"])
            self.assertTrue(any(event.get("current_item_name") == txt.name for event in events))
            self.assertTrue(any("正在解析" in str(event.get("message", "")) for event in events))

    def test_import_workflow_returns_success_for_controlled_skip_only_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rtf = Path(tmp) / "empty.rtf"
            rtf.write_text("", encoding="utf-8")

            def _fake_ingest(args) -> int:
                run_dir = Path(str(args.run_dir))
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "ingest_report.json").write_text(
                    json.dumps(
                        {
                            "import_summary": {"added": 0, "skipped": 1, "conflicts": 0, "failed": 0, "total_candidates": 1, "controlled_skip": True},
                            "import_outcomes": [{"title": rtf.name, "status": "skipped", "reason": "no readable rtf text"}],
                            "confidence_note": "当前导入结果包含按文件类型受控跳过的条目，请检查文件格式支持与抽取结果。",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return 0

            with patch.object(library, "run_ingest", side_effect=_fake_ingest), patch.object(
                library, "run_build_indexes", return_value=0
            ) as build_indexes:
                result = library.run_import_workflow(uploaded_files=[rtf], topic="")

            self.assertTrue(result["ok"])
            self.assertEqual(result.get("import_summary", {}).get("skipped"), 1)
            self.assertIn("受控跳过", str(result.get("message", "")))
            build_indexes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
