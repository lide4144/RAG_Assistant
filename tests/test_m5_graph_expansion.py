from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig
from app.graph_build import ChunkGraph, GraphBuildStats, GraphNode, save_graph
from app.index_bm25 import BM25Doc, BM25Index
from app.index_vec import VecDoc, VecIndex
from app.retrieve import RetrievalCandidate, expand_candidates_with_graph


class GraphExpansionTests(unittest.TestCase):
    def _build_indexes(self) -> tuple[BM25Index, VecIndex]:
        docs_bm25 = [
            BM25Doc(
                chunk_id="seed:1",
                paper_id="p1",
                page_start=1,
                section="A",
                text="seed text",
                clean_text="seed text",
                content_type="body",
            ),
            BM25Doc(
                chunk_id="adj:1",
                paper_id="p1",
                page_start=2,
                section="A",
                text="adjacent detail evidence",
                clean_text="adjacent detail evidence",
                content_type="body",
            ),
            BM25Doc(
                chunk_id="ent:1",
                paper_id="p1",
                page_start=3,
                section="A",
                text="entity linked detail evidence",
                clean_text="entity linked detail evidence",
                content_type="body",
            ),
            BM25Doc(
                chunk_id="front:1",
                paper_id="p1",
                page_start=4,
                section="A",
                text="Author Alice University",
                clean_text="author alice university",
                content_type="front_matter",
            ),
            BM25Doc(
                chunk_id="ref:1",
                paper_id="p1",
                page_start=5,
                section="A",
                text="Reference scale and citation",
                clean_text="reference scale citation",
                content_type="reference",
            ),
        ]
        docs_vec = [
            VecDoc(
                chunk_id=d.chunk_id,
                paper_id=d.paper_id,
                page_start=d.page_start,
                section=d.section,
                text=d.text,
                clean_text=d.clean_text,
                content_type=d.content_type,
            )
            for d in docs_bm25
        ]
        bm25 = BM25Index(docs=docs_bm25, avg_doc_len=1.0, doc_lens=[1] * len(docs_bm25), inverted={}, idf={})
        vec = VecIndex(docs=docs_vec, idf={}, doc_vectors=[{} for _ in docs_vec], doc_norms=[1.0 for _ in docs_vec])
        return bm25, vec

    def _write_graph(self, path: Path) -> None:
        nodes = {
            "seed:1": GraphNode("seed:1", "p1", 1, "A", "body", []),
            "adj:1": GraphNode("adj:1", "p1", 2, "A", "body", []),
            "ent:1": GraphNode("ent:1", "p1", 3, "A", "body", []),
            "front:1": GraphNode("front:1", "p1", 4, "A", "front_matter", []),
            "ref:1": GraphNode("ref:1", "p1", 5, "A", "reference", []),
            "wm:1": GraphNode("wm:1", "p1", 6, "A", "watermark", []),
        }
        graph = ChunkGraph(
            nodes=nodes,
            adjacent={
                "seed:1": ["adj:1", "front:1", "wm:1"],
                "adj:1": ["seed:1"],
                "ent:1": [],
                "front:1": ["seed:1"],
                "ref:1": [],
                "wm:1": ["seed:1"],
            },
            entity={
                "seed:1": [("ent:1", 2), ("ref:1", 1), ("adj:1", 1)],
                "adj:1": [],
                "ent:1": [],
                "front:1": [],
                "ref:1": [],
                "wm:1": [],
            },
            stats=GraphBuildStats(),
            config={},
        )
        save_graph(graph, path)

    def test_expand_filters_and_dedup_and_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            self._write_graph(graph_path)
            bm25, vec = self._build_indexes()
            cfg = PipelineConfig(
                graph_path=str(graph_path),
                graph_expand_alpha=2.0,
                graph_expand_max_candidates=3,
            )
            seeds = [RetrievalCandidate(chunk_id="seed:1", score=1.0, paper_id="p1", text="seed text", clean_text="seed text")]
            merged, stats = expand_candidates_with_graph(
                seeds,
                query="generic question",
                top_k=1,
                bm25_index=bm25,
                vec_index=vec,
                config=cfg,
            )
            ids = [c.chunk_id for c in merged]
            self.assertEqual(ids[0], "seed:1")
            self.assertIn("adj:1", ids)
            self.assertIn("ent:1", ids)
            self.assertEqual(len(ids), 3)
            self.assertNotIn("front:1", ids)
            self.assertNotIn("ref:1", ids)
            self.assertNotIn("wm:1", ids)
            self.assertEqual(stats["adjacent_queries"], 1)
            self.assertEqual(stats["entity_queries"], 1)
            self.assertGreaterEqual(stats["duplicate_hits"], 1)
            self.assertEqual(stats["added"], 2)
            expanded = {c.chunk_id: c for c in merged}
            self.assertEqual(expanded["adj:1"].payload.get("source"), "graph_expand")
            self.assertEqual(expanded["adj:1"].payload.get("retrieval_source"), "adjacent")
            self.assertEqual(expanded["ent:1"].payload.get("source"), "graph_expand")
            self.assertAlmostEqual(expanded["adj:1"].score, 0.97, places=6)
            self.assertAlmostEqual(expanded["ent:1"].score, 0.94, places=6)
            with patch("app.retrieve.fetch_embeddings") as mocked_embed:
                _merged, _stats = expand_candidates_with_graph(
                    seeds,
                    query="generic question",
                    top_k=1,
                    bm25_index=bm25,
                    vec_index=vec,
                    config=cfg,
                )
                mocked_embed.assert_not_called()

    def test_expand_fallback_when_graph_missing(self) -> None:
        bm25, vec = self._build_indexes()
        cfg = PipelineConfig(graph_path="/tmp/not-exist-graph.json", graph_expand_alpha=2.0, graph_expand_max_candidates=200)
        seeds = [RetrievalCandidate(chunk_id="seed:1", score=1.0, paper_id="p1")]
        merged, stats = expand_candidates_with_graph(
            seeds,
            query="any",
            top_k=1,
            bm25_index=bm25,
            vec_index=vec,
            config=cfg,
        )
        self.assertEqual([c.chunk_id for c in merged], ["seed:1"])
        self.assertFalse(stats["graph_loaded"])
        self.assertEqual(stats.get("reason"), "graph_unavailable")

    def test_expand_releases_front_matter_when_author_intent_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            self._write_graph(graph_path)
            bm25, vec = self._build_indexes()
            cfg = PipelineConfig(
                graph_path=str(graph_path),
                graph_expand_alpha=2.0,
                graph_expand_max_candidates=10,
            )
            seeds = [RetrievalCandidate(chunk_id="seed:1", score=1.0, paper_id="p1")]
            merged, _ = expand_candidates_with_graph(
                seeds,
                query="author affiliation institute email",
                top_k=1,
                bm25_index=bm25,
                vec_index=vec,
                config=cfg,
            )
            ids = [c.chunk_id for c in merged]
            self.assertIn("front:1", ids)

    def test_expand_releases_reference_when_reference_intent_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            self._write_graph(graph_path)
            bm25, vec = self._build_indexes()
            cfg = PipelineConfig(
                graph_path=str(graph_path),
                graph_expand_alpha=2.0,
                graph_expand_max_candidates=10,
            )
            seeds = [RetrievalCandidate(chunk_id="seed:1", score=1.0, paper_id="p1")]
            merged, _ = expand_candidates_with_graph(
                seeds,
                query="reference citation validate scale questionnaire",
                top_k=3,
                bm25_index=bm25,
                vec_index=vec,
                config=cfg,
            )
            ids = [c.chunk_id for c in merged]
            self.assertIn("ref:1", ids)

    def test_expand_inherits_backend_payload_from_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            self._write_graph(graph_path)
            bm25, vec = self._build_indexes()
            cfg = PipelineConfig(
                graph_path=str(graph_path),
                dense_backend="embedding",
                graph_expand_alpha=2.0,
                graph_expand_max_candidates=10,
            )
            seeds = [
                RetrievalCandidate(
                    chunk_id="seed:1",
                    score=1.0,
                    paper_id="p1",
                    payload={
                        "source": "hybrid",
                        "dense_backend": "embedding",
                        "retrieval_mode": "hybrid",
                        "embedding_provider": "siliconflow",
                        "embedding_model": "fake-embed-model",
                        "embedding_version": "v1",
                    },
                )
            ]
            merged, _ = expand_candidates_with_graph(
                seeds,
                query="reference citation validate scale questionnaire",
                top_k=3,
                bm25_index=bm25,
                vec_index=vec,
                config=cfg,
            )
            expanded = [c for c in merged if c.chunk_id != "seed:1"]
            self.assertTrue(expanded)
            for row in expanded:
                self.assertEqual(row.payload.get("source"), "graph_expand")
                self.assertEqual(row.payload.get("dense_backend"), "embedding")
                self.assertEqual(row.payload.get("retrieval_mode"), "hybrid")
                self.assertEqual(row.payload.get("embedding_provider"), "siliconflow")
                self.assertEqual(row.payload.get("embedding_model"), "fake-embed-model")
                self.assertEqual(row.payload.get("embedding_version"), "v1")


if __name__ == "__main__":
    unittest.main()
