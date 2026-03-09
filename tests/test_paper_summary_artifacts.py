from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.models import ChunkRecord, PageText
from app.paper_summary import build_paper_summaries
from app.retrieve import recall_papers_by_summary


class PaperSummaryArtifactTests(unittest.TestCase):
    def test_build_summary_contains_required_fields_and_snapshot_hash(self) -> None:
        from app.models import PaperRecord

        papers = [
            PaperRecord(
                paper_id="p1",
                title="Doc One",
                path="data/papers/p1.pdf",
                source_type="pdf",
                source_uri="data/papers/p1.pdf",
            )
        ]
        chunks = [ChunkRecord(chunk_id="p1:1", paper_id="p1", page_start=1, text="retrieval pipeline and ranking")]
        summaries, rebuilt = build_paper_summaries(papers, chunks)

        self.assertEqual(rebuilt, [])
        self.assertEqual(len(summaries), 1)
        row = summaries[0].to_dict()
        self.assertTrue(row["chunk_snapshot_hash"])
        self.assertEqual(row["summary_version"], "v1")
        self.assertTrue(row["keywords"])
        self.assertEqual(row["source_uri"], "data/papers/p1.pdf")

    def test_build_summary_marks_rebuild_when_snapshot_changes(self) -> None:
        from app.models import PaperRecord

        papers = [PaperRecord(paper_id="p1", title="Doc One", path="p1.pdf")]
        chunks_v1 = [ChunkRecord(chunk_id="p1:1", paper_id="p1", page_start=1, text="A")]
        summaries_v1, _ = build_paper_summaries(papers, chunks_v1)
        old_hash = summaries_v1[0].chunk_snapshot_hash
        chunks_v2 = [ChunkRecord(chunk_id="p1:1", paper_id="p1", page_start=1, text="A changed")]
        _, rebuilt = build_paper_summaries(papers, chunks_v2, previous_hashes={"p1": old_hash})
        self.assertEqual(rebuilt, ["p1"])

    def test_ingest_writes_paper_summary_file(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_dir = base / "in"
            output_dir = base / "out"
            run_dir = base / "runs"
            input_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            args = Namespace(
                input=str(input_dir),
                out=str(output_dir),
                config="configs/default.yaml",
                question=None,
                clean=False,
                url=[],
                url_file=None,
            )
            with (
                patch("app.ingest.create_run_dir", return_value=run_dir),
                patch("app.ingest.list_pdf_files", return_value=[input_dir / "a.pdf"]),
                patch("app.ingest.make_paper_id", return_value="paper-a"),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="hello world")], [], None)),
                patch("app.ingest.extract_title", return_value="Demo"),
                patch(
                    "app.ingest.build_chunks",
                    return_value=[ChunkRecord(chunk_id="paper-a:1", paper_id="paper-a", page_start=1, text="hello world")],
                ),
            ):
                code = run_ingest(args)

            self.assertEqual(code, 0)
            summary_file = output_dir / "paper_summary.json"
            self.assertTrue(summary_file.exists())
            payload = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 1)
            self.assertTrue(str(payload[0]["paper_id"]).startswith("pdf_"))

    def test_summary_recall_interface_returns_candidates(self) -> None:
        summaries = [
            {
                "paper_id": "p1",
                "title": "Transformer Overview",
                "one_paragraph_summary": "Encoder decoder attention architecture.",
                "keywords": ["transformer", "attention", "encoder"],
            },
            {
                "paper_id": "p2",
                "title": "Diffusion models",
                "one_paragraph_summary": "Image generation",
                "keywords": ["diffusion"],
            },
        ]
        hits = recall_papers_by_summary("attention architecture", summaries, top_k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].paper_id, "p1")


if __name__ == "__main__":
    unittest.main()
