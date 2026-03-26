from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch
import time
import tempfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.kernel_api import (
    app,
    _TASK_CANCEL_EVENTS,
    _TASKS,
    _TASKS_LOCK,
    _build_qa_args,
    _build_marker_artifacts,
    cancel_task,
    KernelChatRequest,
    KernelChatResponse,
    SourceItem,
    TaskProgressInfo,
    TaskStatusResponse,
    get_latest_import_result,
    _build_sources_from_qa_report,
    _derive_runtime_tool_fallback,
    _build_runtime_tool_results,
    _planner_runtime_route_executor,
    get_task_status,
    _run_qa_once,
    _run_planner_shell_once,
    qa_stream,
    planner_qa,
    planner_qa_stream,
    PlannerShadowReviewRequest,
    save_planner_shadow_review,
    start_graph_build_task,
    _start_library_import_task,
    GraphBuildTaskStartRequest,
)
from app.qa import _resolve_run_dir


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
        self.assertEqual(sources[0].provenance_type, 'citation')
        self.assertTrue(sources[0].citation_indexable)

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

    def test_build_qa_args_uses_request_config_path(self) -> None:
        payload = KernelChatRequest(
            sessionId="s1",
            mode="local",
            query="q1",
            history=[],
            traceId="trace-config",
            configPath="/tmp/runtime-config.yaml",
        )

        args = _build_qa_args(payload, run_id="run-config", on_stream_delta=None)

        self.assertEqual(args.config, "/tmp/runtime-config.yaml")

    def test_resolve_run_dir_prefers_run_id_when_run_dir_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = type("Args", (), {"run_dir": "", "run_id": "kernel_api_demo"})()
            with patch("app.qa.RUNS_DIR", Path(tmp)):
                run_dir = _resolve_run_dir(args)

            self.assertEqual(run_dir, Path(tmp) / "kernel_api_demo")
            self.assertTrue(run_dir.exists())

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

    def test_planner_qa_endpoint_uses_shell_runner(self) -> None:
        mocked_response = KernelChatResponse(
            traceId="trace-planner",
            answer="planner answer [1]",
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
        with patch("app.kernel_api._run_planner_shell_once", return_value=mocked_response):
            response = planner_qa(
                KernelChatRequest(sessionId="s1", mode="local", query="q1", history=[], traceId="trace-planner")
            )

        self.assertEqual(response.traceId, "trace-planner")
        self.assertEqual(response.answer, "planner answer [1]")

    def test_planner_qa_returns_503_when_planner_service_is_blocked(self) -> None:
        with patch(
            "app.kernel_api._load_planner_config_state",
            return_value=(
                object(),
                [],
                {
                    "formal_chat_available": False,
                    "blocked": True,
                    "service_mode": "production",
                    "reason_code": "planner_api_key_missing",
                    "reason_message": "Planner Runtime 缺少 API Key，正式聊天入口不可用。",
                },
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                planner_qa(
                    KernelChatRequest(sessionId="s1", mode="local", query="q1", history=[], traceId="trace-planner-blocked")
                )

        self.assertEqual(exc.exception.status_code, 503)
        self.assertEqual(exc.exception.detail["code"], "PLANNER_SYSTEM_BLOCKED")

    def test_planner_stream_contract_mode_consistency_and_message_end(self) -> None:
        mocked_response = KernelChatResponse(
            traceId="trace-planner-stream",
            answer="planner stream answer [1]",
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
        with patch("app.kernel_api._run_planner_shell_once", return_value=mocked_response):
            response = planner_qa_stream(
                KernelChatRequest(sessionId="s1", mode="local", query="q1", history=[], traceId="trace-planner-stream")
            )

        self.assertTrue((response.media_type or "").startswith("text/event-stream"))
        self.assertIsNotNone(response.body_iterator)

    def test_shadow_review_endpoint_rejects_invalid_trace_id_with_400(self) -> None:
        with self.assertRaises(HTTPException) as exc:
            save_planner_shadow_review(
                PlannerShadowReviewRequest(
                    trace_id="!!!",
                    label="accepted",
                )
            )

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail["code"], "INVALID_SHADOW_REVIEW")

    def test_runtime_tool_fallback_derives_from_short_circuit_trace(self) -> None:
        tool_fallback, reason, failed_tool = _derive_runtime_tool_fallback(
            {
                "short_circuit": {
                    "triggered": True,
                    "reason": "catalog_lookup_empty",
                    "step": "catalog_lookup",
                }
            },
            {},
        )

        self.assertTrue(tool_fallback)
        self.assertEqual(reason, "catalog_lookup_empty")
        self.assertEqual(failed_tool, "catalog_lookup")

    def test_runtime_observation_merges_into_run_artifacts(self) -> None:
        run_id = "kernel_api_runtime_merge"
        response = KernelChatResponse(
            traceId="trace-merge",
            answer="merged [1]",
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
        tool_calls = [{"id": "tool-1", "tool_name": "fact_qa", "produces": [], "status": "dispatched"}]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            for filename in ("run_trace.json", "qa_report.json"):
                (run_dir / filename).write_text(json.dumps({"answer": "ok"}, ensure_ascii=False), encoding="utf-8")

            with (
                patch("app.kernel_api.RUNS_DIR", Path(tmp)),
                patch("app.kernel_api._run_qa_pipeline", return_value=(response, run_id)),
            ):
                _ = _planner_runtime_route_executor(
                    KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-merge"),
                    selected_path="fact_qa",
                    runtime_fallback=False,
                    runtime_fallback_reason=None,
                    planner_result=None,
                    tool_calls=tool_calls,
                )

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            report = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))

        for payload in (trace, report):
            self.assertEqual(payload["runtime_contract_version"], "agent-first-v1")
            self.assertEqual(payload["tool_calls"][0]["tool_name"], "fact_qa")
            self.assertFalse(payload["tool_fallback"])
            self.assertEqual(payload["tool_results"][0]["status"], "succeeded")
            self.assertEqual(payload["tool_results"][0]["metadata"]["trace_id"], "trace-merge")
            self.assertEqual(payload["tool_results"][0]["sources"][0]["provenance_type"], "citation")
            self.assertTrue(payload["tool_results"][0]["sources"][0]["citation_indexable"])

    def test_runtime_tool_results_preserve_empty_result_failure_type(self) -> None:
        results = _build_runtime_tool_results(
            [{"tool_name": "catalog_lookup", "produces": ["paper_set"]}],
            selected_path="summary_passthrough",
            tool_fallback=True,
            tool_fallback_reason="catalog_lookup_empty",
            failed_tool="catalog_lookup",
            trace={
                "short_circuit": {
                    "triggered": True,
                    "reason": "catalog_lookup_empty",
                    "step": "catalog_lookup",
                }
            },
        )

        self.assertEqual(results[0]["error"]["code"], "empty_result")
        self.assertEqual(results[0]["error"]["user_safe_message"], "未找到符合条件的论文，因此未继续执行后续步骤。")

    def test_runtime_tool_results_preserve_missing_dependencies_failure_type(self) -> None:
        results = _build_runtime_tool_results(
            [{"tool_name": "cross_doc_summary", "produces": []}],
            selected_path="summary_passthrough",
            tool_fallback=True,
            tool_fallback_reason="missing_dependencies:paper_set",
            failed_tool="cross_doc_summary",
        )

        self.assertEqual(results[0]["error"]["code"], "missing_dependencies")
        self.assertEqual(results[0]["error"]["failed_dependency"], "paper_set")

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
                self.assertEqual(result.batch_total, 4)
                self.assertEqual(result.batch_completed, 3)
                self.assertEqual(result.batch_failed, 1)
                self.assertEqual(len(result.recent_items), 1)
                self.assertEqual(result.recent_items[0].state, "failed")

    def test_marker_artifacts_keep_same_run_indexes_healthy(self) -> None:
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
            self.assertEqual(by_key["indexes:bmp25"].status, "healthy")
            self.assertEqual(by_key["indexes:vec"].status, "healthy")
            self.assertEqual(by_key["indexes:embed"].status, "healthy")

    def test_marker_artifacts_mark_index_stale_when_input_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            processed = data_dir / "processed"
            indexes = data_dir / "indexes"
            processed.mkdir(parents=True, exist_ok=True)
            indexes.mkdir(parents=True, exist_ok=True)

            artifacts = {
                processed / "chunks.jsonl": 1710000000,
                processed / "chunks_clean.jsonl": 1710000020,
                indexes / "bm25_index.json": 1710000010,
                indexes / "vec_index.json": 1710000025,
                indexes / "vec_index_embed.json": 1710000030,
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
                ),
            ):
                items = _build_marker_artifacts(
                    stage_updated_at={
                        "import": "2024-03-09T16:00:20Z",
                        "clean": "2024-03-09T16:00:20Z",
                        "index": "2024-03-09T16:00:20Z",
                    }
                )

            by_key = {item.key: item for item in items}
            self.assertEqual(by_key["processed:chunks"].status, "healthy")
            self.assertEqual(by_key["processed:chunks_clean"].status, "healthy")
            self.assertEqual(by_key["indexes:bmp25"].status, "stale")
            self.assertEqual(by_key["indexes:bmp25"].health_message, "产物早于上游依赖，建议检查是否需要重建")
            self.assertEqual(by_key["indexes:vec"].status, "healthy")
            self.assertEqual(by_key["indexes:embed"].status, "healthy")

    def test_library_import_task_runs_in_background(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload = Path(tmp) / "demo.pdf"
            upload.write_bytes(b"%PDF-1.4\n")

            def _fake_import_workflow(*, progress_callback=None, **_kwargs):
                if callable(progress_callback):
                    progress_callback(
                        {
                            "stage": "import_clean",
                            "processed": 1,
                            "total": 3,
                            "stage_processed": 1,
                            "stage_total": 3,
                            "message": "正在处理 demo.pdf",
                            "batch_total": 3,
                            "batch_completed": 1,
                            "batch_running": 1,
                            "batch_failed": 0,
                            "current_stage": "import_clean",
                            "current_item_name": "demo.pdf",
                            "recent_items": [
                                {"name": "demo.pdf", "state": "running", "stage": "import_clean", "message": "抽取正文"},
                                {"name": "beta.pdf", "state": "queued", "stage": "import_clean", "message": "等待处理"},
                            ],
                        }
                    )
                return {
                    "ok": True,
                    "message": "导入完成",
                    "success_count": 1,
                    "failed_count": 0,
                    "import_summary": {"added": 1, "skipped": 1, "failed": 1, "total_candidates": 3},
                    "recent_items": [
                        {"name": "demo.pdf", "state": "succeeded", "stage": "done", "message": "完成"},
                        {"name": "broken.pdf", "state": "failed", "stage": "done", "message": "bad pdf"},
                    ],
                    "import_outcomes": [
                        {"source_uri": "demo.pdf", "status": "added"},
                        {"source_uri": "broken.pdf", "status": "failed", "reason": "bad pdf"},
                    ],
                }

            with patch("app.kernel_api.run_import_workflow", side_effect=_fake_import_workflow):
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
                self.assertIsNotNone(current.progress)
                assert current.progress is not None
                self.assertEqual(current.progress.batch_total, 3)
                self.assertEqual(current.progress.batch_completed, 2)
                self.assertEqual(current.progress.batch_failed, 1)
                self.assertEqual(current.progress.current_stage, "done")
                self.assertEqual(len(current.progress.recent_items), 2)
                self.assertEqual(current.progress.recent_items[1].state, "failed")

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
