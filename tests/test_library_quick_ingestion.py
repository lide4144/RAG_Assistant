from __future__ import annotations

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

    def test_import_feedback_contains_structured_failure_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "note.txt"
            txt.write_text("not pdf", encoding="utf-8")
            result = library.run_import_workflow(uploaded_files=[txt], topic="专题A")
            self.assertFalse(result["ok"])
            self.assertEqual(result["success_count"], 0)
            self.assertEqual(result["failed_count"], 1)
            reasons = result.get("failure_reasons", [])
            self.assertTrue(reasons)
            self.assertIn("仅支持 PDF", str(reasons[0]))
            self.assertTrue(result.get("next_steps"))

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


if __name__ == "__main__":
    unittest.main()
