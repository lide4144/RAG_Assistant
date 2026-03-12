from __future__ import annotations

import os
import unittest
from unittest.mock import patch
import time
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.kernel_api import (
    app,
    _TASK_CANCEL_EVENTS,
    _TASKS,
    _TASKS_LOCK,
    _build_marker_artifacts,
    cancel_task,
    KernelChatRequest,
    KernelChatResponse,
    SourceItem,
    TaskProgressInfo,
    TaskStatusResponse,
    get_latest_import_result,
    _build_sources_from_qa_report,
    get_task_status,
    _run_qa_once,
    qa_stream,
    start_graph_build_task,
    _start_library_import_task,
    GraphBuildTaskStartRequest,
)


class KernelApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        with _TASKS_LOCK:
            _TASKS.clear()
            _TASK_CANCEL_EVENTS.clear()
        self.client = TestClient(app)

    def test_source_contract_isomorphic_fields(self) -> None:
        qa_report = {
            'evidence_grouped': [
                {
                    'paper_id': 'p1',
                    'paper_title': 'Paper A',
                    'evidence': [
                        {
                            'chunk_id': 'chunk-1',
                            'quote': 'alpha',
                            'section_page': 'p.1',
                            'source': 'graph_expand',
                            'score_rerank': 0.88,
                        }
                    ],
                }
            ]
        }
        sources = _build_sources_from_qa_report(qa_report)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].source_type, 'graph')
        self.assertEqual(sources[0].source_id, 'chunk-1')
        self.assertEqual(sources[0].title, 'Paper A')
        self.assertEqual(sources[0].snippet, 'alpha')
        self.assertEqual(sources[0].locator, 'p.1')

    def test_run_qa_once_contract(self) -> None:
        payload = KernelChatRequest(sessionId='s1', mode='local', query='q1', traceId='trace-1')

        with (
            patch('app.kernel_api.run_qa', return_value=0),
            patch(
                'app.kernel_api._load_qa_report',
                return_value={
                    'answer': 'hello [1]',
                    'evidence_grouped': [
                        {
                            'paper_id': 'p1',
                            'paper_title': 'Paper A',
                            'evidence': [
                                {
                                    'chunk_id': 'chunk-1',
                                    'quote': 'snippet',
                                    'section_page': 'p.1',
                                    'source': 'local',
                                    'score_rerank': 0.91,
                                }
                            ],
                        }
                    ],
                },
            ),
        ):
            response = _run_qa_once(payload)

        self.assertIsInstance(response, KernelChatResponse)
        self.assertEqual(response.traceId, 'trace-1')
        self.assertEqual(response.answer, 'hello [1]')
        self.assertEqual(len(response.sources), 1)
        self.assertIsInstance(response.sources[0], SourceItem)

    def test_stream_contract_mode_consistency_and_message_end(self) -> None:
        modes = ("local", "web", "hybrid")

        for mode in modes:
            with self.subTest(mode=mode):
                mocked_response = KernelChatResponse(
                    traceId=f"trace-{mode}",
                    answer="stream answer [1]",
                    sources=[
                        SourceItem(
                            source_type="local",
                            source_id="chunk-1",
                            title="Paper A",
                            snippet="snippet",
                            locator="p.1",
                            score=0.9,
                        )
                    ],
                )
                with patch("app.kernel_api._run_qa_once", return_value=mocked_response):
                    response = qa_stream(
                        KernelChatRequest(sessionId="s1", mode=mode, query="q1", history=[], traceId=f"trace-{mode}")
                    )
                    self.assertTrue((response.media_type or "").startswith("text/event-stream"))
                    self.assertIsNotNone(response.body_iterator)

    def test_graph_build_task_start_and_status_contract(self) -> None:
        def _fake_run_graph_build(
            _input: str,
            _output: str,
            *,
            threshold: int = 1,
            top_m: int = 30,
            include_front_matter: bool = False,
            on_progress=None,
        ) -> int:
            _ = (threshold, top_m, include_front_matter)
            if on_progress is not None:
                on_progress(
                    {
                        "stage": "extract_entities",
                        "processed": 2,
                        "total": 4,
                        "elapsed_ms": 100,
                        "message": "2/4",
                    }
                )
                on_progress(
                    {
                        "stage": "done",
                        "processed": 4,
                        "total": 4,
                        "elapsed_ms": 200,
                        "message": "done",
                    }
                )
            return 0

        with patch("app.kernel_api.run_graph_build", side_effect=_fake_run_graph_build):
            started = start_graph_build_task(GraphBuildTaskStartRequest())
            self.assertEqual(started.task_kind, "graph_build")
            self.assertIn(started.state, {"queued", "running", "succeeded"})
            for _ in range(20):
                current = get_task_status(started.task_id)
                if current.state == "succeeded":
                    break
            self.assertEqual(current.state, "succeeded")
            self.assertIsNotNone(current.progress)
            self.assertIn(current.progress.stage, {"extract_entities", "done", "persist_graph"})

    def test_graph_build_task_error_contains_recovery(self) -> None:
        with patch("app.kernel_api.run_graph_build", side_effect=RuntimeError("boom")):
            started = start_graph_build_task(GraphBuildTaskStartRequest(force_new=True))
            for _ in range(20):
                current = get_task_status(started.task_id)
                if current.state == "failed":
                    break
            self.assertEqual(current.state, "failed")
            self.assertIsNotNone(current.error)
            self.assertTrue(bool(current.error.recovery))

    def test_graph_build_task_supports_cancel(self) -> None:
        def _slow_graph_build(
            _input: str,
            _output: str,
            *,
            threshold: int = 1,
            top_m: int = 30,
            include_front_matter: bool = False,
            on_progress=None,
        ) -> int:
            _ = (threshold, top_m, include_front_matter)
            for idx in range(20):
                if on_progress is not None:
                    on_progress(
                        {
                            "stage": "extract_entities",
                            "processed": idx + 1,
                            "total": 20,
                            "elapsed_ms": (idx + 1) * 100,
                            "message": f"{idx + 1}/20",
                        }
                    )
                time.sleep(0.01)
            return 0

        with patch("app.kernel_api.run_graph_build", side_effect=_slow_graph_build):
            started = start_graph_build_task(GraphBuildTaskStartRequest(force_new=True))
            cancelled = cancel_task(started.task_id)
            self.assertTrue(cancelled.cancelled)
            self.assertEqual(cancelled.state, "cancelled")
            for _ in range(50):
                current = get_task_status(started.task_id)
                if current.state == "cancelled":
                    break
                time.sleep(0.01)
            self.assertEqual(current.state, "cancelled")
            for _ in range(100):
                with _TASKS_LOCK:
                    if started.task_id not in _TASK_CANCEL_EVENTS:
                        break
                time.sleep(0.01)

    def test_latest_import_result_reads_ingest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "import_demo"
            run_dir.mkdir(parents=True, exist_ok=True)
            report_path = run_dir / "ingest_report.json"
            report_path.write_text(
                (
                    '{"import_summary":{"added":1,"skipped":2,"failed":1},'
                    '"import_outcomes":[{"status":"failed","reason":"bad pdf"}],'
                    '"import_stage":{"updated_at":"2026-03-06T00:00:01Z"},'
                    '"clean_stage":{"updated_at":"2026-03-06T00:00:01Z"},'
                    '"index_stage":{"status":"success","updated_at":"2026-03-06T00:00:02Z"}}'
                ),
                encoding="utf-8",
            )

            with (
                patch("app.kernel_api.RUNS_DIR", Path(tmp)),
                patch("app.kernel_api.load_papers", return_value=[{"paper_id": "p1"}]),
                patch("app.kernel_api._read_latest_pipeline_status", return_value=None),
            ):
                result = get_latest_import_result()
                self.assertEqual(result.added, 1)
                self.assertEqual(result.skipped, 2)
                self.assertEqual(result.failed, 1)
                self.assertEqual(result.failure_reasons, ["bad pdf"])
                self.assertEqual([stage.stage for stage in result.pipeline_stages], ["import", "clean", "index", "graph_build"])
                self.assertEqual(result.pipeline_stages[0].state, "succeeded")
                self.assertEqual(result.pipeline_stages[1].state, "succeeded")
                self.assertEqual(result.pipeline_stages[0].updated_at, "2026-03-06T00:00:01Z")
                self.assertEqual(result.pipeline_stages[2].updated_at, "2026-03-06T00:00:02Z")
                self.assertEqual(result.stage_updated_at["import"], "2026-03-06T00:00:01Z")
                self.assertEqual(result.stage_updated_at["index"], "2026-03-06T00:00:02Z")

    def test_marker_artifacts_compare_against_related_stage_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            processed = data_dir / "processed"
            indexes = data_dir / "indexes"
            processed.mkdir(parents=True, exist_ok=True)
            indexes.mkdir(parents=True, exist_ok=True)

            artifacts = {
                processed / "chunks.jsonl": 1710000000,
                processed / "chunks_clean.jsonl": 1710000005,
                processed / "papers.json": 1710000000,
                processed / "paper_summary.json": 1710000005,
                indexes / "bm25_index.json": 1710000010,
                indexes / "vec_index.json": 1710000020,
                indexes / "vec_index_embed.json": 1710000020,
            }
            for path, ts in artifacts.items():
                path.write_text("{}", encoding="utf-8")
                os.utime(path, (ts, ts))

            with patch(
                "app.kernel_api._ARTIFACT_INDEX",
                (
                    ("indexes:bmp25", indexes / "bm25_index.json", "bm25-index", "index"),
                    ("indexes:vec", indexes / "vec_index.json", "vector-index", "index"),
                    ("indexes:embed", indexes / "vec_index_embed.json", "embedding-index", "index"),
                    ("processed:chunks", processed / "chunks.jsonl", "chunks", "import"),
                    ("processed:chunks_clean", processed / "chunks_clean.jsonl", "clean-chunks", "clean"),
                    ("processed:papers", processed / "papers.json", "papers-catalog", "import"),
                    ("processed:paper_summary", processed / "paper_summary.json", "paper-summary", "clean"),
                ),
            ):
                items = _build_marker_artifacts(
                    stage_updated_at={
                        "import": "2024-03-09T16:00:00Z",
                        "clean": "2024-03-09T16:00:05Z",
                        "index": "2024-03-09T16:00:20Z",
                    }
                )

            by_key = {item.key: item for item in items}
            self.assertEqual(by_key["processed:chunks"].status, "healthy")
            self.assertEqual(by_key["processed:chunks_clean"].status, "healthy")
            self.assertEqual(by_key["processed:papers"].status, "healthy")
            self.assertEqual(by_key["indexes:bmp25"].status, "stale")
            self.assertEqual(by_key["indexes:vec"].status, "healthy")

    def test_library_import_task_runs_in_background(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload = Path(tmp) / "demo.pdf"
            upload.write_bytes(b"%PDF-1.4\n")

            with patch(
                "app.kernel_api.run_import_workflow",
                return_value={"ok": True, "message": "导入完成", "success_count": 1, "failed_count": 0},
            ):
                started = _start_library_import_task(
                    task_id="task_library_import_test",
                    upload_paths=[upload],
                    topic="topic-a",
                )
                self.assertEqual(started.task_kind, "library_import")
                self.assertIn(started.state, {"queued", "running", "succeeded"})
                for _ in range(20):
                    current = get_task_status(started.task_id)
                    if current.state == "succeeded":
                        break
                    time.sleep(0.01)
                self.assertEqual(current.state, "succeeded")
                self.assertIsNotNone(current.result)
                self.assertEqual(current.result.get("success_count"), 1)

    def test_library_import_endpoint_returns_accepted_task_immediately(self) -> None:
        with patch("app.kernel_api.run_import_workflow", side_effect=lambda **_: {"ok": True, "message": "导入完成"}):
            response = self.client.post(
                "/api/library/import",
                data={"topic": "topic-a"},
                files={"files": ("demo.pdf", b"%PDF-1.4\n", "application/pdf")},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["task_kind"], "library_import")
        self.assertIn(payload["task_state"], {"queued", "running", "succeeded"})
        self.assertTrue(str(payload["message"]).startswith("已接收"))

    def test_library_import_endpoint_reuses_active_task(self) -> None:
        with _TASKS_LOCK:
            _TASKS["task_library_import_existing"] = TaskStatusResponse(
                task_id="task_library_import_existing",
                task_kind="library_import",
                state="running",
                created_at="2026-03-13T00:00:00Z",
                updated_at="2026-03-13T00:00:01Z",
                progress=TaskProgressInfo(
                    stage="import_prepare",
                    processed=2,
                    total=6,
                    elapsed_ms=500,
                    message="正在处理",
                ),
                accepted=True,
                error=None,
                result=None,
            )

        response = self.client.post(
            "/api/library/import",
            data={"topic": "topic-a"},
            files={"files": ("demo.pdf", b"%PDF-1.4\n", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["accepted"])
        self.assertEqual(payload["task_id"], "task_library_import_existing")
        self.assertEqual(payload["task_kind"], "library_import")
        self.assertEqual(payload["task_state"], "running")
        self.assertIn("复用", payload["message"])


if __name__ == '__main__':
    unittest.main()
