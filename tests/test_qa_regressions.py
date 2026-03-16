from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig
from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.intent_calibration import CalibrationResult
from app.qa import _build_answer, _build_evidence_lookup, _parse_answer_payload, run_qa
from app.rewrite import RewriteResult


class QARegressionTests(unittest.TestCase):
    def test_build_evidence_lookup_preserves_structure_fields(self) -> None:
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "p1:1",
                        "paper_id": "p1",
                        "section_page": "p.3",
                        "section_id": "2.1",
                        "quote": "Table 1 reports the main result.",
                        "block_type": "table_block",
                        "structure_provenance": {"source": "marker", "block_type": "Table"},
                    }
                ],
            }
        ]

        lookup = _build_evidence_lookup(evidence_grouped)

        self.assertEqual(lookup["p1:1"]["block_type"], "table_block")
        self.assertEqual(lookup["p1:1"]["structure_provenance"]["block_type"], "Table")

    def test_build_answer_does_not_reject_single_paper_match_with_paper_clue(self) -> None:
        config = PipelineConfig(answer_use_llm=False)
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "p1:1",
                        "section_page": "p.1",
                        "quote": "The paper introduces a retrieval-augmented generation pipeline.",
                        "content_type": "body",
                    }
                ],
            }
        ]

        answer, citations, _, _, _, _, _ = _build_answer(
            "这篇论文讲了什么？",
            "open",
            {"has_paper_clue": True},
            evidence_grouped,
            [],
            config,
            history_turns=[],
        )

        self.assertIn("Paper One", answer)
        self.assertNotIn("当前问题未指定具体论文", answer)
        self.assertEqual(citations[0]["chunk_id"], "p1:1")

    def test_parse_answer_payload_preserves_structured_citation_metadata(self) -> None:
        content = """```json
{
  "answer": "hello",
  "answer_citations": [
    {
      "chunk_id": "c1",
      "paper_id": "p1",
      "section_page": "p.1",
      "block_type": "table_block",
      "structure_provenance": {"source": "marker", "block_type": "Table"}
    }
  ]
}
```"""

        answer, citations, warning = _parse_answer_payload(content=content)

        self.assertEqual(warning, None)
        self.assertEqual(answer, "hello")
        self.assertEqual(citations[0]["block_type"], "table_block")
        self.assertEqual(citations[0]["structure_provenance"]["block_type"], "Table")

    def test_run_qa_trace_records_legacy_selected_rewritten_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_index = base / "bm25.json"
            vec_index = base / "vec.json"
            embed_index = base / "embed.json"
            config_path = base / "cfg.yaml"
            session_store = base / "session_store.json"
            run_dir = base / "run"

            chunks.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "chunk_id": "p1:1",
                                "paper_id": "p1",
                                "page_start": 1,
                                "text": "Transformer architecture uses attention blocks.",
                                "clean_text": "Transformer architecture attention blocks",
                                "content_type": "body",
                                "quality_flags": [],
                                "section": "Intro",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "chunk_id": "p1:2",
                                "paper_id": "p1",
                                "page_start": 2,
                                "text": "The method includes encoder and decoder stacks.",
                                "clean_text": "method encoder decoder stacks",
                                "content_type": "body",
                                "quality_flags": [],
                                "section": "Method",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (base / "papers.json").write_text(
                json.dumps([{"paper_id": "p1", "title": "Paper One", "path": "data/papers/p1.pdf"}], ensure_ascii=False),
                encoding="utf-8",
            )
            config_path.write_text(
                "\n".join(
                    [
                        "dense_backend: tfidf",
                        "planner_enabled: false",
                        "answer_use_llm: false",
                        "rewrite_parallel_candidates_enabled: true",
                        "rewrite_legacy_strategy_enabled: true",
                        "session_store_backend: file",
                        "embedding:",
                        "  enabled: false",
                        "rerank:",
                        "  enabled: false",
                    ]
                ),
                encoding="utf-8",
            )

            build_bm25_index(chunks, bm25_index)
            build_vec_index(chunks, vec_index)

            args = Namespace(
                q="Transformer 有什么用处？",
                chunks=str(chunks),
                bm25_index=str(bm25_index),
                vec_index=str(vec_index),
                embed_index=str(embed_index),
                config=str(config_path),
                mode="hybrid",
                top_k=4,
                session_id="qa-regression",
                session_store=str(session_store),
                clear_session=False,
                run_dir=str(run_dir),
                run_id="",
                topic_name="",
                topic_paper_ids="",
            )

            rewrite_result = RewriteResult(
                question="Transformer 有什么用处？",
                rewritten_query="rule query",
                rewrite_rule_query="rule query",
                rewrite_llm_query="llm query",
                keywords_entities={"keywords": [], "entities": ["Transformer"]},
                strategy_hits=["llm_rewrite_applied"],
                llm_used=True,
            )

            with (
                patch("app.qa.rewrite_query", return_value=rewrite_result),
                patch(
                    "app.qa.calibrate_query_intent",
                    return_value=CalibrationResult(
                        calibrated_query="llm query",
                        calibration_reason={"rule": "identity"},
                    ),
                ),
                redirect_stdout(io.StringIO()),
            ):
                code = run_qa(args)

            self.assertEqual(code, 0)
            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            report = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))

            self.assertEqual(trace["rewrite_selected_by"], "legacy_strategy")
            self.assertEqual(trace["rewritten_query"], "llm query")
            self.assertEqual(trace["query_used"], "llm query")
            self.assertEqual(report["rewritten_query"], "llm query")


if __name__ == "__main__":
    unittest.main()
