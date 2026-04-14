"""Redis-based session storage backend.

This module provides a Redis implementation of the SessionStore interface.
It stores session data in Redis with TTL support.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.session_store import SessionStore


class RedisStore(SessionStore):
    """Redis-based session storage backend with TTL support.

    This implementation stores session data in Redis, providing
    fast access and automatic expiration via TTL.

    Features:
        - Fast in-memory storage
        - TTL support for automatic expiration
        - Distributed storage support
        - Connection pooling

    Args:
        redis_url: Redis connection URL.
                   Defaults to "redis://localhost:6379"
        key_prefix: Prefix for Redis keys.
                    Defaults to "rag"
        ttl_sec: Time-to-live in seconds.
                 Defaults to 86400 (24 hours)

    Example:
        >>> store = RedisStore("redis://localhost:6379", "rag", 86400)
        >>> store.write_session("abc-123", {"turns": [...]})
        >>> session = store.read_session("abc-123")

    Environment Variables:
        RAG_SESSION_REDIS_URL: Redis connection URL
    """

    _client_cache: dict[str, Any] = {}

    def __init__(
        self,
        redis_url: str | None = None,
        key_prefix: str = "rag",
        ttl_sec: int = 86400,
    ) -> None:
        """Initialize Redis store.

        Args:
            redis_url: Redis connection URL. If None, uses environment
                      variable RAG_SESSION_REDIS_URL.
            key_prefix: Prefix for Redis keys.
            ttl_sec: Time-to-live in seconds.

        Raises:
            ImportError: If redis package is not installed.
            ConnectionError: If cannot connect to Redis.
        """
        import os

        try:
            import redis as redis_lib
        except ImportError:
            raise ImportError(
                "Redis support requires 'redis' package. "
                "Install with: pip install redis"
            )

        self.redis_url = redis_url or os.environ.get("RAG_SESSION_REDIS_URL", "")
        self.key_prefix = key_prefix
        self.ttl_sec = ttl_sec

        if not self.redis_url:
            raise ValueError(
                "Redis URL not provided. Set RAG_SESSION_REDIS_URL environment variable."
            )

        # Use cached client if available
        cache_key = f"{self.redis_url}:{self.key_prefix}"
        if cache_key in self._client_cache:
            self._client = self._client_cache[cache_key]
        else:
            self._client = redis_lib.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            self._client_cache[cache_key] = self._client

        # Test connection
        try:
            self._client.ping()
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Redis: {e}") from e

    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for a session."""
        return f"{self.key_prefix}:session:{session_id}"

    def _ensure_session(self) -> dict[str, Any]:
        """Ensure session has default structure."""
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
                  Returns empty structure if not found or expired.
        """
        key = self._session_key(session_id)
        raw = self._client.get(key)

        if not raw:
            return self._ensure_session()

        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        return self._ensure_session()

    def write_session(self, session_id: str, data: dict[str, Any]) -> None:
        """Write or update a session record.

        Args:
            session_id: Unique identifier for the session.
            data: Complete session data including turns and state.
        """
        key = self._session_key(session_id)
        value = json.dumps(data, ensure_ascii=False)

        if self.ttl_sec > 0:
            self._client.setex(key, self.ttl_sec, value)
        else:
            self._client.set(key, value)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session record.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            bool: True if session was deleted, False if not found.
        """
        key = self._session_key(session_id)
        result = self._client.delete(key)
        return result > 0

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all session records.

        Note: Redis does not support efficient listing of all keys.
        This method scans for keys matching the pattern.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            list: List of session summaries.
        """
        pattern = self._session_key("*")
        sessions = []

        # Use scan_iter for better performance with large datasets
        for key in self._client.scan_iter(match=pattern, count=100):
            if len(sessions) >= limit:
                break

            # Extract session_id from key
            prefix_len = len(self._session_key(""))
            session_id = key[prefix_len:]

            # Get session data
            raw = self._client.get(key)
            if raw:
                try:
                    data = json.loads(raw)
                    turns = data.get("turns", [])
                    first_input = ""
                    if turns:
                        first_input = turns[0].get("user_input", "")[:100]

                    sessions.append(
                        {
                            "id": session_id,
                            "title": first_input or "Untitled Session",
                            "messageCount": len(turns),
                            "createdAt": "",
                            "updatedAt": "",
                        }
                    )
                except json.JSONDecodeError:
                    continue

        return sessions

    def clear_all(self) -> None:
        """Clear all session records. Use with caution."""
        pattern = self._session_key("*")
        for key in self._client.scan_iter(match=pattern):
            self._client.delete(key)

    def exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        key = self._session_key(session_id)
        return self._client.exists(key) > 0

    def close(self) -> None:
        """Close Redis connection."""
        if hasattr(self._client, "close"):
            self._client.close()
