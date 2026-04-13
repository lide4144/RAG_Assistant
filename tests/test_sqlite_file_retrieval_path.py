from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.library as library
from app.index_bm25 import build_bm25_index
from app.kernel_api import app
from app.qa import run_qa
from app.rewrite import RewriteResult
from app.intent_calibration import CalibrationResult
from app.vector_backend import FileVectorBackend


def _fake_fetch_embeddings(texts, **kwargs):
    vectors = []
    for text in texts:
        normalized = str(text or "").lower()
        vectors.append(
            [
                float("retrieval" in normalized or "检索" in normalized),
                float("pipeline" in normalized or "流程" in normalized),
                float("transformer" in normalized or "attention" in normalized),
            ]
        )
    return vectors


class SQLiteFileRetrievalPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_import_catalog_filter_and_qa_work_with_file_vector_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_dir = base / "data"
            processed = data_dir / "processed"
            raw_imported = data_dir / "raw" / "imported"
            indexes = data_dir / "indexes"
            runs = base / "runs"
            processed.mkdir(parents=True, exist_ok=True)
            raw_imported.mkdir(parents=True, exist_ok=True)
            indexes.mkdir(parents=True, exist_ok=True)
            runs.mkdir(parents=True, exist_ok=True)

            doc = base / "retrieval-note.txt"
            doc.write_text(
                "Retrieval pipeline uses dense retrieval and reranking.\n"
                "The method combines transformer attention with chunked evidence.",
                encoding="utf-8",
            )

            config_path = base / "qa-config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "planner_enabled: false",
                        "answer_use_llm: false",
                        "sufficiency_gate_enabled: false",
                        "dense_backend: embedding",
                        "session_store_backend: file",
                        "rerank:",
                        "  enabled: false",
                        "embedding:",
                        "  enabled: true",
                        "  provider: fake",
                        "  model: fake-model",
                        "  api_key_env: TEST_EMBED_KEY",
                        "  normalize: true",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(library, "DATA_DIR", data_dir),
                patch.object(library, "RUNS_DIR", runs),
                patch.object(library, "DEFAULT_PAPERS_PATH", processed / "papers.json"),
                patch.object(library, "DEFAULT_TOPICS_PATH", data_dir / "library_topics.json"),
                patch.object(library, "DEFAULT_RAW_IMPORT_DIR", raw_imported),
                patch.object(library, "DEFAULT_PROCESSED_DIR", processed),
                patch("app.build_indexes.resolve_vector_backend", side_effect=lambda _name=None: FileVectorBackend(db_path=processed / "paper_store.sqlite3")),
                patch("app.index_vec.fetch_embeddings", side_effect=_fake_fetch_embeddings),
            ):
                result = library.run_import_workflow(uploaded_files=[doc], topic="专题A", config_path=str(config_path))

            self.assertTrue(result["ok"])
            papers_payload = json.loads((processed / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers_payload), 1)
            paper_id = str(papers_payload[0]["paper_id"])
            paper_title = str(papers_payload[0]["title"])

            with patch("app.kernel_api.DATA_DIR", data_dir):
                catalog_payload = self.client.get("/api/library/papers", params={"status": "ready"}).json()

            self.assertEqual(len(catalog_payload), 1)
            self.assertEqual(catalog_payload[0]["paper_id"], paper_id)

            bm25_index = indexes / "bm25_index.json"
            if not bm25_index.exists():
                build_bm25_index(processed / "chunks_clean.jsonl", bm25_index)

            qa_args = Namespace(
                q=f"In paper {paper_title}, what does the retrieval pipeline use?",
                chunks=str(processed / "chunks_clean.jsonl"),
                bm25_index=str(indexes / "bm25_index.json"),
                vec_index=str(indexes / "vec_index.json"),
                embed_index=str(indexes / "vec_index_embed.json"),
                config=str(config_path),
                mode="hybrid",
                top_k=4,
                session_id="sqlite-file-path",
                session_store=str(base / "session_store.json"),
                clear_session=False,
                run_dir=str(base / "qa-run"),
                run_id="",
                topic_name="专题A",
                topic_paper_ids=paper_id,
            )

            with (
                patch("app.retrieve.fetch_embeddings", side_effect=_fake_fetch_embeddings),
                patch(
                    "app.qa.rewrite_query",
                    return_value=RewriteResult(
                        question=qa_args.q,
                        rewritten_query=f"{paper_title} retrieval pipeline dense retrieval reranking",
                        rewrite_rule_query=f"{paper_title} retrieval pipeline dense retrieval reranking",
                        rewrite_llm_query=None,
                        keywords_entities={"keywords": ["retrieval", "pipeline"], "entities": [paper_title]},
                        strategy_hits=[],
                    ),
                ),
                patch(
                    "app.qa.calibrate_query_intent",
                    return_value=CalibrationResult(
                        calibrated_query=f"{paper_title} retrieval pipeline dense retrieval reranking",
                        calibration_reason={"rule": "identity"},
                    ),
                ),
            ):
                code = run_qa(qa_args)

            self.assertEqual(code, 0)
            report = json.loads((Path(qa_args.run_dir) / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("evidence_grouped"))
            self.assertEqual(report["evidence_grouped"][0]["paper_id"], paper_id)


if __name__ == "__main__":
    unittest.main()
