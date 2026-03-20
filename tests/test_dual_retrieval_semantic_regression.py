from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.qa import run_qa


class DualRetrievalSemanticRegressionTests(unittest.TestCase):
    def _write_chunks(self, path: Path) -> None:
        rows = [
            {
                "chunk_id": "c:1",
                "paper_id": "p1",
                "page_start": 1,
                "text": "Transformer architecture uses self-attention mechanism and encoder decoder pipeline.",
                "clean_text": "transformer architecture self attention mechanism encoder decoder pipeline",
                "content_type": "body",
                "quality_flags": [],
                "section": "Method",
            },
            {
                "chunk_id": "c:2",
                "paper_id": "p1",
                "page_start": 2,
                "text": "The method reports 91.2 accuracy on benchmark evaluation.",
                "clean_text": "method reports 91.2 accuracy benchmark evaluation",
                "content_type": "body",
                "quality_flags": [],
                "section": "Result",
            },
            {
                "chunk_id": "c:3",
                "paper_id": "p2",
                "page_start": 1,
                "text": "Diffusion model focuses on image generation.",
                "clean_text": "diffusion model image generation",
                "content_type": "body",
                "quality_flags": [],
                "section": "Intro",
            },
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_papers(self, path: Path) -> None:
        payload = [
            {"paper_id": "p1", "title": "Transformer Paper", "path": "data/papers/p1.pdf"},
            {"paper_id": "p2", "title": "Diffusion Paper", "path": "data/papers/p2.pdf"},
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _write_config(self, path: Path) -> None:
        path.write_text(
            "dense_backend: tfidf\n"
            "assistant_mode_enabled: false\n"
            "session_store_backend: file\n"
            "embedding:\n"
            "  enabled: false\n"
            "rerank:\n"
            "  enabled: false\n",
            encoding="utf-8",
        )

    def _run_once(self, *, base: Path, query: str, session_id: str) -> dict:
        chunks = base / "chunks_clean.jsonl"
        bm25 = base / "bm25.json"
        vec = base / "vec.json"
        cfg = base / "cfg.yaml"
        store = base / "session_store.json"
        global_runs = Path("runs")
        before = {p.name for p in global_runs.iterdir() if p.is_dir()} if global_runs.exists() else set()
        args = Namespace(
            q=query,
            mode="hybrid",
            chunks=str(chunks),
            bm25_index=str(bm25),
            vec_index=str(vec),
            embed_index=str(base / "embed.json"),
            config=str(cfg),
            top_k=6,
            top_evidence=5,
            session_id=session_id,
            session_store=str(store),
            clear_session=False,
            topic_paper_ids="",
            topic_name="",
        )
        code = run_qa(args)
        self.assertEqual(code, 0)
        after_dirs = [p for p in global_runs.iterdir() if p.is_dir()] if global_runs.exists() else []
        created = [p for p in after_dirs if p.name not in before]
        self.assertTrue(created)
        latest = max(created, key=lambda p: p.stat().st_mtime)
        return json.loads((latest / "qa_report.json").read_text(encoding="utf-8"))

    def test_summary_recall_enabled_and_fallback_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs = base / "runs"
            runs.mkdir(parents=True, exist_ok=True)
            chunks = base / "chunks_clean.jsonl"
            self._write_chunks(chunks)
            self._write_papers(base / "papers.json")
            self._write_config(base / "cfg.yaml")
            build_bm25_index(chunks, base / "bm25.json")
            build_vec_index(chunks, base / "vec.json")

            (base / "paper_summary.json").write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "p1",
                            "title": "Transformer Paper",
                            "one_paragraph_summary": "Transformer architecture and self-attention mechanism.",
                            "keywords": ["transformer", "attention", "architecture"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with_summary = self._run_once(base=base, query="transformer architecture attention", session_id="s1")
            self.assertTrue(with_summary.get("summary_recall_enabled"))
            self.assertGreater(int(with_summary.get("summary_candidate_count") or 0), 0)
            self.assertFalse(with_summary.get("summary_recall_fallback"))

            (base / "paper_summary.json").unlink()
            without_summary = self._run_once(base=base, query="transformer architecture attention", session_id="s2")
            self.assertTrue(without_summary.get("summary_recall_fallback"))

    def test_semantic_matching_metrics_present_for_mixed_expression_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "runs").mkdir(parents=True, exist_ok=True)
            chunks = base / "chunks_clean.jsonl"
            self._write_chunks(chunks)
            self._write_papers(base / "papers.json")
            self._write_config(base / "cfg.yaml")
            build_bm25_index(chunks, base / "bm25.json")
            build_vec_index(chunks, base / "vec.json")
            (base / "paper_summary.json").write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "p1",
                            "title": "Transformer Paper",
                            "one_paragraph_summary": "Transformer method pipeline and architecture.",
                            "keywords": ["transformer", "method", "pipeline"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = self._run_once(base=base, query="请解释 transformer method pipeline 的机制", session_id="s3")
            self.assertIn(str(report.get("semantic_strategy_tier")), {"strict", "balanced", "explore"})


if __name__ == "__main__":
    unittest.main()
