from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig
from app.context_budget import assemble_prompt_with_budget
from app.qa import run_qa
from app.retrieve import RetrievalCandidate


class M77ContextBudgetUnitTests(unittest.TestCase):
    def test_trim_order_history_then_graph_expand_low_score(self) -> None:
        history = [
            {"user_input": "old turn one " * 20, "answer": "answer one " * 20},
            {"user_input": "old turn two " * 20, "answer": "answer two " * 20},
            {"user_input": "latest turn " * 20, "answer": "latest answer " * 20},
        ]
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "P1",
                "evidence": [
                    {
                        "chunk_id": "ge-low",
                        "quote": "graph low " * 80,
                        "section_page": "p.1",
                        "source": "graph_expand",
                        "score_rerank": 0.1,
                        "score_retrieval": 0.1,
                    },
                    {
                        "chunk_id": "bm25-high",
                        "quote": "bm25 high " * 80,
                        "section_page": "p.2",
                        "source": "bm25",
                        "score_rerank": 0.9,
                        "score_retrieval": 0.9,
                    },
                ],
            }
        ]
        result = assemble_prompt_with_budget(
            system_prompt="system prompt",
            user_prompt="user prompt",
            chat_history=history,
            evidence_grouped=evidence_grouped,
            max_context_tokens=60,
        )
        self.assertGreaterEqual(result.history_trimmed_turns, 2)
        self.assertTrue(result.discarded_evidence)
        self.assertEqual(result.discarded_evidence[0]["chunk_id"], "ge-low")

    def test_fallback_when_evidence_trimmed_to_zero(self) -> None:
        result = assemble_prompt_with_budget(
            system_prompt="system prompt",
            user_prompt="user prompt",
            chat_history=[{"user_input": "q " * 30, "answer": "a " * 30}],
            evidence_grouped=[
                {
                    "paper_id": "p1",
                    "paper_title": "P1",
                    "evidence": [
                        {
                            "chunk_id": "only-1",
                            "quote": "very long evidence " * 200,
                            "section_page": "p.1",
                            "source": "graph_expand",
                            "score_rerank": 0.2,
                        }
                    ],
                }
            ],
            max_context_tokens=20,
        )
        self.assertTrue(result.context_overflow_fallback)
        self.assertEqual(result.remaining_evidence_count, 0)
        self.assertEqual(len(result.discarded_evidence), 1)


class M77ContextBudgetIntegrationTests(unittest.TestCase):
    def _args(self, *, base: Path, chunks: Path, cfg: Path) -> Namespace:
        return Namespace(
            q="请比较这些检索结果并总结。",
            mode="hybrid",
            chunks=str(chunks),
            bm25_index=str(base / "bm25.json"),
            vec_index=str(base / "vec.json"),
            embed_index=str(base / "embed.json"),
            config=str(cfg),
            top_k=30,
            top_evidence=30,
            session_id="m77",
            session_store=str(base / "session_store.json"),
            clear_session=False,
        )

    def _long_candidates(self) -> list[RetrievalCandidate]:
        rows: list[RetrievalCandidate] = []
        for i in range(30):
            rows.append(
                RetrievalCandidate(
                    chunk_id=f"ge:{i:03d}",
                    score=1.0 - i * 0.01,
                    content_type="body",
                    payload={
                        "source": "graph_expand",
                        "dense_backend": "tfidf",
                        "retrieval_mode": "hybrid",
                        "score_retrieval": 1.0 - i * 0.01,
                        "score_rerank": 0.2 - i * 0.001,
                    },
                    paper_id=f"p{i % 10}",
                    page_start=1 + i,
                    section="Body",
                    text=("very long graph expansion evidence " * 200) + str(i),
                    clean_text="long graph evidence",
                )
            )
        return rows

    def test_extreme_context_overflow_short_circuits_without_llm_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            chunks.write_text("", encoding="utf-8")
            (base / "papers.json").write_text(
                json.dumps([{"paper_id": f"p{i}", "title": f"Paper-{i}"} for i in range(10)], ensure_ascii=False),
                encoding="utf-8",
            )
            cfg = base / "cfg.yaml"
            cfg.write_text("dense_backend: tfidf\nembedding:\n  enabled: false\n", encoding="utf-8")
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)

            config = PipelineConfig()
            config.embedding.enabled = False
            config.answer_use_llm = True
            config.llm_fallback_enabled = True
            config.max_context_tokens = 40

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._long_candidates(),
                    "score_distribution": {"count": 30, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()

            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._long_candidates()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (
                        cands,
                        {"enabled": True, "graph_loaded": True, "seed_count": len(cands), "added": 0, "added_chunk_ids": []},
                    ),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa.call_chat_completion") as mock_call_chat,
                patch("app.qa.call_chat_completion_stream") as mock_call_stream,
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "test-key"}, clear=False),
            ):
                code = run_qa(self._args(base=base, chunks=chunks, cfg=cfg))

            self.assertEqual(code, 0)
            self.assertFalse(mock_call_chat.called)
            self.assertFalse(mock_call_stream.called)

            report = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("answer"), "检索内容过长，无法生成答案")
            self.assertIn("context_overflow_fallback", report.get("output_warnings", []))
            self.assertTrue(report.get("discarded_evidence"))
            self.assertGreater(report.get("discarded_evidence_count", 0), 0)
            self.assertTrue(trace.get("context_overflow_fallback"))
            self.assertGreaterEqual(trace.get("history_trimmed_turns", 0), 0)


if __name__ == "__main__":
    unittest.main()
