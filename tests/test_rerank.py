from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig
from app.graph_build import ChunkGraph, GraphBuildStats, GraphNode, save_graph
from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.rerank import rerank_candidates
from app.retrieve import RetrievalCandidate, expand_candidates_with_graph, load_indexes_and_config, retrieve_candidates


class RerankTests(unittest.TestCase):
    def _write_chunks(self, path: Path) -> None:
        rows = [
            {
                "chunk_id": "seed:1",
                "paper_id": "p1",
                "page_start": 1,
                "text": "retrieval baseline with graph expansion and rerank integration details",
                "clean_text": "retrieval baseline graph expansion rerank integration",
                "content_type": "body",
                "quality_flags": [],
                "section": "Intro",
            },
            {
                "chunk_id": "adj:1",
                "paper_id": "p1",
                "page_start": 2,
                "text": "adjacent evidence about rerank score and evidence selection quality",
                "clean_text": "adjacent evidence rerank score evidence selection quality",
                "content_type": "body",
                "quality_flags": [],
                "section": "Method",
            },
            {
                "chunk_id": "ent:1",
                "paper_id": "p2",
                "page_start": 4,
                "text": "entity linked paragraph about retrieval candidates and ranking robustness",
                "clean_text": "entity linked paragraph retrieval candidates ranking robustness",
                "content_type": "body",
                "quality_flags": [],
                "section": "Results",
            },
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_graph(self, path: Path) -> None:
        nodes = {
            "seed:1": GraphNode("seed:1", "p1", 1, "Intro", "body", []),
            "adj:1": GraphNode("adj:1", "p1", 2, "Method", "body", []),
            "ent:1": GraphNode("ent:1", "p2", 4, "Results", "body", []),
        }
        graph = ChunkGraph(
            nodes=nodes,
            adjacent={
                "seed:1": ["adj:1"],
                "adj:1": ["seed:1"],
                "ent:1": [],
            },
            entity={
                "seed:1": [("ent:1", 1)],
                "adj:1": [],
                "ent:1": [],
            },
            stats=GraphBuildStats(),
            config={},
        )
        save_graph(graph, path)

    def _write_cfg(self, path: Path, graph_path: Path) -> None:
        path.write_text(
            "dense_backend: tfidf\n"
            "graph_path: " + str(graph_path) + "\n"
            "graph_expand_alpha: 2.0\n"
            "graph_expand_max_candidates: 200\n"
            "rerank:\n"
            "  enabled: true\n"
            "  provider: mock\n"
            "  top_n: 2\n"
            "embedding:\n"
            "  enabled: false\n",
            encoding="utf-8",
        )

    def test_rerank_contract_warns_on_missing_embedding_meta(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "mock"
        cfg.rerank.top_n = 3
        candidates = [
            RetrievalCandidate(
                chunk_id="c:1",
                score=0.9,
                payload={
                    "source": "dense",
                    "dense_backend": "embedding",
                },
                text="one",
                clean_text="one",
            ),
            RetrievalCandidate(
                chunk_id="c:2",
                score=0.8,
                payload={
                    "source": "dense",
                    "dense_backend": "tfidf",
                    "score_retrieval": 0.8,
                },
                text="two",
                clean_text="two",
            ),
        ]
        outcome = rerank_candidates(query="two", candidates=candidates, config=cfg)
        self.assertIn("rerank_input_contract_violation", outcome.warnings)
        self.assertIn("rerank_input_missing_embedding_metadata", outcome.warnings)
        self.assertTrue(outcome.candidates)

    def test_rerank_all_invalid_candidates_returns_empty(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "mock"
        cfg.rerank.top_n = 3
        candidates = [
            RetrievalCandidate(
                chunk_id="c:1",
                score=0.9,
                payload={"source": "dense", "dense_backend": "embedding"},
                text="one",
                clean_text="one",
            ),
            RetrievalCandidate(
                chunk_id="c:2",
                score=0.7,
                payload={"dense_backend": "tfidf"},
                text="two",
                clean_text="two",
            ),
        ]
        outcome = rerank_candidates(query="two", candidates=candidates, config=cfg)
        self.assertEqual(outcome.candidates, [])
        self.assertIn("rerank_no_valid_candidates", outcome.warnings)

    def test_rerank_preserves_dense_backend_and_scores(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "mock"
        cfg.rerank.top_n = 2
        candidates = [
            RetrievalCandidate(
                chunk_id="a",
                score=0.7,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.7},
                text="alpha beta",
                clean_text="alpha beta",
            ),
            RetrievalCandidate(
                chunk_id="b",
                score=0.6,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.6},
                text="alpha",
                clean_text="alpha",
            ),
        ]
        outcome = rerank_candidates(query="alpha beta", candidates=candidates, config=cfg)
        self.assertLessEqual(len(outcome.candidates), 2)
        for row in outcome.candidates:
            self.assertEqual((row.payload or {}).get("dense_backend"), "tfidf")
            self.assertIn("score_retrieval", row.payload or {})
            self.assertIn("score_rerank", row.payload or {})

    def test_rerank_disabled_falls_back_to_retrieval_sort_without_backend_rewrite(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = False
        cfg.rerank.provider = "mock"
        cfg.rerank.top_n = 2
        candidates = [
            RetrievalCandidate(
                chunk_id="a",
                score=0.99,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.2},
                text="alpha",
                clean_text="alpha",
            ),
            RetrievalCandidate(
                chunk_id="b",
                score=0.01,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.9},
                text="beta",
                clean_text="beta",
            ),
            RetrievalCandidate(
                chunk_id="c",
                score=0.5,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.6},
                text="gamma",
                clean_text="gamma",
            ),
        ]

        outcome = rerank_candidates(query="beta gamma", candidates=candidates, config=cfg)

        self.assertEqual([row.chunk_id for row in outcome.candidates], ["b", "c"])
        self.assertFalse(outcome.used_fallback)
        self.assertEqual(outcome.provider, "disabled")
        for row in outcome.candidates:
            self.assertEqual((row.payload or {}).get("dense_backend"), "tfidf")
            self.assertEqual(
                (row.payload or {}).get("score_rerank"),
                (row.payload or {}).get("score_retrieval"),
            )

    def test_siliconflow_provider_success_results_shape(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "siliconflow"
        cfg.rerank.top_n = 2
        cfg.rerank.max_retries = 0
        cfg.rerank.api_key_env = "TEST_SF_KEY"

        candidates = [
            RetrievalCandidate(
                chunk_id="a",
                score=0.3,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.3},
                text="doc a",
                clean_text="doc a",
            ),
            RetrievalCandidate(
                chunk_id="b",
                score=0.2,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.2},
                text="doc b",
                clean_text="doc b",
            ),
        ]

        class _Resp:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

        with patch.dict(os.environ, {"TEST_SF_KEY": "x"}):
            with patch("urllib.request.urlopen", return_value=_Resp({
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ]
            })):
                outcome = rerank_candidates(query="doc b", candidates=candidates, config=cfg)
        self.assertEqual(outcome.candidates[0].chunk_id, "b")
        self.assertFalse(outcome.used_fallback)
        self.assertNotIn("rerank_fallback_to_retrieval", outcome.warnings)

    def test_siliconflow_provider_success_data_shape_with_retry(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "siliconflow"
        cfg.rerank.top_n = 2
        cfg.rerank.max_retries = 1
        cfg.rerank.api_key_env = "TEST_SF_KEY"

        candidates = [
            RetrievalCandidate(
                chunk_id="a",
                score=0.3,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.3},
                text="doc a",
                clean_text="doc a",
            ),
            RetrievalCandidate(
                chunk_id="b",
                score=0.2,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.2},
                text="doc b",
                clean_text="doc b",
            ),
        ]

        class _Resp:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

        with patch.dict(os.environ, {"TEST_SF_KEY": "x"}):
            with patch(
                "urllib.request.urlopen",
                side_effect=[
                    urllib.error.URLError("temporary"),
                    _Resp({
                        "data": [
                            {"index": 0, "score": 0.7},
                            {"index": 1, "score": 0.2},
                        ]
                    }),
                ],
            ):
                outcome = rerank_candidates(query="doc a", candidates=candidates, config=cfg)
        self.assertEqual(outcome.candidates[0].chunk_id, "a")
        self.assertFalse(outcome.used_fallback)
        self.assertNotIn("rerank_fallback_to_retrieval", outcome.warnings)

    def test_siliconflow_provider_failure_fallbacks_to_retrieval_sort(self) -> None:
        cfg = PipelineConfig()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "siliconflow"
        cfg.rerank.top_n = 2
        cfg.rerank.max_retries = 1
        cfg.rerank.fallback_to_retrieval = True
        cfg.rerank.api_key_env = "TEST_SF_KEY"

        candidates = [
            RetrievalCandidate(
                chunk_id="a",
                score=0.2,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.2},
                text="doc a",
                clean_text="doc a",
            ),
            RetrievalCandidate(
                chunk_id="b",
                score=0.9,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.9},
                text="doc b",
                clean_text="doc b",
            ),
            RetrievalCandidate(
                chunk_id="c",
                score=0.6,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.6},
                text="doc c",
                clean_text="doc c",
            ),
        ]

        with patch.dict(os.environ, {"TEST_SF_KEY": "x"}):
            with patch(
                "urllib.request.urlopen",
                side_effect=[urllib.error.URLError("temporary"), urllib.error.URLError("still down")],
            ):
                outcome = rerank_candidates(query="doc b", candidates=candidates, config=cfg)

        self.assertTrue(outcome.used_fallback)
        self.assertIn("rerank_fallback_to_retrieval", outcome.warnings)
        self.assertEqual([row.chunk_id for row in outcome.candidates], ["b", "c"])
        for row in outcome.candidates:
            self.assertEqual((row.payload or {}).get("dense_backend"), "tfidf")
            self.assertEqual(
                (row.payload or {}).get("score_rerank"),
                (row.payload or {}).get("score_retrieval"),
            )

    def test_retrieval_expand_rerank_integration_for_all_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            graph = base / "graph.json"
            cfg_path = base / "cfg.yaml"
            self._write_chunks(chunks)
            self._write_graph(graph)
            self._write_cfg(cfg_path, graph)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            bm25, vec, config, _ = load_indexes_and_config(
                bm25_index_path=str(bm25_idx),
                vec_index_path=str(vec_idx),
                config_path=str(cfg_path),
            )
            self.assertEqual(config.rerank.top_n, 2)

            for mode in ("dense", "bm25", "hybrid"):
                retrieved = retrieve_candidates(
                    "rerank retrieval evidence",
                    mode=mode,
                    top_k=3,
                    bm25_index=bm25,
                    vec_index=vec,
                    config=config,
                )
                expanded, _stats = expand_candidates_with_graph(
                    retrieved,
                    query="rerank retrieval evidence",
                    top_k=3,
                    bm25_index=bm25,
                    vec_index=vec,
                    config=config,
                )
                outcome = rerank_candidates(
                    query="rerank retrieval evidence",
                    candidates=expanded,
                    config=config,
                )
                self.assertLessEqual(len(outcome.candidates), 2)
                self.assertGreaterEqual(outcome.score_distribution.get("count", 0), 1)
                for row in outcome.candidates:
                    self.assertIn("score_retrieval", row.payload or {})
                    self.assertIn("score_rerank", row.payload or {})
                    self.assertEqual((row.payload or {}).get("dense_backend"), "tfidf")


if __name__ == "__main__":
    unittest.main()
