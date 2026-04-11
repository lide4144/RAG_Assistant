from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.marker_parser import MarkerParseError, MarkerParseResult, StructuredBlock
from app.models import PageText
from app.parser import choose_best_title


class MarkerIngestionTests(unittest.TestCase):
    def _marker_enabled_state(self):
        return type("MarkerEnabled", (), {"value": True, "source": "runtime", "warnings": []})()

    def _args(self, input_dir: Path, out_dir: Path, run_dir: Path) -> Namespace:
        return Namespace(
            input=str(input_dir),
            out=str(out_dir),
            config="configs/default.yaml",
            question=None,
            clean=False,
            run_id="",
            run_dir=str(run_dir),
            lock_timeout_sec=10.0,
            url=[],
            url_file=None,
        )

    def test_blacklist_title_is_rejected(self) -> None:
        decision = choose_best_title(
            metadata_title="",
            pages=[PageText(page_num=1, text="Real Paper Title\nBody")],
            title_candidates=["Preprint. Under review."],
            confidence_threshold=0.6,
        )
        self.assertEqual(decision.title, "Real Paper Title")
        self.assertEqual(decision.source, "fallback_first_line")

    def test_attribution_line_is_rejected_as_title(self) -> None:
        decision = choose_best_title(
            metadata_title="",
            pages=[PageText(page_num=1, text="Attention Is All You Need\nBody")],
            title_candidates=["Provided proper attribution is provided, Google hereby grants permission to"],
            confidence_threshold=0.6,
        )
        self.assertEqual(decision.title, "Attention Is All You Need")
        self.assertEqual(decision.source, "fallback_first_line")

    def test_structured_title_prefers_h1_over_h2(self) -> None:
        decision = choose_best_title(
            metadata_title="",
            pages=[PageText(page_num=1, text="Paper Title\nAbstract\n1 Introduction")],
            title_candidates=[
                {"text": "1 Introduction", "source": "marker_h2", "priority": 2, "page": 1, "heading_level": 2},
                {"text": "Paper Title", "source": "marker_h1", "priority": 1, "page": 1, "heading_level": 1},
            ],
            confidence_threshold=0.6,
        )
        self.assertEqual(decision.title, "Paper Title")
        self.assertEqual(decision.source, "marker_h1")

    def test_structured_title_falls_back_to_h2_when_h1_rejected(self) -> None:
        decision = choose_best_title(
            metadata_title="Metadata Title",
            pages=[PageText(page_num=1, text="Metadata Title\nBody")],
            title_candidates=[
                {"text": "Abstract", "source": "marker_h1", "priority": 1, "page": 1, "heading_level": 1},
                {"text": "Useful Paper Title", "source": "marker_h2", "priority": 2, "page": 1, "heading_level": 2},
            ],
            confidence_threshold=0.6,
        )
        self.assertEqual(decision.title, "Useful Paper Title")
        self.assertEqual(decision.source, "marker_h2")

    def test_marker_failure_fallback_keeps_ingest_running(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = in_dir / "a.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            with (
                patch("app.ingest.resolve_effective_marker_enabled", return_value=self._marker_enabled_state()),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest._marker_preflight_check", return_value=(True, "", "")),
                patch("app.ingest.parse_pdf_with_marker", side_effect=MarkerParseError("marker unavailable")),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="Good Title\ncontent")], [], None)),
            ):
                code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            rows = report.get("parser_observability", [])
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].get("parser_fallback"))
            self.assertEqual(rows[0].get("parser_fallback_stage"), "unknown")
            self.assertIn("marker unavailable", str(rows[0].get("parser_fallback_reason", "")))

    def test_marker_preflight_failure_is_reported_with_stage(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = in_dir / "a.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            with (
                patch("app.ingest.resolve_effective_marker_enabled", return_value=self._marker_enabled_state()),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest._marker_preflight_check", return_value=(False, "model_cache_access", "marker preflight failed: cache dir not writable")),
                patch("app.ingest.parse_pdf_pages", return_value=([PageText(page_num=1, text="Good Title\ncontent")], [], None)),
            ):
                code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            rows = report.get("parser_observability", [])
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].get("parser_fallback"))
            self.assertEqual(rows[0].get("parser_fallback_stage"), "model_cache_access")
            self.assertIn("marker preflight failed", str(rows[0].get("parser_fallback_reason", "")))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertIn("parser_fallback_stages", trace)
            self.assertIn("model_cache_access", trace.get("parser_fallback_stages", []))
            counts = trace.get("parser_fallback_stage_counts", {})
            self.assertEqual(counts.get("model_cache_access"), 1)

    def test_controlled_skip_is_reported_as_skipped_not_failed(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            doc = in_dir / "empty.rtf"
            doc.write_text("", encoding="utf-8")

            code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            summary = report.get("import_summary", {})
            self.assertEqual(summary.get("added"), 0)
            self.assertEqual(summary.get("skipped"), 1)
            self.assertEqual(summary.get("failed"), 0)
            self.assertTrue(summary.get("controlled_skip"))
            outcomes = report.get("import_outcomes", [])
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(outcomes[0].get("status"), "skipped")
            self.assertIn("no readable rtf text", str(outcomes[0].get("reason", "")))
            rows = report.get("parser_observability", [])
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].get("controlled_skip"))
            self.assertEqual(rows[0].get("parser_mode"), "controlled_skip")
            self.assertIn("受控跳过", str(report.get("confidence_note", "")))

    def test_papers_and_report_include_parser_observability_fields(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = in_dir / "b.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            marker_result = MarkerParseResult(
                pages=[PageText(page_num=1, text="Marker Title\nBody")],
                blocks=[StructuredBlock(page_num=1, text="Marker Title", heading_level=1)],
                title_candidates=["Marker Title"],
                structured_title_candidates=[{"text": "Marker Title", "source": "marker_h1", "priority": 1, "page": 1, "heading_level": 1}],
                diagnostics={"markdown": {"available": True, "consumption_status": "partial"}},
            )

            with (
                patch("app.ingest.resolve_effective_marker_enabled", return_value=self._marker_enabled_state()),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest._marker_preflight_check", return_value=(True, "", "")),
                patch("app.ingest.parse_pdf_with_marker", return_value=marker_result),
            ):
                code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            papers = json.loads((out_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 1)
            self.assertEqual(papers[0].get("parser_engine"), "marker")
            self.assertEqual(papers[0].get("title_source"), "marker_h1")
            self.assertIsInstance(papers[0].get("title_confidence"), float)
            self.assertEqual(papers[0].get("ingest_metadata", {}).get("title_layer"), "marker_h1")

            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            rows = report.get("parser_observability", [])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("parser_engine"), "marker")
            self.assertFalse(rows[0].get("parser_fallback"))
            self.assertEqual(rows[0].get("title_layer"), "marker_h1")
            self.assertTrue(rows[0].get("markdown_available"))
            self.assertIn("marker_tuning", report)
            self.assertIn("effective_source", report.get("marker_tuning", {}))
            self.assertIn("marker_tuning", rows[0])
            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertIn("parser_engine_counts", trace)
            self.assertIn("title_source_counts", trace)
            self.assertIn("title_confidence_stats", trace)

    def test_formula_and_table_blocks_are_traceable_in_chunks(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = in_dir / "c.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            marker_result = MarkerParseResult(
                pages=[PageText(page_num=1, text="Equation and Table")],
                blocks=[
                    StructuredBlock(page_num=1, text="E = mc^2", heading_level=None, block_type="Formula"),
                    StructuredBlock(page_num=1, text="Table 1 Accuracy 0.95", heading_level=None, block_type="Table"),
                ],
                title_candidates=["Equation and Table"],
            )

            with (
                patch("app.ingest.resolve_effective_marker_enabled", return_value=self._marker_enabled_state()),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest._marker_preflight_check", return_value=(True, "", "")),
                patch("app.ingest.parse_pdf_with_marker", return_value=marker_result),
            ):
                code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            chunk_lines = (out_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            chunk_rows = [json.loads(line) for line in chunk_lines if line.strip()]
            chunk_texts = [row.get("text", "") for row in chunk_rows]
            self.assertTrue(any("E = mc^2" in text for text in chunk_texts))
            self.assertTrue(any("Table 1 Accuracy 0.95" in text for text in chunk_texts))
            self.assertIn("formula_block", {row.get("content_type") for row in chunk_rows})
            self.assertIn("structure_provenance", chunk_rows[0])

            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            rows = report.get("parser_observability", [])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("parser_engine"), "marker")
            self.assertTrue(rows[0].get("block_semantics_preserved"))

    def test_marker_without_blocks_reports_structured_segments_missing(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = in_dir / "d.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            marker_result = MarkerParseResult(
                pages=[PageText(page_num=1, text="Title\nBody")],
                blocks=[],
                title_candidates=["Title"],
            )

            with (
                patch("app.ingest.resolve_effective_marker_enabled", return_value=self._marker_enabled_state()),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest._marker_preflight_check", return_value=(True, "", "")),
                patch("app.ingest.parse_pdf_with_marker", return_value=marker_result),
            ):
                code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
            rows = report.get("parser_observability", [])
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].get("structured_segments_missing"))
            self.assertEqual(rows[0].get("structured_segments_missing_reason"), "marker_blocks_empty")
            self.assertEqual(len(report.get("structured_segments_missing", [])), 1)
            self.assertEqual(rows[0].get("markdown_consumption_status"), "missing")

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("structured_segments_missing_count"), 1)
            reasons = trace.get("structured_segments_missing_reasons", {})
            self.assertEqual(reasons.get("marker_blocks_empty"), 1)

    def test_structure_index_is_written_with_section_mappings(self) -> None:
        from app.ingest import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_dir = base / "in"
            out_dir = base / "out"
            run_dir = base / "run"
            in_dir.mkdir(parents=True, exist_ok=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            pdf = in_dir / "e.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")

            marker_result = MarkerParseResult(
                pages=[PageText(page_num=1, text="Intro\nBody"), PageText(page_num=2, text="Method\nDetails")],
                blocks=[
                    StructuredBlock(page_num=1, text="Introduction", heading_level=1),
                    StructuredBlock(page_num=1, text="Intro body text", heading_level=None),
                    StructuredBlock(page_num=2, text="Method", heading_level=1),
                    StructuredBlock(page_num=2, text="Method body text", heading_level=None),
                ],
                title_candidates=["Structured Paper"],
            )

            with (
                patch("app.ingest.resolve_effective_marker_enabled", return_value=self._marker_enabled_state()),
                patch("app.ingest.list_pdf_files", return_value=[pdf]),
                patch("app.ingest._marker_preflight_check", return_value=(True, "", "")),
                patch("app.ingest.parse_pdf_with_marker", return_value=marker_result),
            ):
                code = run_ingest(self._args(in_dir, out_dir, run_dir))

            self.assertEqual(code, 0)
            structure_index = json.loads((out_dir / "structure_index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(structure_index.get("papers", [])), 1)
            paper = structure_index["papers"][0]
            self.assertEqual(paper.get("structure_parse_status"), "ready")
            self.assertGreaterEqual(len(paper.get("sections", [])), 2)
            self.assertTrue(all(section.get("child_chunk_ids") for section in paper.get("sections", [])))

            papers = json.loads((out_dir / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(papers[0].get("ingest_metadata", {}).get("structure_parse_status"), "ready")


if __name__ == "__main__":
    unittest.main()
