from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.fs_utils import atomic_text_writer
from app.paths import DATA_DIR


DEFAULT_PROCESSED_DIR = DATA_DIR / "processed"
DEFAULT_TOPICS_PATH = DATA_DIR / "library_topics.json"
DEFAULT_RAW_IMPORT_DIR = DATA_DIR / "raw" / "imported"
_STORE_LOCK = threading.Lock()
_FINGERPRINT_SCAN_CACHE: dict[str, dict[str, str]] = {}
_UNSET = object()


def paper_store_path(processed_dir: str | Path = DEFAULT_PROCESSED_DIR) -> Path:
    return Path(processed_dir) / "paper_store.sqlite3"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or paper_store_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload or {}, ensure_ascii=False)


def _json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_temp_path(raw: str) -> bool:
    normalized = str(raw or "").strip()
    if not normalized:
        return True
    return normalized.startswith("/tmp/tmp") or "/_api_upload_staging/" in normalized or "/_ui_upload_staging/" in normalized


def _sha1_file(path: Path) -> str:
    hasher = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def init_paper_store(db_path: str | Path | None = None) -> Path:
    path = Path(db_path or paper_store_path())
    with _STORE_LOCK:
        conn = _connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT '',
                    storage_path TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'pdf',
                    source_uri TEXT NOT NULL DEFAULT '',
                    parser_engine TEXT NOT NULL DEFAULT 'legacy',
                    title_source TEXT NOT NULL DEFAULT '',
                    title_confidence REAL NOT NULL DEFAULT 0,
                    imported_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'imported',
                    fingerprint TEXT NOT NULL DEFAULT '',
                    ingest_metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    error_message TEXT NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_fingerprint ON papers(fingerprint) WHERE fingerprint <> '';
                CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_source_uri ON papers(source_uri) WHERE source_uri <> '';
                CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
                CREATE INDEX IF NOT EXISTS idx_papers_imported_at ON papers(imported_at);

                CREATE TABLE IF NOT EXISTS paper_stage_status (
                    paper_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (paper_id, stage),
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS paper_topics (
                    paper_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (paper_id, topic),
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_paper_topics_topic ON paper_topics(topic);

                CREATE TABLE IF NOT EXISTS paper_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL,
                    page_start INTEGER NOT NULL DEFAULT 1,
                    section TEXT NOT NULL DEFAULT '',
                    source_file TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks(paper_id);

                CREATE TABLE IF NOT EXISTS paper_artifacts (
                    paper_id TEXT NOT NULL,
                    artifact_key TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    path TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (paper_id, artifact_key),
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_paper_artifacts_type ON paper_artifacts(artifact_type);

                CREATE TABLE IF NOT EXISTS vector_backend_state (
                    backend_name TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
    return path


def _derive_status(*, explicit_status: str, paper_id: str, chunk_ids: set[str], clean_ids: set[str], indexes_ready: bool, deleted_at: str = "") -> str:
    status = str(explicit_status or "").strip().lower()
    if deleted_at:
        return "deleted"
    if status and status not in {"active", "unknown"}:
        return status
    if paper_id in clean_ids and indexes_ready:
        return "ready"
    if paper_id in clean_ids:
        return "cleaned"
    if paper_id in chunk_ids:
        return "parsed"
    return "imported"


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _resolve_by_fingerprint(raw_import_dir: Path, fingerprint: str) -> str:
    if not fingerprint or not raw_import_dir.exists():
        return ""
    cache_key = str(raw_import_dir.resolve())
    mapping = _FINGERPRINT_SCAN_CACHE.get(cache_key)
    if mapping is None:
        mapping = {}
        for candidate in raw_import_dir.iterdir():
            if not candidate.is_file():
                continue
            try:
                mapping[_sha1_file(candidate)] = str(candidate)
            except Exception:
                continue
        _FINGERPRINT_SCAN_CACHE[cache_key] = mapping
    return str(mapping.get(fingerprint, "") or "")


def _repair_storage_path(
    row: dict[str, Any],
    *,
    raw_import_dir: Path,
    stable_source_path_by_fingerprint: dict[str, str] | None = None,
) -> str:
    source_type = str(row.get("source_type", "pdf")).strip() or "pdf"
    path_value = str(row.get("path", "")).strip()
    source_uri = str(row.get("source_uri", path_value)).strip()
    fingerprint = str(row.get("fingerprint", "")).strip()
    explicit_map = stable_source_path_by_fingerprint or {}

    if source_type != "pdf":
        return source_uri or path_value

    if fingerprint and explicit_map.get(fingerprint):
        return str(explicit_map[fingerprint])

    if path_value and not _is_temp_path(path_value) and Path(path_value).exists():
        return path_value

    if path_value:
        candidate = raw_import_dir / Path(path_value).name
        if candidate.exists():
            return str(candidate)

    repaired = _resolve_by_fingerprint(raw_import_dir, fingerprint)
    if repaired:
        return repaired
    return path_value


def upsert_paper(row: dict[str, Any], *, db_path: str | Path | None = None) -> None:
    init_paper_store(db_path)
    now = _now_iso()
    payload = dict(row)
    paper_id = str(payload.get("paper_id", "")).strip()
    if not paper_id:
        return
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO papers (
                    paper_id, title, path, storage_path, source_type, source_uri, parser_engine, title_source,
                    title_confidence, imported_at, status, fingerprint, ingest_metadata_json, created_at, updated_at,
                    deleted_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    title=excluded.title,
                    path=excluded.path,
                    storage_path=excluded.storage_path,
                    source_type=excluded.source_type,
                    source_uri=excluded.source_uri,
                    parser_engine=excluded.parser_engine,
                    title_source=excluded.title_source,
                    title_confidence=excluded.title_confidence,
                    imported_at=excluded.imported_at,
                    status=excluded.status,
                    fingerprint=excluded.fingerprint,
                    ingest_metadata_json=excluded.ingest_metadata_json,
                    updated_at=excluded.updated_at,
                    deleted_at=excluded.deleted_at,
                    error_message=excluded.error_message
                """,
                (
                    paper_id,
                    str(payload.get("title", "")).strip(),
                    str(payload.get("path", "")).strip(),
                    str(payload.get("storage_path", payload.get("path", ""))).strip(),
                    str(payload.get("source_type", "pdf")).strip() or "pdf",
                    str(payload.get("source_uri", payload.get("path", ""))).strip(),
                    str(payload.get("parser_engine", "legacy")).strip() or "legacy",
                    str(payload.get("title_source", "")).strip(),
                    float(payload.get("title_confidence", 0.0) or 0.0),
                    str(payload.get("imported_at", "")).strip(),
                    str(payload.get("status", "imported")).strip() or "imported",
                    str(payload.get("fingerprint", "")).strip(),
                    _json_dumps(payload.get("ingest_metadata")),
                    str(payload.get("created_at", "")).strip() or now,
                    str(payload.get("updated_at", "")).strip() or now,
                    str(payload.get("deleted_at", "")).strip() or None,
                    str(payload.get("error_message", "")).strip(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def update_paper(
    paper_id: str,
    *,
    status: str | object = _UNSET,
    error_message: str | object = _UNSET,
    deleted_at: str | None | object = _UNSET,
    path: str | object = _UNSET,
    storage_path: str | object = _UNSET,
    title: str | object = _UNSET,
    source_uri: str | object = _UNSET,
    updated_at: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    if not pid:
        return
    assignments: list[str] = []
    values: list[Any] = []
    if status is not _UNSET:
        assignments.append("status = ?")
        values.append(str(status).strip() or "imported")
    if error_message is not _UNSET:
        assignments.append("error_message = ?")
        values.append(str(error_message or "").strip())
    if deleted_at is not _UNSET:
        assignments.append("deleted_at = ?")
        values.append(str(deleted_at).strip() or None)
    if path is not _UNSET:
        assignments.append("path = ?")
        values.append(str(path).strip())
    if storage_path is not _UNSET:
        assignments.append("storage_path = ?")
        values.append(str(storage_path).strip())
    if title is not _UNSET:
        assignments.append("title = ?")
        values.append(str(title).strip())
    if source_uri is not _UNSET:
        assignments.append("source_uri = ?")
        values.append(str(source_uri).strip())
    assignments.append("updated_at = ?")
    values.append(updated_at or _now_iso())
    values.append(pid)
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(f"UPDATE papers SET {', '.join(assignments)} WHERE paper_id = ?", tuple(values))
            conn.commit()
        finally:
            conn.close()


def upsert_stage_status(
    *,
    paper_id: str,
    stage: str,
    state: str,
    updated_at: str | None = None,
    error_message: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    stage_name = str(stage).strip()
    if not pid or not stage_name:
        return
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO paper_stage_status (paper_id, stage, state, updated_at, error_message, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id, stage) DO UPDATE SET
                    state=excluded.state,
                    updated_at=excluded.updated_at,
                    error_message=excluded.error_message,
                    metadata_json=excluded.metadata_json
                """,
                (pid, stage_name, str(state).strip() or "unknown", updated_at or _now_iso(), str(error_message or "").strip(), _json_dumps(metadata)),
            )
            conn.commit()
        finally:
            conn.close()


def replace_topics(topics: dict[str, list[str]], *, db_path: str | Path | None = None) -> None:
    init_paper_store(db_path)
    now = _now_iso()
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute("DELETE FROM paper_topics")
            for topic, paper_ids in topics.items():
                name = str(topic).strip()
                if not name:
                    continue
                for paper_id in paper_ids:
                    pid = str(paper_id).strip()
                    if not pid:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO paper_topics (paper_id, topic, created_at) VALUES (?, ?, ?)",
                        (pid, name, now),
                    )
            conn.commit()
        finally:
            conn.close()


def assign_topic(topic: str, paper_id: str, *, db_path: str | Path | None = None) -> None:
    name = str(topic).strip()
    pid = str(paper_id).strip()
    if not name or not pid:
        return
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO paper_topics (paper_id, topic, created_at) VALUES (?, ?, ?)",
                (pid, name, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()


def load_topics(*, db_path: str | Path | None = None) -> dict[str, list[str]]:
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute("SELECT topic, paper_id FROM paper_topics ORDER BY topic, paper_id").fetchall()
        finally:
            conn.close()
    topics: dict[str, list[str]] = {}
    for row in rows:
        topic = str(row["topic"]).strip()
        paper_id = str(row["paper_id"]).strip()
        if not topic or not paper_id:
            continue
        topics.setdefault(topic, []).append(paper_id)
    return topics


def replace_chunks(chunks: list[dict[str, Any]], *, db_path: str | Path | None = None) -> None:
    init_paper_store(db_path)
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for row in chunks:
        paper_id = str(row.get("paper_id", "")).strip()
        if not paper_id:
            continue
        by_paper.setdefault(paper_id, []).append(row)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            for paper_id, rows in by_paper.items():
                conn.execute("DELETE FROM paper_chunks WHERE paper_id = ?", (paper_id,))
                for row in rows:
                    chunk_id = str(row.get("chunk_id", "")).strip()
                    if not chunk_id:
                        continue
                    page_start = row.get("page_start", 1)
                    try:
                        page_start = int(page_start)
                    except Exception:
                        page_start = 1
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO paper_chunks (chunk_id, paper_id, page_start, section, source_file, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk_id,
                            paper_id,
                            max(1, int(page_start)),
                            str(row.get("section", "")).strip(),
                            str(row.get("source_file", "")).strip(),
                            _json_dumps(
                                {
                                    "content_type": row.get("content_type"),
                                    "block_type": row.get("block_type"),
                                    "structure_provenance": row.get("structure_provenance"),
                                }
                            ),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()


def upsert_artifact(
    *,
    paper_id: str,
    artifact_key: str,
    artifact_type: str,
    status: str,
    path: str = "",
    version: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    key = str(artifact_key).strip()
    if not pid or not key:
        return
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO paper_artifacts (paper_id, artifact_key, artifact_type, status, path, version, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id, artifact_key) DO UPDATE SET
                    artifact_type=excluded.artifact_type,
                    status=excluded.status,
                    path=excluded.path,
                    version=excluded.version,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (pid, key, str(artifact_type).strip() or key, str(status).strip() or "unknown", str(path).strip(), str(version).strip(), _now_iso(), _json_dumps(metadata)),
            )
            conn.commit()
        finally:
            conn.close()


def update_artifacts_for_paper(
    paper_id: str,
    *,
    status: str,
    artifact_keys: list[str] | None = None,
    metadata_patch: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    if not pid:
        return
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            if artifact_keys:
                rows = conn.execute(
                    f"SELECT artifact_key, metadata_json FROM paper_artifacts WHERE paper_id = ? AND artifact_key IN ({','.join('?' for _ in artifact_keys)})",
                    (pid, *artifact_keys),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT artifact_key, metadata_json FROM paper_artifacts WHERE paper_id = ?",
                    (pid,),
                ).fetchall()
            for row in rows:
                metadata = _json_loads(row["metadata_json"])
                if metadata_patch:
                    metadata.update(metadata_patch)
                conn.execute(
                    """
                    UPDATE paper_artifacts
                    SET status = ?, updated_at = ?, metadata_json = ?
                    WHERE paper_id = ? AND artifact_key = ?
                    """,
                    (str(status).strip() or "unknown", _now_iso(), _json_dumps(metadata), pid, str(row["artifact_key"]).strip()),
                )
            conn.commit()
        finally:
            conn.close()


def clear_chunks_for_paper(paper_id: str, *, db_path: str | Path | None = None) -> None:
    pid = str(paper_id).strip()
    if not pid:
        return
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute("DELETE FROM paper_chunks WHERE paper_id = ?", (pid,))
            conn.commit()
        finally:
            conn.close()


def mark_paper_failed(
    paper_id: str,
    *,
    stage: str,
    reason: str,
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    if not pid:
        return
    message = str(reason or "unknown_failure").strip() or "unknown_failure"
    update_paper(pid, status="failed", error_message=message, db_path=db_path)
    upsert_stage_status(paper_id=pid, stage=stage, state="failed", error_message=message, db_path=db_path)
    update_artifacts_for_paper(
        pid,
        status="stale",
        metadata_patch={"failure_stage": stage, "failure_reason": message},
        db_path=db_path,
    )


def mark_paper_rebuild_pending(
    paper_id: str,
    *,
    reason: str = "",
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    if not pid:
        return
    update_paper(pid, status="rebuild_pending", error_message=str(reason or "").strip(), deleted_at=None, db_path=db_path)
    upsert_stage_status(
        paper_id=pid,
        stage="index",
        state="queued",
        error_message="",
        metadata={"reason": str(reason or "rebuild_requested").strip() or "rebuild_requested"},
        db_path=db_path,
    )
    upsert_stage_status(
        paper_id=pid,
        stage="graph_build",
        state="queued",
        error_message="",
        metadata={"reason": str(reason or "rebuild_requested").strip() or "rebuild_requested"},
        db_path=db_path,
    )
    update_artifacts_for_paper(
        pid,
        status="stale",
        metadata_patch={"rebuild_pending": True, "reason": str(reason or "rebuild_requested").strip() or "rebuild_requested"},
        db_path=db_path,
    )


def mark_paper_deleted(
    paper_id: str,
    *,
    reason: str = "",
    db_path: str | Path | None = None,
) -> None:
    pid = str(paper_id).strip()
    if not pid:
        return
    deleted_at = _now_iso()
    update_paper(
        pid,
        status="deleted",
        error_message=str(reason or "").strip(),
        deleted_at=deleted_at,
        db_path=db_path,
    )
    for stage in ("dedup", "import", "parse", "clean", "index", "graph_build"):
        upsert_stage_status(
            paper_id=pid,
            stage=stage,
            state="deleted",
            error_message=str(reason or "").strip(),
            metadata={"deleted_at": deleted_at},
            db_path=db_path,
        )
    clear_chunks_for_paper(pid, db_path=db_path)
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute("DELETE FROM paper_topics WHERE paper_id = ?", (pid,))
            conn.commit()
        finally:
            conn.close()
    update_artifacts_for_paper(
        pid,
        status="deleted",
        metadata_patch={"deleted_at": deleted_at, "reason": str(reason or "").strip()},
        db_path=db_path,
    )


def set_vector_backend_state(
    *,
    backend_name: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    name = str(backend_name).strip()
    if not name:
        return
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO vector_backend_state (backend_name, status, updated_at, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(backend_name) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (name, str(status).strip() or "unknown", _now_iso(), _json_dumps(metadata)),
            )
            conn.commit()
        finally:
            conn.close()


def get_vector_backend_state(*, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_paper_store(db_path)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            row = conn.execute("SELECT * FROM vector_backend_state ORDER BY updated_at DESC LIMIT 1").fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return {
        "backend_name": str(row["backend_name"]).strip(),
        "status": str(row["status"]).strip(),
        "updated_at": str(row["updated_at"]).strip(),
        "metadata": _json_loads(row["metadata_json"]),
    }


def list_papers(
    *,
    db_path: str | Path | None = None,
    limit: int = 200,
    status: str | None = None,
    topic: str | None = None,
    query: str | None = None,
    include_stage_statuses: bool = False,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    init_paper_store(db_path)
    safe_limit = max(1, min(1000, int(limit)))
    clauses = ["1=1"]
    params: list[Any] = []
    if not include_deleted:
        clauses.append("COALESCE(p.deleted_at, '') = ''")
        clauses.append("p.status <> 'deleted'")
    if status:
        clauses.append("p.status = ?")
        params.append(str(status).strip())
    if topic:
        clauses.append("EXISTS (SELECT 1 FROM paper_topics pt WHERE pt.paper_id = p.paper_id AND pt.topic = ?)")
        params.append(str(topic).strip())
    if query:
        needle = f"%{str(query).strip().lower()}%"
        clauses.append("(lower(p.title) LIKE ? OR lower(p.source_uri) LIKE ? OR lower(p.storage_path) LIKE ?)")
        params.extend([needle, needle, needle])
    sql = f"""
        SELECT p.*,
               COALESCE((SELECT group_concat(topic, ',') FROM paper_topics pt WHERE pt.paper_id = p.paper_id), '') AS topics_csv
        FROM papers p
        WHERE {' AND '.join(clauses)}
        ORDER BY p.imported_at DESC, p.updated_at DESC, p.title ASC
        LIMIT ?
    """
    params.append(safe_limit)
    with _STORE_LOCK:
        conn = _connect(db_path)
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            stage_rows = conn.execute(
                "SELECT paper_id, stage, state, updated_at, error_message, metadata_json FROM paper_stage_status ORDER BY updated_at DESC"
            ).fetchall() if include_stage_statuses else []
        finally:
            conn.close()
    stages_by_paper: dict[str, list[dict[str, Any]]] = {}
    for row in stage_rows:
        stages_by_paper.setdefault(str(row["paper_id"]).strip(), []).append(
            {
                "stage": str(row["stage"]).strip(),
                "state": str(row["state"]).strip(),
                "updated_at": str(row["updated_at"]).strip(),
                "error_message": str(row["error_message"]).strip(),
                "metadata": _json_loads(row["metadata_json"]),
            }
        )
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            "paper_id": str(row["paper_id"]).strip(),
            "title": str(row["title"]).strip(),
            "path": str(row["path"]).strip(),
            "storage_path": str(row["storage_path"]).strip(),
            "source_type": str(row["source_type"]).strip() or "pdf",
            "source_uri": str(row["source_uri"]).strip(),
            "parser_engine": str(row["parser_engine"]).strip() or "legacy",
            "title_source": str(row["title_source"]).strip(),
            "title_confidence": float(row["title_confidence"] or 0.0),
            "imported_at": str(row["imported_at"]).strip(),
            "status": str(row["status"]).strip() or "imported",
            "fingerprint": str(row["fingerprint"]).strip(),
            "ingest_metadata": _json_loads(row["ingest_metadata_json"]),
            "created_at": str(row["created_at"]).strip(),
            "updated_at": str(row["updated_at"]).strip(),
            "deleted_at": str(row["deleted_at"] or "").strip(),
            "error_message": str(row["error_message"]).strip(),
            "topics": [item for item in str(row["topics_csv"]).split(",") if item],
        }
        if include_stage_statuses:
            payload["stage_statuses"] = stages_by_paper.get(payload["paper_id"], [])
        out.append(payload)
    return out


def get_paper(
    paper_id: str,
    *,
    db_path: str | Path | None = None,
    include_deleted: bool = True,
) -> dict[str, Any] | None:
    rows = list_papers(db_path=db_path, limit=1_000, include_stage_statuses=True, include_deleted=include_deleted)
    target = str(paper_id).strip()
    return next((row for row in rows if row.get("paper_id") == target), None)


def export_store_to_compat(
    *,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    topics_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> None:
    processed = Path(processed_dir)
    store_path = Path(db_path or paper_store_path(processed))
    papers = list_papers(db_path=store_path, limit=10_000)
    papers_path = processed / "papers.json"
    papers_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(papers_path) as handle:
        handle.write(json.dumps(papers, ensure_ascii=False, indent=2))
    topic_target = Path(topics_path or DEFAULT_TOPICS_PATH)
    topic_target.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(topic_target) as handle:
        handle.write(json.dumps(load_topics(db_path=store_path), ensure_ascii=False, indent=2))


def sync_store_from_exports(
    *,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    topics_path: str | Path | None = None,
    stable_source_path_by_fingerprint: dict[str, str] | None = None,
    db_path: str | Path | None = None,
) -> Path:
    processed = Path(processed_dir)
    papers_path = processed / "papers.json"
    chunks_path = processed / "chunks.jsonl"
    clean_chunks_path = processed / "chunks_clean.jsonl"
    summary_path = processed / "paper_summary.json"
    structure_path = processed / "structure_index.json"
    indexes_dir = processed.parent / "indexes"
    store_path = Path(db_path or paper_store_path(processed))
    raw_import_dir = DEFAULT_RAW_IMPORT_DIR if processed == DEFAULT_PROCESSED_DIR else processed.parent / "raw" / "imported"

    init_paper_store(store_path)
    papers = _load_json_rows(papers_path)
    chunks = _load_jsonl_rows(chunks_path)
    clean_chunks = _load_jsonl_rows(clean_chunks_path)
    summaries = {str(row.get("paper_id", "")).strip(): row for row in _load_json_rows(summary_path) if str(row.get("paper_id", "")).strip()}
    structure_payload = _load_json_rows(structure_path) if structure_path.suffix == ".jsonl" else []
    structure_map: dict[str, dict[str, Any]] = {}
    if not structure_payload and structure_path.exists():
        try:
            payload = json.loads(structure_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            for row in payload.get("papers", []) or []:
                if not isinstance(row, dict):
                    continue
                paper_id = str(row.get("paper_id", "")).strip()
                if paper_id:
                    structure_map[paper_id] = row

    chunk_ids = {str(row.get("paper_id", "")).strip() for row in chunks if str(row.get("paper_id", "")).strip()}
    clean_ids = {str(row.get("paper_id", "")).strip() for row in clean_chunks if str(row.get("paper_id", "")).strip()}
    indexes_ready = any((indexes_dir / name).exists() for name in ("bm25_index.json", "vec_index.json", "vec_index_embed.json"))

    for row in papers:
        paper_id = str(row.get("paper_id", "")).strip()
        if not paper_id:
            continue
        repaired_path = _repair_storage_path(
            row,
            raw_import_dir=raw_import_dir,
            stable_source_path_by_fingerprint=stable_source_path_by_fingerprint,
        )
        deleted_at = str(row.get("deleted_at", "")).strip()
        paper_status = _derive_status(
            explicit_status=str(row.get("status", "")).strip(),
            paper_id=paper_id,
            chunk_ids=chunk_ids,
            clean_ids=clean_ids,
            indexes_ready=indexes_ready,
            deleted_at=deleted_at,
        )
        upsert_paper(
            {
                **row,
                "path": repaired_path or str(row.get("path", "")).strip(),
                "storage_path": repaired_path or str(row.get("path", "")).strip(),
                "status": paper_status,
                "updated_at": _now_iso(),
                "error_message": str(row.get("error_message", "")).strip(),
            },
            db_path=store_path,
        )

        upsert_stage_status(paper_id=paper_id, stage="dedup", state="succeeded", db_path=store_path)
        upsert_stage_status(paper_id=paper_id, stage="import", state="succeeded", db_path=store_path)
        upsert_stage_status(paper_id=paper_id, stage="parse", state="succeeded" if paper_id in chunk_ids else "queued", db_path=store_path)
        upsert_stage_status(paper_id=paper_id, stage="clean", state="succeeded" if paper_id in clean_ids else "queued", db_path=store_path)
        upsert_stage_status(
            paper_id=paper_id,
            stage="index",
            state="succeeded" if indexes_ready and paper_id in clean_ids else ("queued" if paper_id in clean_ids else "not_started"),
            db_path=store_path,
        )
        graph_state = "succeeded" if (processed / "graph.json").exists() and paper_id in clean_ids else "not_started"
        upsert_stage_status(paper_id=paper_id, stage="graph_build", state=graph_state, db_path=store_path)

        upsert_artifact(
            paper_id=paper_id,
            artifact_key="chunks",
            artifact_type="chunks",
            status="ready" if paper_id in chunk_ids else "missing",
            path=str(chunks_path),
            db_path=store_path,
        )
        upsert_artifact(
            paper_id=paper_id,
            artifact_key="chunks_clean",
            artifact_type="chunks_clean",
            status="ready" if paper_id in clean_ids else "missing",
            path=str(clean_chunks_path),
            db_path=store_path,
        )
        summary_row = summaries.get(paper_id)
        upsert_artifact(
            paper_id=paper_id,
            artifact_key="paper_summary",
            artifact_type="paper_summary",
            status="ready" if summary_row else "missing",
            path=str(summary_path),
            version=str((summary_row or {}).get("summary_version", "")).strip(),
            metadata={"chunk_snapshot_hash": (summary_row or {}).get("chunk_snapshot_hash")},
            db_path=store_path,
        )
        structure_row = structure_map.get(paper_id)
        upsert_artifact(
            paper_id=paper_id,
            artifact_key="structure_index",
            artifact_type="structure_index",
            status=str((structure_row or {}).get("structure_parse_status", "missing")).strip() or "missing",
            path=str(structure_path),
            metadata={"structure_parse_reason": (structure_row or {}).get("structure_parse_reason")},
            db_path=store_path,
        )

    replace_chunks(chunks, db_path=store_path)

    topic_file = Path(topics_path or DEFAULT_TOPICS_PATH)
    if topic_file.exists():
        try:
            payload = json.loads(topic_file.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            normalized = {
                str(topic).strip(): [str(pid).strip() for pid in values if str(pid).strip()]
                for topic, values in payload.items()
                if str(topic).strip() and isinstance(values, list)
            }
            replace_topics(normalized, db_path=store_path)

    export_store_to_compat(processed_dir=processed, topics_path=topic_file, db_path=store_path)
    return store_path


def ensure_store_current(
    *,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    topics_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> Path:
    processed = Path(processed_dir)
    store_path = Path(db_path or paper_store_path(processed))
    papers_path = processed / "papers.json"
    topic_file = Path(topics_path or DEFAULT_TOPICS_PATH)
    needs_sync = not store_path.exists()
    if not needs_sync and papers_path.exists():
        try:
            needs_sync = papers_path.stat().st_mtime > store_path.stat().st_mtime
        except OSError:
            needs_sync = True
    if not needs_sync and topic_file.exists():
        try:
            needs_sync = topic_file.stat().st_mtime > store_path.stat().st_mtime
        except OSError:
            needs_sync = True
    if needs_sync and (papers_path.exists() or topic_file.exists()):
        sync_store_from_exports(processed_dir=processed, topics_path=topic_file, db_path=store_path)
    else:
        init_paper_store(store_path)
    return store_path
