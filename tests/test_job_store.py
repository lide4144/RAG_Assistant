from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.job_store import (
    ConfigSnapshotRecord,
    JobRecord,
    append_job_event,
    clear_job_store,
    get_config_snapshot,
    get_job,
    list_job_events,
    list_jobs,
    save_config_snapshot,
    upsert_job,
)
from app.kernel_api import TaskProgressInfo, TaskStatusResponse, _save_task


class JobStoreTests(unittest.TestCase):
    def test_job_store_round_trip_and_event_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "job_store.sqlite3"
            clear_job_store(db_path)
            upsert_job(
                JobRecord(
                    job_id="job-1",
                    kind="graph_build",
                    state="queued",
                    created_at="2026-04-01T00:00:00Z",
                    updated_at="2026-04-01T00:00:00Z",
                    progress_stage="queued",
                ),
                db_path=db_path,
            )
            append_job_event(
                job_id="job-1",
                event_type="state_changed",
                created_at="2026-04-01T00:00:01Z",
                payload={"state": "queued"},
                db_path=db_path,
            )
            append_job_event(
                job_id="job-1",
                event_type="task_progress",
                created_at="2026-04-01T00:00:02Z",
                payload={"stage": "extract", "processed": 1},
                db_path=db_path,
            )

            saved = get_job("job-1", db_path=db_path)
            events = list_job_events("job-1", db_path=db_path)
            tail = list_job_events("job-1", after_seq=1, db_path=db_path)

            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.job_id, "job-1")
            self.assertEqual(saved.kind, "graph_build")
            self.assertEqual(saved.progress_stage, "queued")
            self.assertEqual([event.seq for event in events], [1, 2])
            self.assertEqual(len(tail), 1)
            self.assertEqual(tail[0].seq, 2)
            self.assertEqual(tail[0].payload["stage"], "extract")

    def test_config_snapshot_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "job_store.sqlite3"
            clear_job_store(db_path)

            save_config_snapshot(
                ConfigSnapshotRecord(
                    config_version_id="cfg-1",
                    scope="llm",
                    created_at="2026-04-01T00:00:00Z",
                    payload={"answer": {"model": "gpt-5.4"}},
                    metadata={"source": "runtime"},
                ),
                db_path=db_path,
            )

            saved = get_config_snapshot("cfg-1", db_path=db_path)

            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.scope, "llm")
            self.assertEqual(saved.payload["answer"]["model"], "gpt-5.4")
            self.assertEqual(saved.metadata["source"], "runtime")

    def test_save_task_syncs_existing_task_into_job_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "job_store.sqlite3"
            clear_job_store(db_path)
            task = TaskStatusResponse(
                task_id="task-graph-1",
                task_kind="graph_build",
                state="running",
                created_at="2026-04-01T00:00:00Z",
                updated_at="2026-04-01T00:00:03Z",
                progress=TaskProgressInfo(stage="entity_extract", processed=2, total=5, elapsed_ms=3000, message="running"),
                result=None,
            )

            with patch("app.job_store.JOB_STORE_PATH", db_path):
                _save_task(task)
                saved = get_job("task-graph-1", db_path=db_path)
                events = list_job_events("task-graph-1", db_path=db_path)
                active = list_jobs(states={"running"}, db_path=db_path)

            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.job_id, "task-graph-1")
            self.assertEqual(saved.kind, "graph_build")
            self.assertEqual(saved.state, "running")
            self.assertEqual(saved.progress_stage, "entity_extract")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "task_snapshot")
            self.assertEqual(events[0].payload["taskId"], "task-graph-1")
            self.assertEqual(events[0].payload["state"], "running")
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0].job_id, "task-graph-1")
