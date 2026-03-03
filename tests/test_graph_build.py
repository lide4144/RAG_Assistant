from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.graph_build import build_graph, load_graph, run_graph_build


class GraphBuildTests(unittest.TestCase):
    def test_filter_rules_default_exclude_front_matter(self) -> None:
        rows = [
            {
                "chunk_id": "p1:00001",
                "paper_id": "p1",
                "page_start": 1,
                "clean_text": "A body chunk",
                "content_type": "body",
                "suppressed": False,
            },
            {
                "chunk_id": "p1:00002",
                "paper_id": "p1",
                "page_start": 2,
                "clean_text": "hidden",
                "content_type": "body",
                "suppressed": True,
            },
            {
                "chunk_id": "p1:00003",
                "paper_id": "p1",
                "page_start": 3,
                "clean_text": "water",
                "content_type": "watermark",
                "suppressed": False,
            },
            {
                "chunk_id": "p1:00004",
                "paper_id": "p1",
                "page_start": 4,
                "clean_text": "dept university",
                "content_type": "front_matter",
                "suppressed": False,
            },
        ]
        graph = build_graph(rows)
        self.assertEqual(graph.stats.kept_nodes, 1)
        self.assertEqual(graph.stats.excluded_suppressed, 1)
        self.assertEqual(graph.stats.excluded_watermark, 1)
        self.assertEqual(graph.stats.excluded_front_matter, 1)

    def test_include_front_matter_when_enabled(self) -> None:
        rows = [
            {
                "chunk_id": "p1:00001",
                "paper_id": "p1",
                "page_start": 1,
                "clean_text": "Dept of University",
                "content_type": "front_matter",
                "suppressed": False,
            }
        ]
        graph = build_graph(rows, include_front_matter=True)
        self.assertIn("p1:00001", graph.nodes)

    def test_adjacent_edges_respect_section(self) -> None:
        rows = [
            {"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "section": "A", "clean_text": "a", "content_type": "body"},
            {"chunk_id": "p1:00002", "paper_id": "p1", "page_start": 1, "section": "A", "clean_text": "b", "content_type": "body"},
            {"chunk_id": "p1:00003", "paper_id": "p1", "page_start": 2, "section": "B", "clean_text": "c", "content_type": "body"},
            {"chunk_id": "p1:00004", "paper_id": "p1", "page_start": 3, "clean_text": "d", "content_type": "body"},
        ]
        graph = build_graph(rows)
        self.assertIn("p1:00002", graph.neighbors("p1:00001", type="adjacent"))
        self.assertNotIn("p1:00003", graph.neighbors("p1:00002", type="adjacent"))
        self.assertIn("p1:00004", graph.neighbors("p1:00003", type="adjacent"))

    def test_entity_fallback_extraction_and_top_m(self) -> None:
        rows = [
            {"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "clean_text": "Use PLA and GUESS-18 in GameUserExperience", "content_type": "body"},
            {"chunk_id": "p1:00002", "paper_id": "p1", "page_start": 2, "clean_text": "PLA baseline", "content_type": "body"},
            {"chunk_id": "p1:00003", "paper_id": "p1", "page_start": 3, "clean_text": "PLA variant", "content_type": "body"},
            {"chunk_id": "p1:00004", "paper_id": "p1", "page_start": 4, "clean_text": "PLA extended", "content_type": "body"},
        ]
        graph = build_graph(rows, entity_top_m=2)
        entities = graph.nodes["p1:00001"].entities
        self.assertIn("PLA", entities)
        self.assertIn("GUESS-18", entities)
        self.assertIn("GameUserExperience", entities)
        self.assertLessEqual(len(graph.neighbors("p1:00001", type="entity")), 2)

    def test_entity_threshold_boundary_no_edge_when_below_threshold(self) -> None:
        rows = [
            {"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "entities": ["PLA"], "clean_text": "PLA", "content_type": "body"},
            {"chunk_id": "p1:00002", "paper_id": "p1", "page_start": 2, "entities": ["PLA"], "clean_text": "PLA", "content_type": "body"},
        ]
        graph = build_graph(rows, entity_overlap_threshold=2)
        self.assertEqual(graph.neighbors("p1:00001", type="entity"), [])
        self.assertEqual(graph.neighbors("p1:00002", type="entity"), [])

    def test_save_load_and_neighbors_with_weight(self) -> None:
        rows = [
            {"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "clean_text": "PLA", "content_type": "body"},
            {"chunk_id": "p1:00002", "paper_id": "p1", "page_start": 2, "clean_text": "PLA", "content_type": "body"},
        ]
        graph = build_graph(rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text(json.dumps(graph.to_dict(), ensure_ascii=False), encoding="utf-8")
            loaded = load_graph(path)
            weighted = loaded.neighbors_with_weight("p1:00001", type="entity")
            self.assertTrue(weighted)
            self.assertEqual(weighted[0]["edge_type"], "entity")

    def test_cli_run_graph_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "chunks_clean.jsonl"
            output_path = Path(tmp) / "graph.pkl"
            rows = [
                {"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "clean_text": "PLA", "content_type": "body"},
                {"chunk_id": "p1:00002", "paper_id": "p1", "page_start": 2, "clean_text": "PLA", "content_type": "body"},
            ]
            with input_path.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            code = run_graph_build(input_path, output_path, threshold=1, top_m=30)
            self.assertEqual(code, 0)
            self.assertTrue(output_path.exists())
            loaded = load_graph(output_path)
            self.assertIn("p1:00002", loaded.neighbors("p1:00001", type="adjacent"))


if __name__ == "__main__":
    unittest.main()
