from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

import httpx

from app.graph_build import (
    EntityExtractionResult,
    LLMExtractionMetrics,
    LLMEntityExtractionConfig,
    build_graph,
    extract_entities_from_text_llm,
    load_graph,
    run_graph_build,
)


class GraphBuildTests(unittest.TestCase):
    async def _fake_extractor(self, clean_text: str, _cfg: LLMEntityExtractionConfig) -> EntityExtractionResult:
        entities: list[dict[str, str]] = []
        if "PLA" in clean_text:
            entities.append({"entity_name": "PLA", "entity_type": "METHOD"})
        if "GUESS-18" in clean_text:
            entities.append({"entity_name": "GUESS-18", "entity_type": "MODEL"})
        if "GameUserExperience" in clean_text:
            entities.append({"entity_name": "GameUserExperience", "entity_type": "CONCEPT"})
        return EntityExtractionResult.model_validate({"entities": entities})

    async def _failing_extractor(self, _clean_text: str, _cfg: LLMEntityExtractionConfig) -> EntityExtractionResult:
        raise RuntimeError("simulated llm failure")

    class _FakeResponse:
        def __init__(self, status_code: int, body: dict | None = None) -> None:
            self.status_code = status_code
            self._body = body or {}

        def json(self) -> dict:
            return self._body

    class _FakeAsyncClient:
        def __init__(self, responses: list["GraphBuildTests._FakeResponse"]) -> None:
            self._responses = list(responses)

        async def post(self, _endpoint: str, *, headers: dict, json: dict) -> "GraphBuildTests._FakeResponse":
            _ = headers
            _ = json
            if not self._responses:
                raise AssertionError("No fake response available")
            return self._responses.pop(0)

        async def aclose(self) -> None:
            return None

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
        graph = build_graph(
            rows,
            entity_top_m=2,
            llm_entity_extractor=self._fake_extractor,
            llm_entity_config=LLMEntityExtractionConfig(max_concurrency=2),
        )
        entities = graph.nodes["p1:00001"].entities
        self.assertIn("PLA", entities)
        self.assertIn("GUESS-18", entities)
        self.assertIn("GameUserExperience", entities)
        self.assertLessEqual(len(graph.neighbors("p1:00001", type="entity")), 2)

    def test_entity_llm_failure_fallback_does_not_break_graph(self) -> None:
        rows = [
            {"chunk_id": "p1:00001", "paper_id": "p1", "page_start": 1, "clean_text": "PLA", "content_type": "body"},
            {"chunk_id": "p1:00002", "paper_id": "p1", "page_start": 2, "clean_text": "PLA", "content_type": "body"},
        ]
        graph = build_graph(
            rows,
            llm_entity_extractor=self._failing_extractor,
            llm_entity_config=LLMEntityExtractionConfig(max_concurrency=2),
        )
        self.assertEqual(graph.neighbors("p1:00001", type="entity"), [])
        self.assertIn("p1:00002", graph.neighbors("p1:00001", type="adjacent"))
        self.assertGreaterEqual(graph.stats.llm_entity_failures, 1)

    def test_extract_entities_429_retries_then_fallback(self) -> None:
        cfg = LLMEntityExtractionConfig(api_key_env="TEST_API_KEY", max_retries=1)
        metrics = LLMExtractionMetrics()
        client = self._FakeAsyncClient(
            [
                self._FakeResponse(429, body={}),
                self._FakeResponse(429, body={}),
            ]
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "token"}, clear=False):
            result = asyncio.run(
                extract_entities_from_text_llm(
                    "text for rate limit",
                    cfg,
                    client=cast(httpx.AsyncClient, client),
                    metrics=metrics,
                )
            )

        self.assertEqual(result.entities, [])
        self.assertEqual(metrics.calls, 2)
        self.assertEqual(metrics.rate_limits, 2)
        self.assertEqual(metrics.retries, 1)
        self.assertEqual(metrics.failures, 1)
        self.assertEqual(metrics.fallback_empty, 1)

    def test_extract_entities_invalid_json_retries_then_fallback(self) -> None:
        cfg = LLMEntityExtractionConfig(api_key_env="TEST_API_KEY", max_retries=1)
        metrics = LLMExtractionMetrics()
        client = self._FakeAsyncClient(
            [
                self._FakeResponse(
                    200,
                    body={"choices": [{"message": {"content": "not-a-json"}}]},
                ),
                self._FakeResponse(
                    200,
                    body={"choices": [{"message": {"content": "still-not-json"}}]},
                ),
            ]
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "token"}, clear=False):
            result = asyncio.run(
                extract_entities_from_text_llm(
                    "text for invalid json",
                    cfg,
                    client=cast(httpx.AsyncClient, client),
                    metrics=metrics,
                )
            )

        self.assertEqual(result.entities, [])
        self.assertEqual(metrics.calls, 2)
        self.assertEqual(metrics.retries, 1)
        self.assertEqual(metrics.failures, 1)
        self.assertEqual(metrics.fallback_empty, 1)

    def test_extract_entities_schema_validation_error_retries_then_fallback(self) -> None:
        cfg = LLMEntityExtractionConfig(api_key_env="TEST_API_KEY", max_retries=1)
        metrics = LLMExtractionMetrics()
        client = self._FakeAsyncClient(
            [
                self._FakeResponse(
                    200,
                    body={
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({"entities": [{"entity_name": "PLA"}]})
                                }
                            }
                        ]
                    },
                ),
                self._FakeResponse(
                    200,
                    body={
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({"entities": [{"entity_name": "PLA"}]})
                                }
                            }
                        ]
                    },
                ),
            ]
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "token"}, clear=False):
            result = asyncio.run(
                extract_entities_from_text_llm(
                    "text for schema error",
                    cfg,
                    client=cast(httpx.AsyncClient, client),
                    metrics=metrics,
                )
            )

        self.assertEqual(result.entities, [])
        self.assertEqual(metrics.calls, 2)
        self.assertEqual(metrics.retries, 1)
        self.assertEqual(metrics.failures, 1)
        self.assertEqual(metrics.fallback_empty, 1)

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
            {
                "chunk_id": "p1:00001",
                "paper_id": "p1",
                "page_start": 1,
                "clean_text": "PLA",
                "entities": ["PLA"],
                "content_type": "body",
            },
            {
                "chunk_id": "p1:00002",
                "paper_id": "p1",
                "page_start": 2,
                "clean_text": "PLA",
                "entities": ["PLA"],
                "content_type": "body",
            },
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
