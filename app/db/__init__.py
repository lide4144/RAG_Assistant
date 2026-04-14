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


def _get_config_backend() -> str:
    """Read session_store_backend from YAML config with env override.

    Priority:
    1. SESSION_BACKEND env var (if set)
    2. session_store_backend from YAML config
    3. Default 'file'
    """
    import os

    # Priority 1: Environment variable override
    env_backend = os.environ.get("SESSION_BACKEND", "").strip().lower()
    if env_backend:
        return env_backend

    # Priority 2: YAML config
    try:
        from app.config import load_config

        config = load_config()
        backend = getattr(config, "session_store_backend", "")
        if backend:
            return backend.strip().lower()
    except Exception:
        pass

    # Priority 3: Default
    return "file"


def create_store(backend: str | None = None, **kwargs) -> SessionStore:
    """Factory function to create a session store backend.

    Args:
        backend: Storage backend type ('file', 'redis', 'sqlite').
                If None, reads from YAML config (with SESSION_BACKEND env override).
        **kwargs: Backend-specific configuration options.

    Returns:
        SessionStore: Configured storage backend instance.

    Examples:
        >>> store = create_store()  # Uses config or 'file'
        >>> store = create_store("sqlite", db_path="data/sessions.db")
        >>> store = create_store("redis", redis_url="redis://localhost:6379")
    """
    import os

    if backend is None:
        backend = _get_config_backend()

    def _get_config_value(field_name: str, default: str) -> str:
        """Get config value from YAML with env override."""
        env_map = {
            "store_path": "SESSION_STORE_PATH",
            "sqlite_path": "SESSION_SQLITE_PATH",
            "redis_url": "RAG_SESSION_REDIS_URL",
            "redis_key_prefix": "RAG_SESSION_REDIS_KEY_PREFIX",
            "redis_ttl_sec": "RAG_SESSION_REDIS_TTL_SEC",
        }

        # Priority 1: kwargs
        if field_name in kwargs:
            return str(kwargs[field_name])

        # Priority 2: Environment variable
        env_var = env_map.get(field_name)
        if env_var:
            env_val = os.environ.get(env_var, "").strip()
            if env_val:
                return env_val

        # Priority 3: YAML config
        try:
            from app.config import load_config

            config = load_config()
            config_val = getattr(config, f"session_{field_name}", "")
            if config_val:
                return str(config_val)
        except Exception:
            pass

        # Priority 4: Default
        return default

    if backend == "file":
        store_path = _get_config_value("store_path", "data/session_store.json")
        return FileStore(store_path)
    elif backend == "sqlite":
        db_path = _get_config_value("sqlite_path", "data/session_store.db")
        return SQLiteStore(db_path)
    elif backend == "redis":
        try:
            from app.db.redis_store import RedisStore

            redis_url = _get_config_value("redis_url", "")
            redis_key_prefix = _get_config_value("redis_key_prefix", "rag")
            redis_ttl_sec = int(_get_config_value("redis_ttl_sec", "86400"))
            return RedisStore(redis_url, redis_key_prefix, redis_ttl_sec)
        except ImportError:
            raise ImportError(
                "Redis support requires 'redis' package. Install with: pip install redis"
            )
    else:
        raise ValueError(f"Unknown backend: {backend}. Supported: file, sqlite, redis")
