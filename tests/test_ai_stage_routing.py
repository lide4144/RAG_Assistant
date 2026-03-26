from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import load_and_validate_config
from app.embedding_api import _classify_http_error
from app.index_bm25 import build_bm25_index, load_bm25_index
from app.index_vec import VecIndex, build_vec_index, load_vec_index
from app.kernel_api import health_deps
from app.rerank import rerank_candidates
from app.retrieve import RetrievalCandidate, retrieve_candidates


class ConfigStageMappingTests(unittest.TestCase):
    def test_legacy_nested_config_maps_to_stage_prefixed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cfg.yaml"
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            cfg_path.write_text(
                "embedding:\n"
                "  provider: legacy-emb\n"
                "  base_url: https://emb.example.com/v1\n"
                "  model: emb-v1\n"
                "  api_key_env: EMB_KEY\n"
                "rerank:\n"
                "  provider: legacy-rerank\n"
                "  base_url: https://rr.example.com/v1\n"
                "  model: rr-v1\n"
                "  api_key_env: RR_KEY\n",
                encoding="utf-8",
            )
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                cfg, _ = load_and_validate_config(cfg_path)
        self.assertEqual(cfg.embedding_provider, "legacy-emb")
        self.assertEqual(cfg.embedding_api_base, "https://emb.example.com/v1")
        self.assertEqual(cfg.embedding.provider, "legacy-emb")
        self.assertEqual(cfg.rerank_provider, "legacy-rerank")
        self.assertEqual(cfg.rerank_api_base, "https://rr.example.com/v1")
        self.assertEqual(cfg.rerank.provider, "legacy-rerank")

    def test_stage_prefixed_fields_override_legacy_nested_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cfg.yaml"
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            cfg_path.write_text(
                "embedding_provider: stage-emb\n"
                "embedding_api_base: https://stage-emb.example.com/v1\n"
                "embedding:\n"
                "  provider: legacy-emb\n"
                "  base_url: https://legacy-emb.example.com/v1\n"
                "rerank_provider: stage-rerank\n"
                "rerank_api_base: https://stage-rerank.example.com/v1\n"
                "rerank:\n"
                "  provider: legacy-rerank\n"
                "  base_url: https://legacy-rerank.example.com/v1\n",
                encoding="utf-8",
            )
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                cfg, _ = load_and_validate_config(cfg_path)
        self.assertEqual(cfg.embedding.provider, "stage-emb")
        self.assertEqual(cfg.embedding.base_url, "https://stage-emb.example.com/v1")
        self.assertEqual(cfg.rerank.provider, "stage-rerank")
        self.assertEqual(cfg.rerank.base_url, "https://stage-rerank.example.com/v1")


class StageFallbackTests(unittest.TestCase):
    def _write_chunks(self, path: Path) -> None:
        rows = [
            {"chunk_id": "c1", "paper_id": "p1", "page_start": 1, "section": "s", "text": "alpha beta", "clean_text": "alpha beta", "content_type": "body"},
            {"chunk_id": "c2", "paper_id": "p1", "page_start": 2, "section": "s", "text": "gamma delta", "clean_text": "gamma delta", "content_type": "body"},
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_embedding_missing_key_falls_back_to_tfidf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks.jsonl"
            bm25_path = base / "bm25.json"
            vec_path = base / "vec.json"
            self._write_chunks(chunks)
            build_bm25_index(chunks, bm25_path)
            build_vec_index(chunks, vec_path)

            bm25 = load_bm25_index(bm25_path)
            vec = load_vec_index(vec_path)
            embed = VecIndex(docs=[], idf={}, doc_vectors=[], doc_norms=[], index_type="embedding", embedding_dim=3, embeddings=[])
            cfg, _ = load_and_validate_config()
            cfg.dense_backend = "embedding"
            cfg.embedding_api_key_env = "MISSING_STAGE_KEY"
            cfg.embedding.api_key_env = "MISSING_STAGE_KEY"
            metrics: dict[str, object] = {}
            with patch.dict(os.environ, {}, clear=False):
                out = retrieve_candidates(
                    "alpha",
                    mode="dense",
                    top_k=2,
                    bm25_index=bm25,
                    vec_index=vec,
                    embed_index=embed,
                    config=cfg,
                    runtime_metrics=metrics,
                )
        self.assertTrue(out)
        self.assertEqual(metrics.get("embedding_fallback_reason"), "missing_api_key")
        self.assertTrue(bool(metrics.get("embedding_fallback_success")))
        for row in out:
            self.assertEqual((row.payload or {}).get("dense_backend"), "tfidf")

    def test_rerank_failure_passthrough_marks_payload(self) -> None:
        cfg, _ = load_and_validate_config()
        cfg.rerank.enabled = True
        cfg.rerank.provider = "siliconflow"
        cfg.rerank.fallback_to_retrieval = True
        cfg.rerank.api_key_env = "MISSING_RERANK_KEY"
        cfg.rerank_api_key_env = "MISSING_RERANK_KEY"
        candidates = [
            RetrievalCandidate(
                chunk_id="a",
                score=0.8,
                payload={"source": "hybrid", "dense_backend": "tfidf", "score_retrieval": 0.8},
                text="a",
                clean_text="a",
            )
        ]
        with patch.dict(os.environ, {}, clear=False):
            out = rerank_candidates(query="a", candidates=candidates, config=cfg)
        self.assertTrue(out.used_fallback)
        self.assertIn("rerank_fallback_to_retrieval", out.warnings)
        payload = out.candidates[0].payload or {}
        self.assertTrue(bool(payload.get("used_fallback")))
        self.assertTrue(bool(payload.get("rerank_fallback_to_retrieval")))


class HealthDepsTests(unittest.TestCase):
    def test_health_deps_contains_three_stage_status(self) -> None:
        payload = health_deps()
        for stage in ("answer", "embedding", "rerank"):
            self.assertIn(stage, payload)
            self.assertIn("status", payload[stage])
            self.assertIn("provider", payload[stage])
            self.assertIn("model", payload[stage])
            self.assertIn("checked_at", payload[stage])
            self.assertIn("reason", payload[stage])
        self.assertIn("passthrough_mode", payload["rerank"])
        self.assertIn("fallback_mode", payload["embedding"])
        self.assertIn("planner", payload)
        self.assertIn("status", payload["planner"])
        self.assertIn("provider", payload["planner"])
        self.assertIn("model", payload["planner"])
        self.assertIn("checked_at", payload["planner"])
        self.assertIn("reason_code", payload["planner"])
        self.assertIn("service_mode", payload["planner"])
        self.assertIn("configured", payload["planner"])
        self.assertIn("blocked", payload["planner"])
        self.assertIn("formal_chat_available", payload["planner"])


class FailureClassificationTests(unittest.TestCase):
    def test_embedding_http_401_maps_to_auth_failed(self) -> None:
        recoverable, category = _classify_http_error(401, "unauthorized")
        self.assertFalse(recoverable)
        self.assertEqual(category, "auth_failed")


if __name__ == "__main__":
    unittest.main()
