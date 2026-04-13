from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from app.fs_utils import FileLockTimeoutError
from app.models import ChunkRecord, PageText, PaperRecord
from app.paper_store import list_papers
from app.paths import CONFIGS_DIR, DATA_DIR, RUNS_DIR
from app.writer import validate_chunks_jsonl, write_chunks_jsonl, write_papers_json


class WriterHardeningTests(unittest.TestCase):
    def test_validate_chunks_jsonl_fail_fast_and_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chunks.jsonl"
            lines = [
                json.dumps({"chunk_id": "c1", "paper_id": "p1", "page_start": "bad", "text": "x"}, ensure_ascii=False),
                json.dumps({"chunk_id": None, "paper_id": "p1", "page_start": 1, "text": "x"}, ensure_ascii=False),
                json.dumps({"chunk_id": "c3", "paper_id": "", "page_start": 1, "text": "x"}, ensure_ascii=False),
                json.dumps({"chunk_id": "c4", "paper_id": "p1", "page_start": 0, "text": ""}, ensure_ascii=False),
                "{bad json",
                json.dumps({"chunk_id": "c6", "paper_id": "p1", "page_start": 2, "text": "x"}, ensure_ascii=False),
            ]
            path.write_text("\n".join(lines), encoding="utf-8")
            ok, errors = validate_chunks_jsonl(path, max_errors=5)
            self.assertFalse(ok)
            self.assertTrue(any("stopping after 5 errors" in e for e in errors))

    def test_write_chunks_jsonl_atomic_keeps_previous_file_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "chunks.jsonl"
            output.write_text('{"old":"ok"}\n', encoding="utf-8")

            class _BadChunk:
                def __init__(self, raise_error: bool) -> None:
                    self.raise_error = raise_error

                def to_dict(self) -> dict[str, object]:
                    if self.raise_error:
                        raise ValueError("boom")
                    return {"chunk_id": "c1", "paper_id": "p1", "page_start": 1, "text": "x"}

            with self.assertRaises(RuntimeError):
                write_chunks_jsonl([_BadChunk(False), _BadChunk(True)], output)
            self.assertEqual(output.read_text(encoding="utf-8"), '{"old":"ok"}\n')

    def test_write_papers_json_streams_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            rows = (
                PaperRecord(paper_id=f"p{i}", title=f"title-{i}", path=f"/tmp/{i}.pdf")
                for i in range(2)
            )
            write_papers_json(rows, output)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["paper_id"], "p0")


class IngestLockTests(unittest.TestCase):
    def test_ingest_returns_conflict_on_lock_timeout(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_dir = base / "out"
            run_dir = base / "run"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            fake_pdf = input_dir / "a.pdf"

            args = Namespace(
                input=str(input_dir),
                out=str(output_dir),
                config=str(CONFIGS_DIR / "default.yaml"),
                question=None,
                clean=False,
                run_id="",
                run_dir=str(run_dir),
                lock_timeout_sec=0.01,
            )

            @contextmanager
            def _lock_timeout(*_args, **_kwargs):
                raise FileLockTimeoutError("timeout")
                yield

            err = io.StringIO()
            with (
                patch("app.ingest.list_local_document_files", return_value=[fake_pdf]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello")], [], None)),
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
                patch("app.ingest.file_lock", _lock_timeout),
                redirect_stderr(err),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 3)
            self.assertIn("Another import/index process is active", err.getvalue())

    def test_ingest_prefers_stable_source_override_for_store_and_compat_exports(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_dir = base / "out"
            run_dir = base / "run"
            raw_dir = base / "raw" / "imported"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            raw_dir.mkdir(parents=True, exist_ok=True)

            temp_doc = input_dir / "note.txt"
            stable_doc = raw_dir / "note.txt"
            temp_doc.write_text("Transformer retrieval pipeline details", encoding="utf-8")
            stable_doc.write_text("Transformer retrieval pipeline details", encoding="utf-8")

            args = Namespace(
                input=str(input_dir),
                out=str(output_dir),
                config=str(CONFIGS_DIR / "default.yaml"),
                question=None,
                clean=False,
                run_id="",
                run_dir=str(run_dir),
                lock_timeout_sec=0.01,
                source_path_overrides={
                    str(temp_doc): str(stable_doc),
                    str(temp_doc.resolve()): str(stable_doc.resolve()),
                },
            )

            code = run_ingest(args)

            self.assertEqual(code, 0)
            rows = list_papers(db_path=output_dir / "paper_store.sqlite3", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["storage_path"], str(stable_doc.resolve()))
            exported = json.loads((output_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(exported[0]["storage_path"], str(stable_doc.resolve()))


class PathAnchoringTests(unittest.TestCase):
    def test_default_paths_are_anchored(self) -> None:
        import app.library as library

        self.assertTrue(RUNS_DIR.is_absolute())
        self.assertTrue(DATA_DIR.is_absolute())
        self.assertTrue(Path(DATA_DIR / "processed" / "chunks_clean.jsonl").is_absolute())
        self.assertTrue(Path(CONFIGS_DIR / "default.yaml").is_absolute())
        self.assertTrue(library.DEFAULT_PROCESSED_DIR.is_absolute())


class ImportProgressTests(unittest.TestCase):
    def test_run_import_workflow_emits_progress_updates(self) -> None:
        from app.library import run_import_workflow

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            pdf = base / "demo.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%fake\n")
            progress_calls: list[dict[str, object]] = []

            with (
                patch("app.library.run_ingest", return_value=0),
                patch("app.library.run_build_indexes", return_value=0),
                patch("app.library.load_papers", return_value=[]),
                patch("app.library.load_topics", return_value={}),
            ):
                result = run_import_workflow(
                    uploaded_files=[pdf],
                    topic="",
                    config_path=str(CONFIGS_DIR / "default.yaml"),
                    progress_callback=lambda event: progress_calls.append(event),
                )

            self.assertTrue(result["ok"])
            self.assertTrue(progress_calls)
            self.assertEqual(int(progress_calls[-1].get("processed", -1)), 1)
            self.assertEqual(int(progress_calls[-1].get("total", -1)), 1)

    def test_run_import_workflow_returns_conflict_message_when_ingest_locked(self) -> None:
        from app.library import run_import_workflow

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            pdf = base / "demo.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%fake\n")

            with patch("app.library.run_ingest", return_value=3):
                result = run_import_workflow(
                    uploaded_files=[pdf],
                    topic="",
                    config_path=str(CONFIGS_DIR / "default.yaml"),
                )

            self.assertFalse(result["ok"])
            self.assertEqual(result["message"], "导入冲突，请稍后重试。")
            rendered_reasons = "\n".join(result.get("failure_reasons", []))
            self.assertIn("导入冲突", rendered_reasons)


if __name__ == "__main__":
    unittest.main()
