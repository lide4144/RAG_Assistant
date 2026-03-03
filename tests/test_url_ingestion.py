from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.models import ChunkRecord
from app.web_ingest import UrlIngestResult
from app.web_ingest import fetch_url_document


class UrlIngestionTests(unittest.TestCase):
    def _build_args(
        self,
        *,
        input_dir: Path | None,
        output_dir: Path,
        url_list: list[str] | None = None,
        url_file: str | None = None,
    ) -> Namespace:
        return Namespace(
            input=str(input_dir) if input_dir else None,
            out=str(output_dir),
            config="configs/default.yaml",
            question=None,
            clean=False,
            url=list(url_list or []),
            url_file=url_file,
        )

    def test_url_only_ingestion_writes_compatible_paper_mapping(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "out"
            run_dir = base / "runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            args = self._build_args(input_dir=None, output_dir=out, url_list=["https://mp.weixin.qq.com/s/demo"])

            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch(
                    "app.ingest.fetch_url_document",
                    return_value=UrlIngestResult(
                        ok=True,
                        url="https://mp.weixin.qq.com/s/demo",
                        title="公众号文章标题",
                        text="正文内容" * 100,
                        fetched_at="2026-02-27T00:00:00+00:00",
                        http_status=200,
                    ),
                ),
                patch(
                    "app.ingest.build_chunks",
                    return_value=[
                        ChunkRecord(
                            chunk_id="u:00001",
                            paper_id="u",
                            page_start=1,
                            text="正文内容",
                        )
                    ],
                ),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 0)
            papers = json.loads((out / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 1)
            self.assertEqual(papers[0]["source_type"], "url")
            self.assertEqual(papers[0]["source_uri"], "https://mp.weixin.qq.com/s/demo")
            self.assertEqual(papers[0]["path"], "https://mp.weixin.qq.com/s/demo")
            self.assertIn("ingest_metadata", papers[0])

    def test_mixed_inputs_skip_invalid_url_and_keep_pdf(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            out = base / "out"
            run_dir = base / "runs"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = input_dir / "a.pdf"

            args = self._build_args(
                input_dir=input_dir,
                output_dir=out,
                url_list=["not-a-url", "https://example.com/a"],
            )

            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([], [], None)),
                patch(
                    "app.ingest.fetch_url_document",
                    return_value=UrlIngestResult(
                        ok=False,
                        url="https://example.com/a",
                        title="",
                        text="",
                        fetched_at="2026-02-27T00:00:00+00:00",
                        http_status=403,
                        error_code="access_restricted",
                        error_message="http_error:403",
                    ),
                ),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 1)
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            reasons = [r.get("reason") for r in report["url_invalid_or_failed"]]
            self.assertIn("invalid_url", reasons)
            self.assertIn("access_restricted", reasons)

    def test_url_file_can_drive_batch_ingestion(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "out"
            run_dir = base / "runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            url_file = base / "urls.txt"
            url_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "https://example.com/1",
                        "https://example.com/1",
                        "invalid",
                        "https://example.com/2",
                    ]
                ),
                encoding="utf-8",
            )
            args = self._build_args(input_dir=None, output_dir=out, url_file=str(url_file))

            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch(
                    "app.ingest.fetch_url_document",
                    side_effect=[
                        UrlIngestResult(
                            ok=True,
                            url="https://example.com/1",
                            title="T1",
                            text="A" * 200,
                            fetched_at="2026-02-27T00:00:00+00:00",
                            http_status=200,
                        ),
                        UrlIngestResult(
                            ok=True,
                            url="https://example.com/2",
                            title="T2",
                            text="B" * 200,
                            fetched_at="2026-02-27T00:00:01+00:00",
                            http_status=200,
                        ),
                    ],
                ),
                patch(
                    "app.ingest.build_chunks",
                    side_effect=[
                        [ChunkRecord(chunk_id="p1:1", paper_id="p1", page_start=1, text="A")],
                        [ChunkRecord(chunk_id="p2:1", paper_id="p2", page_start=1, text="B")],
                    ],
                ),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 0)
            papers = json.loads((out / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 2)
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("url_total"), 2)
            self.assertTrue(any(item.get("reason") == "invalid_url" for item in report.get("url_invalid_or_failed", [])))

    def test_fetch_url_document_marks_empty_body_as_structured_failure(self) -> None:
        class _Resp:
            status = 200

            class headers:
                @staticmethod
                def get_content_charset():
                    return "utf-8"

            def read(self):
                return b"<html><head><title>T</title></head><body>too short</body></html>"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        with patch("app.web_ingest.request.urlopen", return_value=_Resp()):
            result = fetch_url_document("https://example.com/empty", min_text_chars=50)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "empty_content")


if __name__ == "__main__":
    unittest.main()
