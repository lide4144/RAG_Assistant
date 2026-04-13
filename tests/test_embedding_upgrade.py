from __future__ import annotations

import json
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import PipelineConfig
from app.embedding_api import EmbeddingAPIError, fetch_embeddings
from app.index_bm25 import build_bm25_index
from app.index_vec import EmbeddingBuildStats, VecIndex, build_embedding_vec_index, build_vec_index, load_vec_index
from app.llm_client import clear_llm_event_callbacks, register_llm_event_callback
from app.qa import ensure_indexes
from app.retrieve import load_indexes_and_config, retrieve_candidates


def _fake_fetch_embeddings(texts, **kwargs):
    vectors = []
    for t in texts:
        t = (t or "").lower()
        vectors.append(
            [
                float("semantic" in t or "meaning" in t),
                float("game" in t or "play" in t),
                float(len(t.split()) % 5 + 1),
            ]
        )
    return vectors


class EmbeddingUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_llm_event_callbacks()

    def _write_chunks(self, path: Path) -> None:
        rows = [
            {
                "chunk_id": "c:1",
                "paper_id": "p1",
                "page_start": 1,
                "section": "Intro",
                "text": "Raw text semantic gameplay details",
                "clean_text": "semantic game details",
                "content_type": "body",
                "suppressed": False,
            },
            {
                "chunk_id": "c:2",
                "paper_id": "p1",
                "page_start": 2,
                "section": "Method",
                "text": "Raw text benchmark details",
                "clean_text": "benchmark details",
                "content_type": "body",
                "suppressed": False,
            },
            {
                "chunk_id": "c:wm",
                "paper_id": "p1",
                "page_start": 3,
                "section": None,
                "text": "Downloaded from IEEE",
                "clean_text": "downloaded ieee",
                "content_type": "watermark",
                "suppressed": False,
            },
            {
                "chunk_id": "c:s",
                "paper_id": "p1",
                "page_start": 4,
                "section": None,
                "text": "suppressed",
                "clean_text": "suppressed",
                "content_type": "body",
                "suppressed": True,
            },
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_many_chunks(self, path: Path, count: int) -> None:
        rows = []
        for i in range(count):
            rows.append(
                {
                    "chunk_id": f"cx:{i}",
                    "paper_id": "p1",
                    "page_start": i + 1,
                    "section": "Body",
                    "text": f"Raw text {i}",
                    "clean_text": f"semantic benchmark text {i}",
                    "content_type": "body",
                    "suppressed": False,
                }
            )
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_embedding_index_build_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            embed_idx = base / "vec_embed.json"
            cache_path = base / "embedding_cache.jsonl"
            self._write_chunks(chunks)

            cfg = PipelineConfig().embedding
            cfg.cache_path = str(cache_path)
            cfg.model = "fake-model"
            cfg.normalize = True

            with patch("app.index_vec.fetch_embeddings", side_effect=_fake_fetch_embeddings):
                index1, stats1 = build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)
                self.assertEqual(len(index1.docs), 2)
                self.assertEqual(index1.embedding_dim, 3)
                self.assertGreater(stats1.cache_miss, 0)

                index2, stats2 = build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)
                self.assertEqual(len(index2.docs), 2)
                self.assertGreaterEqual(stats2.cache_hits, 2)

            loaded = load_vec_index(embed_idx)
            self.assertEqual(loaded.index_type, "embedding")
            self.assertEqual(loaded.embedding_model, "fake-model")

    def test_embedding_failure_reason_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            embed_idx = base / "vec_embed.json"
            cache_path = base / "embedding_cache.jsonl"
            failure_path = base / "embedding_failures.jsonl"
            self._write_chunks(chunks)

            cfg = PipelineConfig().embedding
            cfg.cache_path = str(cache_path)
            cfg.failure_log_path = str(failure_path)
            cfg.model = "fake-model"

            def _flaky_fetch(texts, **kwargs):
                if any("benchmark" in (t or "").lower() for t in texts):
                    raise EmbeddingAPIError("synthetic-429")
                return _fake_fetch_embeddings(texts, **kwargs)

            with patch("app.index_vec.fetch_embeddings", side_effect=_flaky_fetch):
                _, stats = build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)

            self.assertEqual(stats.failed_items, 1)
            self.assertEqual(stats.failure_records_written, 1)
            self.assertTrue(failure_path.exists())
            rows = [json.loads(line) for line in failure_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["chunk_id"], "c:2")
            self.assertEqual(rows[0]["model"], "fake-model")
            self.assertEqual(rows[0]["retries"], 2)
            self.assertIn("synthetic-429", rows[0]["error"])

    def test_fetch_embeddings_emits_observability(self) -> None:
        events: list[dict[str, object]] = []
        register_llm_event_callback(events.append)

        class _Resp:
            headers = {"x-trace-id": "embed-trace-1"}

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"data": [{"embedding": [0.1, 0.2, 0.3]}]}, ensure_ascii=False).encode("utf-8")

        with (
            patch.dict("os.environ", {"TEST_EMBED_KEY": "token"}, clear=False),
            patch("urllib.request.urlopen", return_value=_Resp()),
        ):
            vectors = fetch_embeddings(
                ["semantic game details"],
                base_url="https://api.example.com/v1",
                model="embed-model",
                api_key_env="TEST_EMBED_KEY",
                provider="siliconflow",
            )

        self.assertEqual(vectors, [[0.1, 0.2, 0.3]])
        success_event = next(e for e in events if str(e.get("event")) == "request_success")
        self.assertEqual(success_event.get("debug_stage"), "embedding")
        self.assertEqual(success_event.get("endpoint"), "https://api.example.com/v1/embeddings")
        self.assertEqual(success_event.get("transport"), "urllib")
        self.assertIn('"model": "embed-model"', str(success_event.get("request_payload")))
        self.assertIn('"embedding": [', str(success_event.get("response_payload")))
        self.assertIn('"embedding_count": 1', str(success_event.get("response_text")))

    def test_max_concurrent_requests_limits_real_parallelism(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            embed_idx = base / "vec_embed.json"
            self._write_many_chunks(chunks, count=8)

            cfg = PipelineConfig().embedding
            cfg.model = "fake-model"
            cfg.cache_enabled = False
            cfg.batch_size = 1
            cfg.max_requests_per_minute = 10000
            cfg.max_concurrent_requests = 3

            lock = threading.Lock()
            in_flight = {"now": 0, "max": 0}

            def _slow_fetch(texts, **kwargs):
                with lock:
                    in_flight["now"] += 1
                    in_flight["max"] = max(in_flight["max"], in_flight["now"])
                time.sleep(0.03)
                out = _fake_fetch_embeddings(texts, **kwargs)
                with lock:
                    in_flight["now"] -= 1
                return out

            with patch("app.index_vec.fetch_embeddings", side_effect=_slow_fetch):
                _, stats = build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)

            self.assertEqual(stats.failed_items, 0)
            self.assertLessEqual(in_flight["max"], cfg.max_concurrent_requests)
            self.assertGreaterEqual(in_flight["max"], 2)

    def test_split_strategy_splits_and_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            embed_idx = base / "vec_embed.json"
            rows = [
                {
                    "chunk_id": "split:1",
                    "paper_id": "p1",
                    "page_start": 1,
                    "section": "Method",
                    "text": "raw",
                    "clean_text": " ".join(f"t{i}" for i in range(25)),
                    "content_type": "body",
                    "suppressed": False,
                }
            ]
            with chunks.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

            cfg = PipelineConfig().embedding
            cfg.model = "fake-model"
            cfg.normalize = False
            cfg.max_tokens_per_chunk = 5
            cfg.over_limit_strategy = "split"

            def _split_fetch(texts, **kwargs):
                return [[float(i + 1), float((i + 1) * 2)] for i, _ in enumerate(texts)]

            with patch("app.index_vec.fetch_embeddings", side_effect=_split_fetch):
                index, stats = build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)

            self.assertEqual(len(index.docs), 1)
            self.assertEqual(index.embeddings[0], [3.0, 6.0])
            self.assertEqual(stats.skipped_over_limit_count, 0)
            self.assertEqual(stats.failed_items, 0)

    def test_rate_limit_and_backoff_metrics_accumulate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            embed_idx = base / "vec_embed.json"
            self._write_chunks(chunks)

            cfg = PipelineConfig().embedding
            cfg.model = "fake-model"
            cfg.cache_enabled = False
            cfg.batch_size = 2
            cfg.max_retries = 2
            cfg.backoff_base_ms = 1
            cfg.backoff_max_ms = 4

            attempts: dict[str, int] = {}

            def _flaky_retry_fetch(texts, **kwargs):
                if len(texts) > 1:
                    raise EmbeddingAPIError(
                        "batch-429",
                        status_code=429,
                        trace_id="trace-batch",
                        response_body="synthetic batch body",
                        recoverable=True,
                        category="rate_limit",
                    )
                key = (texts[0] or "").lower()
                seen = attempts.get(key, 0)
                attempts[key] = seen + 1
                if seen == 0:
                    if "semantic" in key:
                        raise EmbeddingAPIError(
                            "item-429",
                            status_code=429,
                            recoverable=True,
                            category="rate_limit",
                        )
                    raise EmbeddingAPIError(
                        "item-503",
                        status_code=503,
                        recoverable=True,
                        category="server_error",
                    )
                return _fake_fetch_embeddings(texts, **kwargs)

            with patch("app.index_vec.fetch_embeddings", side_effect=_flaky_retry_fetch):
                _, stats = build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)

            self.assertEqual(stats.failed_items, 0)
            self.assertGreaterEqual(stats.rate_limited_count, 2)
            self.assertGreater(stats.backoff_total_ms, 0)
            self.assertTrue(stats.embedding_batch_failures)
            self.assertEqual(stats.embedding_batch_failures[0]["status_code"], 429)
            self.assertEqual(stats.embedding_batch_failures[0]["trace_id"], "trace-batch")
            self.assertEqual(stats.embedding_batch_failures[0]["response_body"], "synthetic batch body")

    def test_dense_backend_embedding_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            tfidf_idx = base / "vec_tfidf.json"
            embed_idx = base / "vec_embed.json"
            cache_path = base / "embedding_cache.jsonl"
            cfg_path = base / "cfg.yaml"
            self._write_chunks(chunks)

            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, tfidf_idx)

            cfg = PipelineConfig().embedding
            cfg.cache_path = str(cache_path)
            cfg.model = "fake-model"
            with patch("app.index_vec.fetch_embeddings", side_effect=_fake_fetch_embeddings):
                build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)

            cfg_path.write_text(
                "dense_backend: embedding\n"
                "embedding:\n"
                "  enabled: true\n"
                "  provider: siliconflow\n"
                "  model: fake-model\n"
                f"  cache_path: {cache_path}\n",
                encoding="utf-8",
            )

            bm25, vec, embed, config, _ = load_indexes_and_config(
                bm25_index_path=str(bm25_idx),
                vec_index_path=str(tfidf_idx),
                embed_index_path=str(embed_idx),
                config_path=str(cfg_path),
                include_embed_index=True,
            )
            metrics = {}
            with patch("app.retrieve.fetch_embeddings", side_effect=_fake_fetch_embeddings):
                out = retrieve_candidates(
                    "semantic meaning for gameplay",
                    mode="dense",
                    top_k=5,
                    bm25_index=bm25,
                    vec_index=vec,
                    embed_index=embed,
                    config=config,
                    runtime_metrics=metrics,
                )
            self.assertTrue(out)
            self.assertEqual(metrics.get("dense_score_type"), "cosine")
            self.assertIn("embedding_query_time_ms", metrics)
            for row in out:
                payload = row.payload or {}
                self.assertEqual(payload.get("dense_backend"), "embedding")
                self.assertEqual(payload.get("retrieval_mode"), "dense")
                self.assertEqual(payload.get("embedding_provider"), "siliconflow")
                self.assertEqual(payload.get("embedding_model"), "fake-model")

    def test_ensure_indexes_rebuilds_invalid_embedding_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            tfidf_idx = base / "vec_tfidf.json"
            embed_idx = base / "vec_embed.json"
            cfg_path = base / "cfg.yaml"
            self._write_chunks(chunks)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, tfidf_idx)

            # Simulate stale/broken embedding index from previous failed build.
            embed_idx.write_text(
                json.dumps(
                    {
                        "embedding_provider": "siliconflow",
                        "embedding_model": "fake-model",
                        "embedding_dim": 1,
                        "docs": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            cfg_path.write_text(
                "dense_backend: embedding\n"
                "embedding:\n"
                "  enabled: true\n"
                "  provider: siliconflow\n"
                "  model: fake-model\n",
                encoding="utf-8",
            )

            backend = Mock()
            backend.rebuild.return_value = (
                VecIndex(docs=[], idf={}, doc_vectors=[], doc_norms=[], index_type="embedding", embedding_dim=1024, embeddings=[]),
                EmbeddingBuildStats(),
            )
            with patch("app.qa.resolve_vector_backend", return_value=backend):
                ensure_indexes(
                    chunks_path=str(chunks),
                    bm25_index_path=str(bm25_idx),
                    vec_index_path=str(tfidf_idx),
                    embed_index_path=str(embed_idx),
                    config_path=str(cfg_path),
                    mode="dense",
                )
                self.assertTrue(backend.rebuild.called)

    def test_retrieve_candidates_uses_vector_backend_search_for_embedding_dense_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            tfidf_idx = base / "vec_tfidf.json"
            embed_idx = base / "vec_embed.json"
            cfg_path = base / "cfg.yaml"
            cache_path = base / "embedding_cache.jsonl"
            self._write_chunks(chunks)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, tfidf_idx)

            cfg = PipelineConfig().embedding
            cfg.cache_path = str(cache_path)
            cfg.model = "fake-model"
            with patch("app.index_vec.fetch_embeddings", side_effect=_fake_fetch_embeddings):
                build_embedding_vec_index(chunks, embed_idx, embedding_cfg=cfg)

            cfg_path.write_text(
                "dense_backend: embedding\n"
                "embedding:\n"
                "  enabled: true\n"
                "  provider: siliconflow\n"
                "  model: fake-model\n"
                f"  cache_path: {cache_path}\n",
                encoding="utf-8",
            )

            bm25, vec, embed, config, _ = load_indexes_and_config(
                bm25_index_path=str(bm25_idx),
                vec_index_path=str(tfidf_idx),
                embed_index_path=str(embed_idx),
                config_path=str(cfg_path),
                include_embed_index=True,
            )
            backend = Mock()
            backend.search.return_value = [(embed.docs[0], 0.9)]

            with (
                patch("app.retrieve.fetch_embeddings", side_effect=_fake_fetch_embeddings),
                patch("app.retrieve.resolve_vector_backend", return_value=backend),
            ):
                out = retrieve_candidates(
                    "semantic meaning for gameplay",
                    mode="dense",
                    top_k=5,
                    bm25_index=bm25,
                    vec_index=vec,
                    embed_index=embed,
                    embed_index_path=str(embed_idx),
                    config=config,
                    runtime_metrics={},
                )

            self.assertTrue(out)
            backend.search.assert_called_once()
            self.assertEqual(backend.search.call_args.kwargs["index_path"], str(embed_idx))


if __name__ == "__main__":
    unittest.main()
