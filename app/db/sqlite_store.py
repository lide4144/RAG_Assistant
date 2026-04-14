"""SQLite-based session storage backend.

This module provides a SQLite implementation of the SessionStore interface.
It stores session data in a SQLite database file, enabling SQL queries for
debugging and analysis.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.session_store import SessionStore
from app.db.migrations import ensure_migrated


class SQLiteStore(SessionStore):
    """SQLite-based session storage backend.

    This implementation stores session data in a SQLite database file,
    providing SQL query capabilities for debugging and analysis.

    Features:
        - Automatic database schema migration
        - WAL mode for better concurrency
        - JSON field support for flexible metadata
        - Foreign key constraints for data integrity

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to "data/session_store.db"

    Example:
        >>> store = SQLiteStore("data/sessions.db")
        >>> store.write_session("abc-123", {"turns": [...]})
        >>> session = store.read_session("abc-123")
        >>>
        >>> # Query with SQL
        >>> store.execute_query(
        ...     "SELECT * FROM sessions WHERE updated_at > datetime('now', '-1 day')"
        ... )

    Environment Variables:
        SESSION_SQLITE_PATH: Override default database path
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize SQLite store.

        Args:
            db_path: Path to database file. If None, uses environment
                    variable SESSION_SQLITE_PATH or defaults to
                    "data/session_store.db"
        """
        import os

        if db_path is None:
            db_path = os.environ.get("SESSION_SQLITE_PATH", "data/session_store.db")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Run migrations on init
        ensure_migrated(self.db_path)

        # Enable WAL mode for better concurrency
        self._enable_wal_mode()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper settings."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _enable_wal_mode(self) -> None:
        """Enable WAL mode for better read concurrency."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")

    def read_session(self, session_id: str) -> dict[str, Any]:
        """Read a session record by ID.

        Reads the session from SQLite and reconstructs the full session
        structure including turns and state.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            dict: Session data with turns and state.
                  Returns empty structure if not found.
        """
        with self._get_connection() as conn:
            # Check if session exists
            cursor = conn.execute(
                "SELECT id, title, created_at FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()

            if row is None:
                # Return empty session structure
                return {
                    "turns": [],
                    "pending_clarify": None,
                    "state": {
                        "topic_anchors": [],
                        "transient_constraints": [],
                        "last_reset_turn_number": 0,
                        "clarify_count_for_topic": 0,
                        "dialog_state": "normal",
                        "summary_memory": "",
                        "semantic_recall_memory": [],
                        "user_honesty_preferences": {
                            "hide_low_confidence_warnings": False,
                            "acknowledged_at": None,
                            "acknowledgment_count": 0,
                        },
                    },
                }

            # Read turns
            cursor = conn.execute(
                """SELECT turn_number, user_input, standalone_query, answer,
                          decision, cited_chunk_ids, entity_mentions,
                          topic_anchors, transient_constraints, output_warnings,
                          planner_summary, created_at
                   FROM session_turns
                   WHERE session_id = ?
                   ORDER BY turn_number""",
                (session_id,),
            )
            turns = []
            for row in cursor.fetchall():
                turn = {
                    "turn_number": row["turn_number"],
                    "timestamp": row["created_at"],
                    "user_input": row["user_input"] or "",
                    "standalone_query": row["standalone_query"] or "",
                    "answer": row["answer"] or "",
                    "decision": row["decision"] or "",
                    "cited_chunk_ids": json.loads(row["cited_chunk_ids"])
                    if row["cited_chunk_ids"]
                    else [],
                    "entity_mentions": json.loads(row["entity_mentions"])
                    if row["entity_mentions"]
                    else [],
                    "topic_anchors": json.loads(row["topic_anchors"])
                    if row["topic_anchors"]
                    else [],
                    "transient_constraints": json.loads(row["transient_constraints"])
                    if row["transient_constraints"]
                    else [],
                    "output_warnings": json.loads(row["output_warnings"])
                    if row["output_warnings"]
                    else [],
                    "planner_summary": json.loads(row["planner_summary"])
                    if row["planner_summary"]
                    else {},
                }
                turns.append(turn)

            # Build state from latest turn or default
            state = {
                "topic_anchors": [],
                "transient_constraints": [],
                "last_reset_turn_number": 0,
                "clarify_count_for_topic": 0,
                "dialog_state": "normal",
                "summary_memory": "",
                "semantic_recall_memory": [],
                "user_honesty_preferences": {
                    "hide_low_confidence_warnings": False,
                    "acknowledged_at": None,
                    "acknowledgment_count": 0,
                },
            }

            if turns:
                last_turn = turns[-1]
                state["topic_anchors"] = last_turn.get("topic_anchors", [])
                state["transient_constraints"] = last_turn.get(
                    "transient_constraints", []
                )

            return {
                "turns": turns,
                "pending_clarify": None,  # Simplified for now
                "state": state,
            }

    def write_session(self, session_id: str, data: dict[str, Any]) -> None:
        """Write or update a session record.

        Writes the complete session data to SQLite, including metadata,
        turns, and messages.

        Args:
            session_id: Unique identifier for the session.
            data: Complete session data including turns and state.

        Raises:
            sqlite3.Error: If database operation fails.
        """
        now = datetime.now(timezone.utc).isoformat()
        title = self._extract_title(data)
        turns = data.get("turns", [])

        with self._get_connection() as conn:
            # Insert or update session
            conn.execute(
                """INSERT INTO sessions (id, title, created_at, updated_at)
                   VALUES (?, ?, COALESCE(
                       (SELECT created_at FROM sessions WHERE id = ?),
                       ?
                   ), ?)
                   ON CONFLICT(id) DO UPDATE SET
                   title = excluded.title,
                   updated_at = excluded.updated_at""",
                (session_id, title, session_id, now, now),
            )

            # Insert turns
            for turn in turns:
                turn_number = turn.get("turn_number", 0)
                created_at = turn.get("timestamp", now)

                conn.execute(
                    """INSERT INTO session_turns
                       (session_id, turn_number, user_input, standalone_query,
                        answer, decision, cited_chunk_ids, entity_mentions,
                        topic_anchors, transient_constraints, output_warnings,
                        planner_summary, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(session_id, turn_number) DO UPDATE SET
                       user_input = excluded.user_input,
                       standalone_query = excluded.standalone_query,
                       answer = excluded.answer,
                       decision = excluded.decision,
                       cited_chunk_ids = excluded.cited_chunk_ids,
                       entity_mentions = excluded.entity_mentions,
                       topic_anchors = excluded.topic_anchors,
                       transient_constraints = excluded.transient_constraints,
                       output_warnings = excluded.output_warnings,
                       planner_summary = excluded.planner_summary""",
                    (
                        session_id,
                        turn_number,
                        turn.get("user_input", ""),
                        turn.get("standalone_query", ""),
                        turn.get("answer", ""),
                        turn.get("decision", ""),
                        json.dumps(turn.get("cited_chunk_ids", [])),
                        json.dumps(turn.get("entity_mentions", [])),
                        json.dumps(turn.get("topic_anchors", [])),
                        json.dumps(turn.get("transient_constraints", [])),
                        json.dumps(turn.get("output_warnings", [])),
                        json.dumps(turn.get("planner_summary", {})),
                        created_at,
                    ),
                )

            conn.commit()

    def _extract_title(self, data: dict[str, Any]) -> str | None:
        """Extract session title from first user input."""
        turns = data.get("turns", [])
        for turn in turns:
            user_input = turn.get("user_input", "").strip()
            if user_input:
                # Truncate to reasonable length
                return user_input[:100] if len(user_input) > 100 else user_input
        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session record.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            bool: True if session was deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all session records.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            list: List of session summaries.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT s.id, s.title, s.created_at, s.updated_at,
                          COUNT(st.turn_number) as turn_count
                   FROM sessions s
                   LEFT JOIN session_turns st ON s.id = st.session_id
                   GROUP BY s.id
                   ORDER BY s.updated_at DESC
                   LIMIT ?""",
                (limit,),
            )

            sessions = []
            for row in cursor.fetchall():
                sessions.append(
                    {
                        "id": row["id"],
                        "title": row["title"] or "Untitled Session",
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "messageCount": row["turn_count"],
                    }
                )

            return sessions

    def clear_all(self) -> None:
        """Clear all session records. Use with caution."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM session_turns")
            conn.execute("DELETE FROM sessions")
            conn.commit()

    def exists(self, session_id: str) -> bool:
        """Check if a session exists in the database."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
            return cursor.fetchone() is not None

    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a SQL query (for debugging).

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            list: Query results as list of dictionaries.

        Warning:
            This method is intended for debugging only.
            Be careful with user-provided queries.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics.

        Returns:
            dict: Statistics including session count, turn count, etc.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            session_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM session_turns")
            turn_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT MAX(updated_at) FROM sessions")
            last_update = cursor.fetchone()[0]

            return {
                "session_count": session_count,
                "turn_count": turn_count,
                "last_update": last_update,
                "db_path": str(self.db_path),
                "db_size_bytes": self.db_path.stat().st_size
                if self.db_path.exists()
                else 0,
            }
