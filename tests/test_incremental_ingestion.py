from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.models import ChunkRecord, PageText
from app.web_ingest import UrlIngestResult


class IncrementalIngestionTests(unittest.TestCase):
    def _args(
        self,
        input_dir: Path | None,
        out_dir: Path,
        *,
        urls: list[str] | None = None,
        run_dir: Path | None = None,
    ) -> Namespace:
        return Namespace(
            input=str(input_dir) if input_dir else None,
            out=str(out_dir),
            config="configs/default.yaml",
            question=None,
            clean=False,
            run_id="",
            run_dir=str(run_dir) if run_dir else "",
            lock_timeout_sec=10.0,
            url=list(urls or []),
            url_file=None,
        )

    def test_same_pdf_content_imported_twice_keeps_single_paper(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_a = base / "in_a"
            in_b = base / "in_b"
            out_dir = base / "out"
            in_a.mkdir(parents=True, exist_ok=True)
            in_b.mkdir(parents=True, exist_ok=True)
            (in_a / "first.pdf").write_bytes(b"%PDF-same-content")
            (in_b / "second.pdf").write_bytes(b"%PDF-same-content")

            def _build_chunks(paper_id: str, pages: list[PageText], chunk_size: int, overlap: int) -> list[ChunkRecord]:
                return [ChunkRecord(chunk_id=f"{paper_id}:00001", paper_id=paper_id, page_start=1, text="hello")]

            common_patches = (
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello")], [], "T")),
                patch("app.ingest.extract_title", return_value="Demo PDF"),
                patch("app.ingest.build_chunks", side_effect=_build_chunks),
            )

            with common_patches[0], common_patches[1], common_patches[2]:
                code1 = run_ingest(self._args(in_a, out_dir))
            with common_patches[0], common_patches[1], common_patches[2]:
                code2 = run_ingest(self._args(in_b, out_dir))

            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            papers = json.loads((out_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 1)
            self.assertTrue(str(papers[0].get("paper_id", "")).startswith("pdf_"))

    def test_new_pdf_is_merged_without_losing_history(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_a = base / "in_a"
            in_b = base / "in_b"
            out_dir = base / "out"
            in_a.mkdir(parents=True, exist_ok=True)
            in_b.mkdir(parents=True, exist_ok=True)
            (in_a / "a.pdf").write_bytes(b"%PDF-content-a")
            (in_b / "b.pdf").write_bytes(b"%PDF-content-b")

            def _build_chunks(paper_id: str, pages: list[PageText], chunk_size: int, overlap: int) -> list[ChunkRecord]:
                return [ChunkRecord(chunk_id=f"{paper_id}:00001", paper_id=paper_id, page_start=1, text=paper_id)]

            with (
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello")], [], "T")),
                patch("app.ingest.extract_title", return_value="Demo PDF"),
                patch("app.ingest.build_chunks", side_effect=_build_chunks),
            ):
                code1 = run_ingest(self._args(in_a, out_dir))
                code2 = run_ingest(self._args(in_b, out_dir))

            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            papers = json.loads((out_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 2)

    def test_same_url_with_different_content_marked_as_conflict(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out_dir = base / "out"
            run1 = base / "run1"
            run2 = base / "run2"
            args1 = self._args(None, out_dir, urls=["https://example.com/paper"], run_dir=run1)
            args2 = self._args(None, out_dir, urls=["https://example.com/paper"], run_dir=run2)

            def _build_chunks(paper_id: str, pages: list[PageText], chunk_size: int, overlap: int) -> list[ChunkRecord]:
                return [ChunkRecord(chunk_id=f"{paper_id}:00001", paper_id=paper_id, page_start=1, text=pages[0].text)]

            first = UrlIngestResult(
                ok=True,
                url="https://example.com/paper",
                title="T1",
                text="A" * 200,
                fetched_at="2026-02-28T00:00:00+00:00",
                http_status=200,
            )
            second = UrlIngestResult(
                ok=True,
                url="https://example.com/paper",
                title="T1",
                text="B" * 200,
                fetched_at="2026-02-28T00:01:00+00:00",
                http_status=200,
            )

            with patch("app.ingest.build_chunks", side_effect=_build_chunks), patch(
                "app.ingest.fetch_url_document", side_effect=[first, second]
            ):
                code1 = run_ingest(args1)
                code2 = run_ingest(args2)

            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            self.assertTrue((out_dir / "papers.json").exists())
            papers = json.loads((out_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 1)
            latest_report = json.loads((run2 / "ingest_report.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(int(latest_report.get("import_summary", {}).get("conflicts", 0)), 1)


if __name__ == "__main__":
    unittest.main()
