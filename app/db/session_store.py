"""Abstract base class for session storage backends.

This module defines the SessionStore interface that all storage backends
must implement. The interface provides a unified way to store and retrieve
session data regardless of the underlying storage mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SessionStore(ABC):
    """Abstract base class for session storage backends.

    This class defines the interface that all session storage implementations
    must follow. It provides methods for reading, writing, deleting, and listing
    session records.

    Implementations:
        - FileStore: JSON file-based storage
        - RedisStore: Redis-based storage with TTL
        - SQLiteStore: SQLite-based storage for SQL queries

    Example:
        >>> class MyStore(SessionStore):
        ...     def read_session(self, session_id: str) -> dict[str, Any]:
        ...         # Implementation
        ...         pass
        ...     def write_session(self, session_id: str, data: dict[str, Any]) -> None:
        ...         # Implementation
        ...         pass
        ...     # ... implement other methods
    """

    @abstractmethod
    def read_session(self, session_id: str) -> dict[str, Any]:
        """Read a session record by ID.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            dict: Session data including turns and state.
            Returns empty session structure if not found.

        Example:
            >>> store = create_store()
            >>> session = store.read_session("abc-123")
            >>> print(session.get("turns", []))
        """
        pass

    @abstractmethod
    def write_session(self, session_id: str, data: dict[str, Any]) -> None:
        """Write or update a session record.

        Args:
            session_id: Unique identifier for the session.
            data: Complete session data to store.

        Raises:
            IOError: If write operation fails.

        Example:
            >>> store = create_store()
            >>> store.write_session("abc-123", {"turns": [...], "state": {...}})
        """
        pass

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete a session record.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            bool: True if session was deleted, False if not found.

        Example:
            >>> store = create_store()
            >>> if store.delete_session("abc-123"):
            ...     print("Session deleted")
        """
        pass

    @abstractmethod
    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all session records.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            list: List of session summaries, each containing at least
                  'id', 'title', 'created_at', 'updated_at'.

        Example:
            >>> store = create_store()
            >>> sessions = store.list_sessions(limit=10)
            >>> for session in sessions:
            ...     print(f"{session['id']}: {session['title']}")
        """
        pass

    @abstractmethod
    def clear_all(self) -> None:
        """Clear all session records. Use with caution, mainly for testing.

        This method removes all session data from the storage backend.
        It should be used carefully, primarily in test environments.

        Example:
            >>> store = create_store()
            >>> store.clear_all()  # Clear all sessions
        """
        pass

    def exists(self, session_id: str) -> bool:
        """Check if a session exists.

        This is a convenience method with a default implementation
        that reads the session. Backends may override with more
        efficient implementations.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            bool: True if session exists.
        """
        try:
            session = self.read_session(session_id)
            return bool(session.get("turns") or session.get("state"))
        except Exception:
            return False

    def close(self) -> None:
        """Close any open connections or resources.

        This method should be called when done using the store
        to ensure proper cleanup of resources.

        Default implementation does nothing.
        """
        pass
