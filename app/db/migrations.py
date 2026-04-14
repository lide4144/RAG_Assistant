"""Database migration utilities for SQLite session storage.

This module provides schema versioning and migration capabilities
for the SQLite session storage backend.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Migration registry: (version_number, sql_statements)
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        -- Sessions table: stores session metadata
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Session messages table: stores frontend message format
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            metadata TEXT,  -- JSON: citations, mode, viewMode, etc.
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        -- Session turns table: stores backend turn format for debugging
        CREATE TABLE IF NOT EXISTS session_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            user_input TEXT,
            standalone_query TEXT,
            answer TEXT,
            decision TEXT,
            cited_chunk_ids TEXT,  -- JSON array
            entity_mentions TEXT,  -- JSON array
            topic_anchors TEXT,    -- JSON array
            transient_constraints TEXT,  -- JSON array
            output_warnings TEXT,  -- JSON array
            planner_summary TEXT,  -- JSON object
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            UNIQUE(session_id, turn_number)
        );

        -- Schema migrations tracking table
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_session_id ON session_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_messages_created_at ON session_messages(created_at);
        CREATE INDEX IF NOT EXISTS idx_turns_session_id ON session_turns(session_id);
        CREATE INDEX IF NOT EXISTS idx_turns_session_turn ON session_turns(session_id, turn_number);
        """,
    ),
]


def get_current_version(db_path: str | Path) -> int:
    """Get the current schema version from the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        int: Current schema version (0 if no migrations applied).
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return 0

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute("SELECT MAX(version) FROM schema_migrations")
            result = cursor.fetchone()
            return result[0] if result and result[0] is not None else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def set_version(db_path: str | Path, version: int) -> None:
    """Record a migration version as applied.

    Args:
        db_path: Path to the SQLite database file.
        version: Migration version number to record.
    """
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations (version) VALUES (?)", (version,)
        )
        conn.commit()


def migrate(db_path: str | Path) -> int:
    """Run pending migrations on the database.

    This function checks the current schema version and applies
    any pending migrations in order.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        int: Number of migrations applied.

    Raises:
        sqlite3.Error: If migration fails.

    Example:
        >>> migrate("data/sessions.db")
        1  # One migration was applied
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    current_version = get_current_version(db_path)
    applied_count = 0

    for version, sql in MIGRATIONS:
        if version > current_version:
            with sqlite3.connect(str(db_path)) as conn:
                # Enable foreign keys
                conn.execute("PRAGMA foreign_keys = ON")
                # Execute migration
                conn.executescript(sql)
                # Record version
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
                )
                conn.commit()
            applied_count += 1

    return applied_count


def ensure_migrated(db_path: str | Path) -> None:
    """Ensure database is migrated to latest version.

    This is a convenience function that calls migrate() and handles
    common errors. Use this in production code.

    Args:
        db_path: Path to the SQLite database file.

    Raises:
        RuntimeError: If migration fails with details.
    """
    try:
        applied = migrate(db_path)
        if applied > 0:
            print(f"[migrations] Applied {applied} migration(s) to {db_path}")
    except sqlite3.Error as e:
        raise RuntimeError(f"Database migration failed: {e}") from e


def get_migration_status(db_path: str | Path) -> dict[str, Any]:
    """Get detailed migration status for debugging.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        dict: Status information including current version,
              pending migrations, and total migrations.
    """
    current = get_current_version(db_path)
    total = len(MIGRATIONS)
    pending = [v for v, _ in MIGRATIONS if v > current]

    return {
        "current_version": current,
        "latest_version": total,
        "pending_count": len(pending),
        "pending_versions": pending,
        "is_up_to_date": current >= total,
        "db_path": str(db_path),
    }
