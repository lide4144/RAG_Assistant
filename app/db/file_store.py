"""File-based session storage backend.

This module provides a file-based implementation of the SessionStore interface.
It stores session data in a JSON file, compatible with the legacy session_state.py
implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db.session_store import SessionStore


class FileStore(SessionStore):
    """File-based session storage backend using JSON.

    This implementation stores all session data in a single JSON file,
    compatible with the original session_state.py implementation.

    Features:
        - Simple JSON file storage
        - Human-readable format
        - No external dependencies
        - Compatible with legacy implementations

    Args:
        store_path: Path to the JSON file.
                    Defaults to "data/session_store.json"

    Example:
        >>> store = FileStore("data/sessions.json")
        >>> store.write_session("abc-123", {"turns": [...]})
        >>> session = store.read_session("abc-123")

    Environment Variables:
        SESSION_STORE_PATH: Override default file path
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        """Initialize file store.

        Args:
            store_path: Path to JSON file. If None, uses environment
                       variable SESSION_STORE_PATH or defaults to
                       "data/session_store.json"
        """
        import os

        if store_path is None:
            store_path = os.environ.get("SESSION_STORE_PATH", "data/session_store.json")

        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_store(self) -> dict[str, Any]:
        """Read the entire store from file."""
        if not self.store_path.exists():
            return {"sessions": {}}

        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"sessions": {}}

        if not isinstance(payload, dict):
            return {"sessions": {}}

        sessions = payload.get("sessions")
        if not isinstance(sessions, dict):
            return {"sessions": {}}

        return payload

    def _write_store(self, payload: dict[str, Any]) -> None:
        """Write the entire store to file."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _ensure_session(self, session_id: str) -> dict[str, Any]:
        """Ensure session exists with default structure."""
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

    def read_session(self, session_id: str) -> dict[str, Any]:
        """Read a session record by ID.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            dict: Session data with turns and state.
                  Returns empty structure if not found.
        """
        payload = self._read_store()
        sessions = payload.get("sessions", {})

        if session_id not in sessions:
            return self._ensure_session(session_id)

        session = sessions[session_id]

        # Ensure all required fields exist
        if "turns" not in session or not isinstance(session["turns"], list):
            session["turns"] = []

        if "pending_clarify" not in session:
            session["pending_clarify"] = None

        if "state" not in session or not isinstance(session["state"], dict):
            session["state"] = self._ensure_session(session_id)["state"]

        return session

    def write_session(self, session_id: str, data: dict[str, Any]) -> None:
        """Write or update a session record.

        Args:
            session_id: Unique identifier for the session.
            data: Complete session data including turns and state.

        Raises:
            IOError: If write operation fails.
        """
        payload = self._read_store()
        sessions = payload.setdefault("sessions", {})
        sessions[session_id] = data
        self._write_store(payload)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session record.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            bool: True if session was deleted, False if not found.
        """
        payload = self._read_store()
        sessions = payload.get("sessions", {})

        if session_id in sessions:
            del sessions[session_id]
            self._write_store(payload)
            return True

        return False

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all session records.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            list: List of session summaries.
        """
        payload = self._read_store()
        sessions = payload.get("sessions", {})

        # Sort by session ID (approximate by insertion order in Python 3.7+)
        items = list(sessions.items())[:limit]

        result = []
        for session_id, session in items:
            turns = session.get("turns", [])
            first_input = ""
            if turns:
                first_input = turns[0].get("user_input", "")[:100]

            result.append(
                {
                    "id": session_id,
                    "title": first_input or "Untitled Session",
                    "messageCount": len(turns),
                    "createdAt": "",  # Not stored in legacy format
                    "updatedAt": "",  # Not stored in legacy format
                }
            )

        return result

    def clear_all(self) -> None:
        """Clear all session records. Use with caution."""
        self._write_store({"sessions": {}})

    def exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        payload = self._read_store()
        return session_id in payload.get("sessions", {})
