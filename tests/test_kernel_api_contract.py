from __future__ import annotations

import json
import os
import threading
import unittest
from unittest.mock import patch
import time
import tempfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.kernel_api import (
    _JOB_CANCEL_EVENTS,
    _LLM_DEBUG_STORE,
    _LLM_DEBUG_STORE_LOCK,
    app,
    _TASK_CANCEL_EVENTS,
    _TASKS,
    _TASKS_LOCK,
    _build_qa_args,
    _build_marker_artifacts,
    _chunk_stream_fallback_answer,
    cancel_task,
    KernelChatRequest,
    KernelChatResponse,
    SourceItem,
    TaskProgressInfo,
    TaskStatusResponse,
    get_latest_import_result,
    get_llm_debug_trace,
    _build_sources_from_qa_report,
    _derive_runtime_tool_fallback,
    _build_runtime_tool_results,
    _planner_runtime_route_executor,
    get_task_status,
    _run_qa_once,
    _run_planner_shell_once,
    create_chat_job,
    cancel_job,
    download_llm_logs,
    list_llm_logs,
    get_job_events,
    get_job_llm_debug,
    get_job_status,
    get_runtime_overview,
    qa_stream,
    planner_qa,
    planner_qa_stream,
    PlannerShadowReviewRequest,
    save_planner_shadow_review,
    save_admin_llm_config,
    start_graph_build_task,
    _start_library_import_task,
    GraphBuildTaskStartRequest,
    AdminSaveLLMConfigRequest,
)
from app.job_store import JobRecord, clear_job_store, get_config_snapshot, get_job, list_job_events, upsert_job
from app.llm_client import emit_llm_debug_event
from app.pipeline_runtime_config import default_marker_llm, default_marker_tuning
from app.qa import _resolve_run_dir


class KernelApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        with _TASKS_LOCK:
            _TASKS.clear()
            _TASK_CANCEL_EVENTS.clear()
            _JOB_CANCEL_EVENTS.clear()
        with _LLM_DEBUG_STORE_LOCK:
            _LLM_DEBUG_STORE.clear()
        clear_job_store()
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

    def test_chunk_stream_fallback_answer_splits_long_text(self) -> None:
        long_answer = "这是一段用于验证流式拆分的回答。" * 8

        chunks = _chunk_stream_fallback_answer(long_answer, chunk_size=24)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual("".join(chunks), long_answer)

    def test_llm_debug_endpoint_returns_records_for_trace(self) -> None:
        with _LLM_DEBUG_STORE_LOCK:
            _LLM_DEBUG_STORE["trace-debug"] = {
                "trace_id": "trace-debug",
                "records": [
                    {
                        "event": "chat_completion_success",
                        "stage": "chat_completion",
                        "debug_stage": "answer",
                        "provider": "openai",
                        "model": "gpt-5.4",
                        "api_base": "https://api.example.test/v1",
                        "endpoint": "https://api.example.test/v1/chat/completions",
                        "transport": "litellm",
                        "route_id": "primary",
                        "system_prompt": "system text",
                        "user_prompt": "user text",
                        "request_payload": "{\"model\":\"gpt-5.4\"}",
                        "response_payload": "{\"content\":\"assistant text\"}",
                        "response_text": "assistant text",
                        "timestamp": "2026-03-31T00:00:00Z",
                    }
                ],
            }

        payload = get_llm_debug_trace("trace-debug").model_dump()

        self.assertEqual(payload["trace_id"], "trace-debug")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["debug_stage"], "answer")
        self.assertEqual(payload["records"][0]["endpoint"], "https://api.example.test/v1/chat/completions")
        self.assertEqual(payload["records"][0]["transport"], "litellm")
        self.assertEqual(payload["records"][0]["system_prompt"], "system text")
        self.assertEqual(payload["records"][0]["user_prompt"], "user text")
        self.assertEqual(payload["records"][0]["request_payload"], "{\"model\":\"gpt-5.4\"}")
        self.assertEqual(payload["records"][0]["response_payload"], "{\"content\":\"assistant text\"}")
        self.assertEqual(payload["records"][0]["response_text"], "assistant text")

    def test_llm_log_download_endpoint_returns_current_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "llm-api-20260408.log"
            log_path.write_text("line-1\nline-2\n", encoding="utf-8")
            fake_cfg = type(
                "LlmLogCfg",
                (),
                {
                    "enabled": True,
                    "max_body_chars": 50000,
                    "safe_root": str(Path(tmp)),
                    "log_path": str(log_path),
                    "source": {"enabled": "default", "max_body_chars": "default", "safe_root": "default", "log_path": "derived"},
                    "warnings": [],
                },
            )()
            with patch("app.kernel_api.resolve_effective_llm_log_config", return_value=fake_cfg):
                response = download_llm_logs()

        self.assertEqual(Path(response.path), log_path)
        self.assertEqual(response.filename, log_path.name)

    def test_llm_log_list_returns_recent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            older = base / "llm-api-20260408-101010-a.log"
            current = base / "llm-api-20260408-111111-b.log"
            older.write_text("older", encoding="utf-8")
            current.write_text("current", encoding="utf-8")
            fake_cfg = type(
                "LlmLogCfg",
                (),
                {
                    "enabled": True,
                    "max_body_chars": 50000,
                    "safe_root": str(base),
                    "log_path": str(current),
                    "source": {"enabled": "default", "max_body_chars": "default", "safe_root": "default", "log_path": "derived"},
                    "warnings": [],
                },
            )()
            with patch("app.kernel_api.resolve_effective_llm_log_config", return_value=fake_cfg):
                payload = list_llm_logs(limit=10)

        self.assertEqual(payload["safe_root"], str(base))
        self.assertEqual(payload["current_log_path"], str(current))
        self.assertEqual(payload["files"][0]["file_name"], current.name)
        self.assertTrue(payload["files"][0]["current"])
        self.assertIn("filename=", payload["files"][0]["download_url"])

    def test_runtime_overview_exposes_llm_logging(self) -> None:
        fake_cfg = type(
            "Cfg",
            (),
            {
                "answer_llm_provider": "openai",
                "answer_llm_api_base": "https://api.example.com/v1",
                "answer_llm_model": "gpt-4.1-mini",
                "embedding_provider": "siliconflow",
                "embedding_api_base": "https://api.example.com/v1",
                "embedding_model": "bge-m3",
                "rerank_provider": "siliconflow",
                "rerank_api_base": "https://api.example.com/v1",
                "rerank_model": "reranker",
                "rewrite_llm_provider": "openai",
                "rewrite_llm_api_base": "https://api.example.com/v1",
                "rewrite_llm_model": "rewrite-model",
                "graph_entity_llm_provider": "openai",
                "graph_entity_llm_base_url": "https://api.example.com/v1",
                "graph_entity_llm_model": "graph-model",
                "sufficiency_judge_llm_provider": "openai",
                "sufficiency_judge_llm_api_base": "https://api.example.com/v1",
                "sufficiency_judge_llm_model": "judge-model",
            },
        )()
        fake_stages = type(
            "Stages",
            (),
            {
                "stages": {
                    "answer": type("Stage", (), {"source": {"provider": "runtime", "api_base": "runtime", "model": "runtime"}})(),
                    "embedding": type("Stage", (), {"source": {"provider": "runtime", "api_base": "runtime", "model": "runtime"}})(),
                    "rerank": type("Stage", (), {"source": {"provider": "runtime", "api_base": "runtime", "model": "runtime"}})(),
                    "rewrite": type("Stage", (), {"source": {"provider": "runtime", "api_base": "runtime", "model": "runtime"}})(),
                    "graph_entity": type("Stage", (), {"source": {"provider": "runtime", "api_base": "runtime", "model": "runtime"}})(),
                    "sufficiency_judge": type("Stage", (), {"source": {"provider": "runtime", "api_base": "runtime", "model": "runtime"}})(),
                },
                "warnings": [],
            },
        )()
        fake_planner = type("Planner", (), {"provider": "openai", "api_base": "https://api.example.com/v1", "model": "planner-model", "timeout_ms": 6000, "api_key": "k"})()
        fake_marker_enabled = type("MarkerEnabled", (), {"value": True, "source": "runtime", "warnings": []})()
        fake_marker_tuning = type("MarkerTuningResolved", (), {"values": default_marker_tuning(), "source": {}, "warnings": []})()
        fake_marker_llm = type("MarkerLlmResolved", (), {"values": default_marker_llm(), "source": {}, "warnings": []})()
        fake_import = type("ImportResult", (), {"updated_at": None, "artifact_summary": {"counts": {}}, "degraded": False, "fallback_reason": None, "fallback_path": None, "confidence_note": None, "stage_updated_at": {}})()

        with (
            patch("app.kernel_api._active_job_summaries", return_value=[]),
            patch("app.kernel_api.load_runtime_llm_config", return_value=(None, None)),
            patch("app.kernel_api.load_planner_runtime_config", return_value=(None, None)),
            patch("app.kernel_api.load_and_validate_config", return_value=(fake_cfg, [])),
            patch("app.kernel_api.yaml.safe_load", return_value={}),
            patch("pathlib.Path.read_text", return_value="{}"),
            patch("app.kernel_api.resolve_effective_llm_stages", return_value=fake_stages),
            patch("app.kernel_api.resolve_effective_planner_runtime", return_value=(fake_planner, {"model": "runtime"}, [])),
            patch(
                "app.kernel_api.evaluate_planner_service_state",
                return_value={
                    "service_mode": "production",
                    "configured": True,
                    "llm_required": True,
                    "formal_chat_available": True,
                    "blocked": False,
                    "reason_code": None,
                    "reason_message": None,
                },
            ),
            patch("app.kernel_api.resolve_effective_marker_enabled", return_value=fake_marker_enabled),
            patch("app.kernel_api.resolve_effective_marker_tuning", return_value=fake_marker_tuning),
            patch("app.kernel_api.resolve_effective_marker_llm", return_value=fake_marker_llm),
            patch("app.kernel_api._marker_llm_runtime_entry", return_value={"configured": False, "status": "disabled", "summary_fields": []}),
            patch("app.kernel_api._load_latest_import_result", return_value=fake_import),
            patch("app.kernel_api._build_runtime_status", return_value=("READY", [])),
        ):
            payload = get_runtime_overview()

        self.assertIn("observability", payload)
        self.assertIn("llm_logging", payload["observability"])
        self.assertIn("enabled", payload["observability"]["llm_logging"])
        self.assertIn("max_body_chars", payload["observability"]["llm_logging"])
        self.assertIn("safe_root", payload["observability"]["llm_logging"])
        self.assertIn("download_url", payload["observability"]["llm_logging"])

    def test_jobs_endpoint_exposes_synced_task_and_events(self) -> None:
        task = TaskStatusResponse(
            task_id="task-sync-1",
            task_kind="graph_build",
            state="running",
            created_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:05Z",
            progress=TaskProgressInfo(stage="extract", processed=1, total=3, elapsed_ms=5000, message="running"),
        )
        with _TASKS_LOCK:
            _TASKS[task.task_id] = task
        from app.kernel_api import _sync_task_to_job_store

        _sync_task_to_job_store(task)

        detail_payload = get_job_status("task-sync-1").model_dump()
        events_payload = [item.model_dump() for item in get_job_events("task-sync-1")]

        self.assertEqual(detail_payload["job_id"], "task-sync-1")
        self.assertEqual(detail_payload["kind"], "graph_build")
        self.assertEqual(detail_payload["state"], "running")
        self.assertEqual(events_payload[0]["payload"]["taskId"], "task-sync-1")

    def test_admin_save_config_rejects_when_active_job_exists(self) -> None:
        task = TaskStatusResponse(
            task_id="task-active-1",
            task_kind="library_import",
            state="running",
            created_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:05Z",
            progress=TaskProgressInfo(stage="import", processed=1, total=4, elapsed_ms=5000, message="running"),
        )
        with _TASKS_LOCK:
            _TASKS[task.task_id] = task
        from app.kernel_api import _sync_task_to_job_store

        _sync_task_to_job_store(task)

        with self.assertRaises(HTTPException) as exc:
            save_admin_llm_config(
                AdminSaveLLMConfigRequest(
                    answer={"provider": "openai", "api_base": "https://api.openai.com/v1", "api_key": "sk-test", "model": "gpt-4.1-mini"},
                    embedding={"provider": "siliconflow", "api_base": "https://api.siliconflow.cn/v1", "api_key": "sk-test", "model": "bge-m3"},
                    rerank={"provider": "siliconflow", "api_base": "https://api.siliconflow.cn/v1", "api_key": "sk-test", "model": "Qwen/Qwen3-Reranker-8B"},
                    rewrite={"provider": "siliconflow", "api_base": "https://api.siliconflow.cn/v1", "api_key": "sk-test", "model": "rewrite-model"},
                    graph_entity={"provider": "siliconflow", "api_base": "https://api.siliconflow.cn/v1", "api_key": "sk-test", "model": "graph-model"},
                    sufficiency_judge={"provider": "siliconflow", "api_base": "https://api.siliconflow.cn/v1", "api_key": "sk-test", "model": "judge-model"},
                )
            )

        self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(exc.exception.detail["code"], "SETTINGS_LOCKED_BY_ACTIVE_JOB")
        self.assertEqual(exc.exception.detail["activeJobs"][0]["jobId"], "task-active-1")

    def test_create_chat_job_records_snapshot_and_events(self) -> None:
        payload = KernelChatRequest(sessionId="s-job", mode="local", query="q-job", history=[], traceId="trace-job")

        def _fake_run_qa_once(inner_payload: KernelChatRequest, on_stream_delta=None):
            if on_stream_delta is not None:
                on_stream_delta("hello ")
                on_stream_delta("world")
            return KernelChatResponse(traceId=inner_payload.traceId or "trace-job", answer="hello world", sources=[], runId="run-job-1")

        with patch("app.kernel_api._run_qa_once", side_effect=_fake_run_qa_once):
            created = create_chat_job(payload).model_dump()

            job_id = created["job"]["job_id"]
            config_version_id = created["job"]["config_version_id"]
            self.assertTrue(job_id.startswith("job_chat_"))
            self.assertTrue(config_version_id.startswith("cfg_"))

            current = None
            for _ in range(50):
                current = get_job_status(job_id).model_dump()
                if current["state"] == "succeeded":
                    break
                time.sleep(0.02)

        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current["state"], "succeeded")
        self.assertEqual(current["run_id"], "run-job-1")
        self.assertEqual(current["latest_output_text"], "hello world")

        snapshot = get_config_snapshot(config_version_id)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.scope, "chat_answer")
        self.assertEqual(snapshot.payload["request"]["query"], "q-job")

        events = [item.model_dump() for item in get_job_events(job_id)]
        self.assertGreaterEqual(len(events), 4)
        self.assertEqual(events[0]["event_type"], "state_changed")
        self.assertEqual(events[1]["event_type"], "state_changed")
        self.assertEqual(events[2]["event_type"], "message")
        self.assertEqual(events[-1]["event_type"], "messageEnd")

    def test_create_chat_job_records_llm_stage_events(self) -> None:
        payload = KernelChatRequest(sessionId="s-job-llm", mode="local", query="q-job-llm", history=[], traceId="trace-job-llm")

        def _fake_run_qa_once(inner_payload: KernelChatRequest, on_stream_delta=None):
            emit_llm_debug_event(
                {
                    "trace_id": inner_payload.traceId,
                    "event": "request_success",
                    "debug_stage": "rewrite",
                    "provider": "openai",
                    "model": "rewrite-model",
                    "elapsed_ms": 12,
                }
            )
            if on_stream_delta is not None:
                on_stream_delta("answer")
            return KernelChatResponse(traceId=inner_payload.traceId or "trace-job-llm", answer="answer", sources=[], runId="run-job-llm-1")

        with patch("app.kernel_api._run_qa_once", side_effect=_fake_run_qa_once):
            created = create_chat_job(payload).model_dump()
            job_id = created["job"]["job_id"]
            current = None
            for _ in range(50):
                current = get_job_status(job_id).model_dump()
                if current["state"] == "succeeded":
                    break
                time.sleep(0.02)

        self.assertIsNotNone(current)
        assert current is not None
        events = [item.model_dump() for item in get_job_events(job_id)]
        llm_stage = next(item for item in events if item["event_type"] == "llm_stage")
        self.assertEqual(llm_stage["payload"]["type"], "llmStage")
        self.assertEqual(llm_stage["payload"]["stage"], "rewrite")
        self.assertEqual(llm_stage["payload"]["model"], "rewrite-model")

    def test_job_llm_debug_resolves_via_job_trace(self) -> None:
        task = TaskStatusResponse(
            task_id="task-debug-job",
            task_kind="graph_build",
            state="running",
            created_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:05Z",
            progress=TaskProgressInfo(stage="extract", processed=1, total=3, elapsed_ms=5000, message="running"),
        )
        with _TASKS_LOCK:
            _TASKS[task.task_id] = task
        from app.kernel_api import _sync_task_to_job_store

        _sync_task_to_job_store(task)
        from app.job_store import upsert_job, get_job

        saved = get_job("task-debug-job")
        assert saved is not None
        upsert_job(saved.model_copy(update={"trace_id": "trace-debug-job"}))
        with _LLM_DEBUG_STORE_LOCK:
            _LLM_DEBUG_STORE["trace-debug-job"] = {
                "trace_id": "trace-debug-job",
                "records": [{"event": "chat_completion_success", "timestamp": "2026-04-01T00:00:00Z"}],
            }

        payload = get_job_llm_debug("task-debug-job").model_dump()

        self.assertEqual(payload["trace_id"], "trace-debug-job")
        self.assertEqual(payload["count"], 1)

    def test_cancel_chat_job_marks_job_cancelled(self) -> None:
        payload = KernelChatRequest(sessionId="s-cancel", mode="local", query="q-cancel", history=[], traceId="trace-cancel")
        first_delta_sent = threading.Event()
        continue_after_cancel = threading.Event()

        def _fake_run_qa_once(inner_payload: KernelChatRequest, on_stream_delta=None):
            if on_stream_delta is not None:
                on_stream_delta("hello ")
                first_delta_sent.set()
                continue_after_cancel.wait(timeout=1.0)
                on_stream_delta("world")
            return KernelChatResponse(traceId=inner_payload.traceId or "trace-cancel", answer="hello world", sources=[], runId="run-cancel-1")

        with patch("app.kernel_api._run_qa_once", side_effect=_fake_run_qa_once):
            created = create_chat_job(payload).model_dump()
            job_id = created["job"]["job_id"]

            self.assertTrue(first_delta_sent.wait(timeout=1.0))
            cancelled = cancel_job(job_id).model_dump()
            continue_after_cancel.set()

            current = None
            for _ in range(50):
                current = get_job_status(job_id).model_dump()
                if current["state"] == "cancelled":
                    break
                time.sleep(0.02)

        self.assertEqual(cancelled["job_id"], job_id)
        self.assertEqual(cancelled["kind"], "chat_answer")
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current["state"], "cancelled")
        self.assertEqual(current["progress_stage"], "cancelled")
        self.assertEqual(current["latest_output_text"], "hello ")

        events = [item.model_dump() for item in get_job_events(job_id)]
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[-1]["event_type"], "state_changed")
        self.assertEqual(events[-1]["payload"]["state"], "cancelled")

    def test_startup_reconciles_unfinished_jobs_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "job_store.sqlite3"
            clear_job_store(db_path)
            upsert_job(
                JobRecord(
                    job_id="job-restart-1",
                    kind="planner_chat",
                    state="running",
                    created_at="2026-04-07T01:00:00Z",
                    updated_at="2026-04-07T01:00:01Z",
                    progress_stage="running",
                    metadata={"mode": "local"},
                ),
                db_path=db_path,
            )

            with patch("app.job_store.JOB_STORE_PATH", db_path):
                with TestClient(app):
                    pass

            saved = get_job("job-restart-1", db_path=db_path)
            events = list_job_events("job-restart-1", db_path=db_path)

            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.state, "cancelled")
            self.assertEqual(saved.progress_stage, "cancelled")
            self.assertEqual(saved.error_payload.get("code"), "JOB_INTERRUPTED_BY_RESTART")
            self.assertTrue(saved.metadata.get("recovered_after_restart"))
            self.assertTrue(
                any(
                    event.event_type == "state_changed"
                    and event.payload.get("state") == "cancelled"
                    and event.payload.get("reason") == "process_restart"
                    for event in events
                )
            )

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
