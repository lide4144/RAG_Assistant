"""Session storage backends for RAG GPT.

This module provides pluggable storage backends for session state management:
- FileStore: JSON file-based storage (default)
- RedisStore: Redis-based storage with TTL support
- SQLiteStore: SQLite-based storage for debugging and SQL queries

Usage:
    from app.db import create_store

    # Create store based on environment configuration
    store = create_store()

    # Or explicitly specify backend
    store = create_store("sqlite", db_path="data/sessions.db")
"""

from app.db.session_store import SessionStore
from app.db.file_store import FileStore
from app.db.sqlite_store import SQLiteStore

try:
    from app.db.redis_store import RedisStore

    __all__ = ["SessionStore", "FileStore", "RedisStore", "SQLiteStore", "create_store"]
except ImportError:
    # Redis is optional
    __all__ = ["SessionStore", "FileStore", "SQLiteStore", "create_store"]


def create_store(backend: str | None = None, **kwargs) -> SessionStore:
    """Factory function to create a session store backend.

    Args:
        backend: Storage backend type ('file', 'redis', 'sqlite').
                If None, reads from SESSION_BACKEND env var, defaults to 'file'.
        **kwargs: Backend-specific configuration options.

    Returns:
        SessionStore: Configured storage backend instance.

    Examples:
        >>> store = create_store()  # Uses SESSION_BACKEND or 'file'
        >>> store = create_store("sqlite", db_path="data/sessions.db")
        >>> store = create_store("redis", redis_url="redis://localhost:6379")
    """
    import os

    if backend is None:
        backend = os.environ.get("SESSION_BACKEND", "file").strip().lower()

    if backend == "file":
        store_path = kwargs.get("store_path") or os.environ.get(
            "SESSION_STORE_PATH", "data/session_store.json"
        )
        return FileStore(store_path)
    elif backend == "sqlite":
        db_path = kwargs.get("db_path") or os.environ.get(
            "SESSION_SQLITE_PATH", "data/session_store.db"
        )
        return SQLiteStore(db_path)
    elif backend == "redis":
        try:
            from app.db.redis_store import RedisStore

            redis_url = kwargs.get("redis_url") or os.environ.get(
                "RAG_SESSION_REDIS_URL", ""
            )
            redis_key_prefix = kwargs.get("redis_key_prefix", "rag")
            redis_ttl_sec = kwargs.get("redis_ttl_sec", 86400)
            return RedisStore(redis_url, redis_key_prefix, redis_ttl_sec)
        except ImportError:
            raise ImportError(
                "Redis support requires 'redis' package. Install with: pip install redis"
            )
    else:
        raise ValueError(f"Unknown backend: {backend}. Supported: file, sqlite, redis")
