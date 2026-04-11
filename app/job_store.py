from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.paths import DATA_DIR


JOB_STORE_PATH = DATA_DIR / "processed" / "job_store.sqlite3"
_JOB_STORE_LOCK = threading.Lock()


class JobRecord(BaseModel):
    job_id: str
    kind: str
    state: str
    created_at: str
    updated_at: str
    accepted: bool = True
    session_id: str | None = None
    trace_id: str | None = None
    run_id: str | None = None
    config_version_id: str | None = None
    progress_stage: str | None = None
    latest_output_text: str | None = None
    result_payload: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobEventRecord(BaseModel):
    job_id: str
    seq: int
    event_type: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ConfigSnapshotRecord(BaseModel):
    config_version_id: str
    scope: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or JOB_STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_job_store(db_path: str | Path | None = None) -> Path:
    path = Path(db_path or JOB_STORE_PATH)
    with _JOB_STORE_LOCK:
        conn = _connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    accepted INTEGER NOT NULL DEFAULT 1,
                    session_id TEXT,
                    trace_id TEXT,
                    run_id TEXT,
                    config_version_id TEXT,
                    progress_stage TEXT,
                    latest_output_text TEXT,
                    result_payload TEXT,
                    error_payload TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    job_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (job_id, seq)
                );

                CREATE TABLE IF NOT EXISTS config_snapshots (
                    config_version_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
    return path


def clear_job_store(db_path: str | Path | None = None) -> None:
    init_job_store(db_path)
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute("DELETE FROM job_events")
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM config_snapshots")
            conn.commit()
        finally:
            conn.close()


def upsert_job(record: JobRecord, db_path: str | Path | None = None) -> JobRecord:
    init_job_store(db_path)
    payload = record.model_copy(deep=True)
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, kind, state, created_at, updated_at, accepted, session_id, trace_id, run_id,
                    config_version_id, progress_stage, latest_output_text, result_payload, error_payload, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    kind=excluded.kind,
                    state=excluded.state,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    accepted=excluded.accepted,
                    session_id=excluded.session_id,
                    trace_id=excluded.trace_id,
                    run_id=excluded.run_id,
                    config_version_id=excluded.config_version_id,
                    progress_stage=excluded.progress_stage,
                    latest_output_text=excluded.latest_output_text,
                    result_payload=excluded.result_payload,
                    error_payload=excluded.error_payload,
                    metadata_json=excluded.metadata_json
                """,
                (
                    payload.job_id,
                    payload.kind,
                    payload.state,
                    payload.created_at,
                    payload.updated_at,
                    1 if payload.accepted else 0,
                    payload.session_id,
                    payload.trace_id,
                    payload.run_id,
                    payload.config_version_id,
                    payload.progress_stage,
                    payload.latest_output_text,
                    json.dumps(payload.result_payload or {}, ensure_ascii=False),
                    json.dumps(payload.error_payload or {}, ensure_ascii=False),
                    json.dumps(payload.metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return payload


def get_job(job_id: str, db_path: str | Path | None = None) -> JobRecord | None:
    init_job_store(db_path)
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return JobRecord(
        job_id=str(row["job_id"]),
        kind=str(row["kind"]),
        state=str(row["state"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        accepted=bool(row["accepted"]),
        session_id=row["session_id"],
        trace_id=row["trace_id"],
        run_id=row["run_id"],
        config_version_id=row["config_version_id"],
        progress_stage=row["progress_stage"],
        latest_output_text=row["latest_output_text"],
        result_payload=json.loads(row["result_payload"] or "{}"),
        error_payload=json.loads(row["error_payload"] or "{}"),
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def list_jobs(*, states: set[str] | None = None, limit: int = 100, db_path: str | Path | None = None) -> list[JobRecord]:
    init_job_store(db_path)
    safe_limit = max(1, min(500, int(limit)))
    query = "SELECT * FROM jobs"
    params: list[Any] = []
    if states:
        placeholders = ",".join("?" for _ in states)
        query += f" WHERE state IN ({placeholders})"
        params.extend(sorted(states))
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(safe_limit)
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(query, tuple(params)).fetchall()
        finally:
            conn.close()
    return [get_job(str(row["job_id"]), db_path=db_path) for row in rows if row is not None]  # type: ignore[list-item]


def append_job_event(
    *,
    job_id: str,
    event_type: str,
    created_at: str,
    payload: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> JobEventRecord:
    init_job_store(db_path)
    normalized_payload = dict(payload or {})
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM job_events WHERE job_id = ?", (job_id,)).fetchone()
            next_seq = int(row["seq"] or 0) + 1 if row is not None else 1
            conn.execute(
                "INSERT INTO job_events (job_id, seq, event_type, created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
                (job_id, next_seq, event_type, created_at, json.dumps(normalized_payload, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()
    return JobEventRecord(job_id=job_id, seq=next_seq, event_type=event_type, created_at=created_at, payload=normalized_payload)


def list_job_events(
    job_id: str,
    *,
    after_seq: int = 0,
    limit: int = 500,
    db_path: str | Path | None = None,
) -> list[JobEventRecord]:
    init_job_store(db_path)
    safe_limit = max(1, min(5000, int(limit)))
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT job_id, seq, event_type, created_at, payload_json
                FROM job_events
                WHERE job_id = ? AND seq > ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (job_id, max(0, int(after_seq)), safe_limit),
            ).fetchall()
        finally:
            conn.close()
    return [
        JobEventRecord(
            job_id=str(row["job_id"]),
            seq=int(row["seq"]),
            event_type=str(row["event_type"]),
            created_at=str(row["created_at"]),
            payload=json.loads(row["payload_json"] or "{}"),
        )
        for row in rows
    ]


def save_config_snapshot(record: ConfigSnapshotRecord, db_path: str | Path | None = None) -> ConfigSnapshotRecord:
    init_job_store(db_path)
    payload = record.model_copy(deep=True)
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO config_snapshots (config_version_id, scope, created_at, payload_json, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(config_version_id) DO UPDATE SET
                    scope=excluded.scope,
                    created_at=excluded.created_at,
                    payload_json=excluded.payload_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    payload.config_version_id,
                    payload.scope,
                    payload.created_at,
                    json.dumps(payload.payload or {}, ensure_ascii=False),
                    json.dumps(payload.metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return payload


def get_config_snapshot(config_version_id: str, db_path: str | Path | None = None) -> ConfigSnapshotRecord | None:
    init_job_store(db_path)
    with _JOB_STORE_LOCK:
        conn = _connect(db_path)
        try:
            row = conn.execute("SELECT * FROM config_snapshots WHERE config_version_id = ?", (config_version_id,)).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return ConfigSnapshotRecord(
        config_version_id=str(row["config_version_id"]),
        scope=str(row["scope"]),
        created_at=str(row["created_at"]),
        payload=json.loads(row["payload_json"] or "{}"),
        metadata=json.loads(row["metadata_json"] or "{}"),
    )
