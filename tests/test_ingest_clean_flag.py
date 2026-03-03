from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.models import ChunkRecord, PageText


class IngestCleanFlagTests(unittest.TestCase):
    def _build_args(self, input_dir: Path, output_dir: Path, clean: bool) -> Namespace:
        return Namespace(
            input=str(input_dir),
            out=str(output_dir),
            config="configs/default.yaml",
            question=None,
            clean=clean,
        )

    def test_default_mode_does_not_trigger_clean(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_dir = base / "out"
            run_dir = base / "runs_case1"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)

            fake_pdf = input_dir / "a.pdf"
            args = self._build_args(input_dir, output_dir, clean=False)
            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch("app.ingest.list_pdf_files", return_value=[fake_pdf]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello world")], [], None)),
                patch("app.ingest.extract_title", return_value="Demo"),
                patch(
                    "app.ingest.build_chunks",
                    return_value=[
                        ChunkRecord(
                            chunk_id="paper-a:00001",
                            paper_id="paper-a",
                            page_start=1,
                            text="hello world",
                        )
                    ],
                ),
                patch("app.ingest.run_clean_chunks") as clean_mock,
            ):
                code = run_ingest(args)

            self.assertEqual(code, 0)
            self.assertFalse(clean_mock.called)
            self.assertTrue((output_dir / "chunks.jsonl").exists())
            self.assertFalse((output_dir / "chunks_clean.jsonl").exists())
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["clean_enabled"])
            self.assertIsNone(report["clean_output"])
            self.assertFalse(report["clean_success"])
            self.assertIsNone(report["clean_error"])

    def test_clean_mode_generates_chunks_clean_jsonl(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_dir = base / "out"
            run_dir = base / "runs_case2"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)

            fake_pdf = input_dir / "a.pdf"
            args = self._build_args(input_dir, output_dir, clean=True)
            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch("app.ingest.list_pdf_files", return_value=[fake_pdf]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello world")], [], None)),
                patch("app.ingest.extract_title", return_value="Demo"),
                patch(
                    "app.ingest.build_chunks",
                    return_value=[
                        ChunkRecord(
                            chunk_id="paper-a:00001",
                            paper_id="paper-a",
                            page_start=1,
                            text="hello world",
                        )
                    ],
                ),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "chunks.jsonl").exists())
            self.assertTrue((output_dir / "chunks_clean.jsonl").exists())
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["clean_enabled"])
            self.assertEqual(report["clean_output"], str(output_dir / "chunks_clean.jsonl"))
            self.assertTrue(report["clean_success"])
            self.assertIsNone(report["clean_error"])

    def test_clean_failure_does_not_break_ingest_success(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_dir = base / "out"
            run_dir = base / "runs_case3"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)

            fake_pdf = input_dir / "a.pdf"
            args = self._build_args(input_dir, output_dir, clean=True)
            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch("app.ingest.list_pdf_files", return_value=[fake_pdf]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello world")], [], None)),
                patch("app.ingest.extract_title", return_value="Demo"),
                patch(
                    "app.ingest.build_chunks",
                    return_value=[
                        ChunkRecord(
                            chunk_id="paper-a:00001",
                            paper_id="paper-a",
                            page_start=1,
                            text="hello world",
                        )
                    ],
                ),
                patch("app.ingest.run_clean_chunks", side_effect=RuntimeError("clean boom")),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "chunks.jsonl").exists())
            self.assertTrue((output_dir / "papers.json").exists())
            self.assertFalse((output_dir / "chunks_clean.jsonl").exists())
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["clean_enabled"])
            self.assertEqual(report["clean_output"], str(output_dir / "chunks_clean.jsonl"))
            self.assertFalse(report["clean_success"])
            self.assertEqual(report["clean_error"], "clean boom")

    def test_main_prints_clean_stage_status_for_success_and_failure(self) -> None:
        from app.ingest import main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_ok = base / "out_ok"
            output_fail = base / "out_fail"
            run_ok = base / "runs_ok"
            run_fail = base / "runs_fail"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_ok.mkdir(parents=True, exist_ok=True)
            run_fail.mkdir(parents=True, exist_ok=True)

            fake_pdf = input_dir / "a.pdf"
            common_patches = (
                patch("app.ingest.list_pdf_files", return_value=[fake_pdf]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello world")], [], None)),
                patch("app.ingest.extract_title", return_value="Demo"),
                patch(
                    "app.ingest.build_chunks",
                    return_value=[
                        ChunkRecord(
                            chunk_id="paper-a:00001",
                            paper_id="paper-a",
                            page_start=1,
                            text="hello world",
                        )
                    ],
                ),
            )

            out_stdout_ok = io.StringIO()
            out_stderr_ok = io.StringIO()
            with (
                patch("app.ingest.create_run_dir", return_value=run_ok),
                common_patches[0],
                common_patches[1],
                common_patches[2],
                common_patches[3],
                common_patches[4],
                redirect_stdout(out_stdout_ok),
                redirect_stderr(out_stderr_ok),
            ):
                code_ok = main(
                    ["--input", str(input_dir), "--out", str(output_ok), "--clean"]
                )

            self.assertEqual(code_ok, 0)
            self.assertIn(
                f"Clean output: {output_ok / 'chunks_clean.jsonl'}",
                out_stdout_ok.getvalue(),
            )

            out_stdout_fail = io.StringIO()
            out_stderr_fail = io.StringIO()
            with (
                patch("app.ingest.create_run_dir", return_value=run_fail),
                common_patches[0],
                common_patches[1],
                common_patches[2],
                common_patches[3],
                common_patches[4],
                patch("app.ingest.run_clean_chunks", side_effect=RuntimeError("clean boom")),
                redirect_stdout(out_stdout_fail),
                redirect_stderr(out_stderr_fail),
            ):
                code_fail = main(
                    ["--input", str(input_dir), "--out", str(output_fail), "--clean"]
                )

            self.assertEqual(code_fail, 0)
            self.assertIn(
                "Clean output: failed (see ingest report)",
                out_stdout_fail.getvalue(),
            )


if __name__ == "__main__":
    unittest.main()
