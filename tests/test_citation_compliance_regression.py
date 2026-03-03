from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.qa import run_qa


class CitationComplianceRegressionTests(unittest.TestCase):
    def _prepare_base(self, base: Path) -> None:
        chunks = [
            {
                "chunk_id": "c:1",
                "paper_id": "p1",
                "page_start": 1,
                "text": "Transformer uses self-attention layers.",
                "clean_text": "transformer self attention layers",
                "content_type": "body",
                "quality_flags": [],
                "section": "Method",
            }
        ]
        with (base / "chunks_clean.jsonl").open("w", encoding="utf-8") as f:
            for row in chunks:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        (base / "papers.json").write_text(
            json.dumps([{"paper_id": "p1", "title": "P1", "path": "p1.pdf"}], ensure_ascii=False),
            encoding="utf-8",
        )
        (base / "cfg.yaml").write_text(
            "dense_backend: tfidf\n"
            "assistant_mode_enabled: false\n"
            "session_store_backend: file\n"
            "evidence_policy_enforced: false\n"
            "embedding:\n"
              "  enabled: false\n"
            "rerank:\n"
              "  enabled: false\n",
            encoding="utf-8",
        )
        build_bm25_index(base / "chunks_clean.jsonl", base / "bm25.json")
        build_vec_index(base / "chunks_clean.jsonl", base / "vec.json")
        (base / "runs").mkdir(parents=True, exist_ok=True)

    def test_invalid_citation_is_filtered_to_chunk_traceable_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._prepare_base(base)

            args = Namespace(
                q="self attention method",
                mode="hybrid",
                chunks=str(base / "chunks_clean.jsonl"),
                bm25_index=str(base / "bm25.json"),
                vec_index=str(base / "vec.json"),
                embed_index=str(base / "embed.json"),
                config=str(base / "cfg.yaml"),
                top_k=5,
                top_evidence=5,
                session_id="cite-check",
                session_store=str(base / "session_store.json"),
                clear_session=False,
                topic_paper_ids="",
                topic_name="",
            )
            global_runs = Path("runs")
            before = {p.name for p in global_runs.iterdir() if p.is_dir()} if global_runs.exists() else set()

            with patch(
                "app.qa.run_sufficiency_gate",
                return_value={
                    "enabled": True,
                    "decision": "answer",
                    "reason": "ok",
                    "clarify_questions": [],
                    "semantic_similarity_score": 0.9,
                    "semantic_policy": "balanced",
                    "triggered_rules": [],
                    "clarify_limit_hit": False,
                    "forced_partial_answer": False,
                    "missing_key_elements": [],
                },
            ), patch(
                "app.qa._build_answer",
                return_value=(
                    "The method uses self-attention [1].",
                    [{"chunk_id": "c:404", "paper_id": "p9", "section_page": "p.9"}],
                    False,
                    False,
                    None,
                    {
                        "answer_stream_enabled": False,
                        "answer_stream_used": False,
                        "answer_stream_first_token_ms": None,
                        "answer_stream_fallback_reason": None,
                        "answer_stream_events": [],
                    },
                    {
                        "prompt_tokens_est": 0,
                        "discarded_evidence": [],
                        "discarded_evidence_count": 0,
                        "history_trimmed_turns": 0,
                        "context_overflow_fallback": False,
                    },
                ),
            ):
                code = run_qa(args)

            self.assertEqual(code, 0)
            after_dirs = [p for p in global_runs.iterdir() if p.is_dir()] if global_runs.exists() else []
            created = [p for p in after_dirs if p.name not in before]
            self.assertTrue(created)
            latest = max(created, key=lambda p: p.stat().st_mtime)
            report = json.loads((latest / "qa_report.json").read_text(encoding="utf-8"))
            evidence_ids = {
                str(item.get("chunk_id"))
                for group in report.get("evidence_grouped", [])
                for item in (group.get("evidence", []) or [])
            }
            citation_ids = {str(c.get("chunk_id")) for c in (report.get("answer_citations", []) or [])}
            self.assertTrue(citation_ids.issubset(evidence_ids))
            self.assertIn("citation_mapping_incomplete_low_confidence", report.get("output_warnings", []))


if __name__ == "__main__":
    unittest.main()
