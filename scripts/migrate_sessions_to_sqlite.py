#!/usr/bin/env python3
"""Migrate session data from JSON file to SQLite database.

Usage:
    python scripts/migrate_sessions_to_sqlite.py [json_path] [sqlite_path]

Examples:
    # Use default paths
    python scripts/migrate_sessions_to_sqlite.py

    # Specify custom paths
    python scripts/migrate_sessions_to_sqlite.py data/session_store.json data/session_store.db

    # Dry run (preview without writing)
    python scripts/migrate_sessions_to_sqlite.py --dry-run
"""

import json
import sys
from pathlib import Path
from typing import Any


def migrate_sessions(
    json_path: str, sqlite_path: str, dry_run: bool = False
) -> dict[str, Any]:
    """Migrate sessions from JSON file to SQLite database.

    Args:
        json_path: Path to the JSON session store file.
        sqlite_path: Path to the SQLite database file.
        dry_run: If True, only preview the migration without writing.

    Returns:
        dict: Migration statistics.
    """
    json_file = Path(json_path)
    if not json_file.exists():
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)

    # Read JSON data
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}")
        sys.exit(1)

    sessions = data.get("sessions", {})
    if not sessions:
        print("No sessions found in JSON file.")
        return {"total": 0, "migrated": 0, "errors": 0}

    print(f"Found {len(sessions)} session(s) in JSON file.")

    if dry_run:
        print("\n--- DRY RUN MODE (no changes will be made) ---\n")
        for session_id, session_data in sessions.items():
            turns = session_data.get("turns", [])
            print(f"Session: {session_id}")
            print(f"  Turns: {len(turns)}")
            if turns:
                print(f"  First input: {turns[0].get('user_input', 'N/A')[:50]}...")
        return {"total": len(sessions), "migrated": 0, "dry_run": True}

    # Import SQLite store
    try:
        from app.db import SQLiteStore
    except ImportError:
        print("Error: Cannot import SQLiteStore. Make sure you're in the project root.")
        sys.exit(1)

    # Create SQLite store
    store = SQLiteStore(sqlite_path)

    # Migrate sessions
    migrated = 0
    errors = 0

    for session_id, session_data in sessions.items():
        try:
            store.write_session(session_id, session_data)
            migrated += 1
            print(f"✓ Migrated: {session_id}")
        except Exception as e:
            errors += 1
            print(f"✗ Error migrating {session_id}: {e}")

    print(f"\n--- Migration Complete ---")
    print(f"Total sessions: {len(sessions)}")
    print(f"Successfully migrated: {migrated}")
    print(f"Errors: {errors}")
    print(f"SQLite database: {sqlite_path}")

    return {
        "total": len(sessions),
        "migrated": migrated,
        "errors": errors,
    }


def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        sys.argv.remove("--dry-run")

    if len(sys.argv) > 3:
        print(__doc__)
        sys.exit(1)

    json_path = sys.argv[1] if len(sys.argv) > 1 else "data/session_store.json"
    sqlite_path = sys.argv[2] if len(sys.argv) > 2 else "data/session_store.db"

    print(f"Migrating sessions from:\n  JSON: {json_path}\n  SQLite: {sqlite_path}\n")

    stats = migrate_sessions(json_path, sqlite_path, dry_run)

    if dry_run:
        print("\nTo perform the actual migration, run without --dry-run")


if __name__ == "__main__":
    main()
