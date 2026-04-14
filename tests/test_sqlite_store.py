"""Tests for SQLite session storage backend."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db.sqlite_store import SQLiteStore
from app.db.migrations import get_current_version, get_migration_status


class TestSQLiteStore(unittest.TestCase):
    """Test cases for SQLiteStore."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.store = SQLiteStore(str(self.db_path))

    def tearDown(self):
        """Clean up temporary database."""
        self.temp_dir.cleanup()

    def test_initialization_creates_database(self):
        """Test that initialization creates the database file."""
        self.assertTrue(self.db_path.exists())

    def test_initialization_runs_migrations(self):
        """Test that initialization runs schema migrations."""
        version = get_current_version(self.db_path)
        self.assertGreater(version, 0)

    def test_write_and_read_session(self):
        """Test writing and reading a session."""
        session_id = "test-session-123"
        data = {
            "turns": [
                {
                    "turn_number": 1,
                    "user_input": "Hello",
                    "standalone_query": "Hello",
                    "answer": "Hi there!",
                    "decision": "qa",
                    "cited_chunk_ids": ["chunk1", "chunk2"],
                    "entity_mentions": ["AI", "ML"],
                    "topic_anchors": ["machine learning"],
                    "transient_constraints": [],
                    "output_warnings": [],
                    "planner_summary": {"decision_result": "qa"},
                }
            ],
            "state": {
                "topic_anchors": ["machine learning"],
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
            "pending_clarify": None,
        }

        # Write session
        self.store.write_session(session_id, data)

        # Read session
        result = self.store.read_session(session_id)

        # Verify
        self.assertEqual(len(result["turns"]), 1)
        self.assertEqual(result["turns"][0]["user_input"], "Hello")
        self.assertEqual(result["turns"][0]["answer"], "Hi there!")

    def test_read_nonexistent_session(self):
        """Test reading a session that doesn't exist."""
        result = self.store.read_session("nonexistent")
        self.assertEqual(result["turns"], [])
        self.assertEqual(result["state"]["dialog_state"], "normal")

    def test_delete_session(self):
        """Test deleting a session."""
        session_id = "test-delete"
        data = {"turns": [], "state": {}}

        # Create session
        self.store.write_session(session_id, data)
        self.assertTrue(self.store.exists(session_id))

        # Delete session
        deleted = self.store.delete_session(session_id)
        self.assertTrue(deleted)
        self.assertFalse(self.store.exists(session_id))

    def test_delete_nonexistent_session(self):
        """Test deleting a session that doesn't exist."""
        result = self.store.delete_session("nonexistent")
        self.assertFalse(result)

    def test_list_sessions(self):
        """Test listing sessions."""
        # Create multiple sessions
        for i in range(3):
            self.store.write_session(
                f"session-{i}",
                {
                    "turns": [
                        {
                            "turn_number": 1,
                            "user_input": f"Query {i}",
                            "standalone_query": f"Query {i}",
                            "answer": f"Answer {i}",
                            "decision": "qa",
                        }
                    ],
                    "state": {},
                },
            )

        # List sessions
        sessions = self.store.list_sessions(limit=10)
        self.assertEqual(len(sessions), 3)

    def test_list_sessions_limit(self):
        """Test session listing with limit."""
        # Create 5 sessions
        for i in range(5):
            self.store.write_session(f"session-{i}", {"turns": [], "state": {}})

        # List with limit
        sessions = self.store.list_sessions(limit=3)
        self.assertEqual(len(sessions), 3)

    def test_update_session(self):
        """Test updating an existing session."""
        session_id = "test-update"

        # Initial write
        self.store.write_session(
            session_id,
            {
                "turns": [{"turn_number": 1, "user_input": "First"}],
                "state": {},
            },
        )

        # Update with new turn
        self.store.write_session(
            session_id,
            {
                "turns": [
                    {"turn_number": 1, "user_input": "First"},
                    {"turn_number": 2, "user_input": "Second"},
                ],
                "state": {},
            },
        )

        # Verify update
        result = self.store.read_session(session_id)
        self.assertEqual(len(result["turns"]), 2)

    def test_clear_all(self):
        """Test clearing all sessions."""
        # Create sessions
        for i in range(3):
            self.store.write_session(f"session-{i}", {"turns": [], "state": {}})

        # Clear all
        self.store.clear_all()

        # Verify
        sessions = self.store.list_sessions()
        self.assertEqual(len(sessions), 0)

    def test_json_fields(self):
        """Test that JSON fields are properly serialized/deserialized."""
        session_id = "test-json"
        data = {
            "turns": [
                {
                    "turn_number": 1,
                    "user_input": "Test",
                    "standalone_query": "Test",
                    "answer": "Test",
                    "cited_chunk_ids": ["id1", "id2", "id3"],
                    "entity_mentions": ["AI", "ML", "NLP"],
                    "planner_summary": {"decision_result": "qa", "strictness": "high"},
                }
            ],
            "state": {},
        }

        self.store.write_session(session_id, data)
        result = self.store.read_session(session_id)

        turn = result["turns"][0]
        self.assertEqual(turn["cited_chunk_ids"], ["id1", "id2", "id3"])
        self.assertEqual(turn["entity_mentions"], ["AI", "ML", "NLP"])

    def test_stats(self):
        """Test getting storage statistics."""
        # Create sessions
        for i in range(3):
            self.store.write_session(
                f"session-{i}",
                {
                    "turns": [{"turn_number": 1, "user_input": f"Q{i}"}],
                    "state": {},
                },
            )

        stats = self.store.get_stats()
        self.assertEqual(stats["session_count"], 3)
        self.assertEqual(stats["turn_count"], 3)
        self.assertTrue(stats["db_size_bytes"] > 0)

    def test_execute_query(self):
        """Test executing a custom query."""
        # Create a session
        self.store.write_session(
            "test-query",
            {"turns": [{"turn_number": 1, "user_input": "Test query"}], "state": {}},
        )

        # Execute query
        results = self.store.execute_query(
            "SELECT id, title FROM sessions WHERE id = ?", ("test-query",)
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "test-query")


class TestMigrations(unittest.TestCase):
    """Test cases for database migrations."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

    def tearDown(self):
        """Clean up temporary database."""
        self.temp_dir.cleanup()

    def test_migration_status_new_db(self):
        """Test migration status for a new database."""
        # Don't create store yet, just check status
        status = get_migration_status(self.db_path)
        self.assertEqual(status["current_version"], 0)
        self.assertFalse(status["is_up_to_date"])

    def test_migration_after_init(self):
        """Test migration status after initialization."""
        store = SQLiteStore(str(self.db_path))
        status = get_migration_status(self.db_path)
        self.assertGreater(status["current_version"], 0)
        self.assertTrue(status["is_up_to_date"])


class TestMultiBackend(unittest.TestCase):
    """Test cases for multi-backend compatibility."""

    def setUp(self):
        """Create temporary directories for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.json_path = Path(self.temp_dir.name) / "test.json"

    def tearDown(self):
        """Clean up temporary directories."""
        self.temp_dir.cleanup()

    def test_file_and_sqlite_compatibility(self):
        """Test that file and sqlite backends produce compatible results."""
        from app.db.file_store import FileStore

        session_id = "compat-test"
        data = {
            "turns": [
                {
                    "turn_number": 1,
                    "user_input": "Test",
                    "standalone_query": "Test",
                    "answer": "Answer",
                    "decision": "qa",
                }
            ],
            "state": {"dialog_state": "normal"},
        }

        # Write to both stores
        sqlite_store = SQLiteStore(str(self.db_path))
        file_store = FileStore(str(self.json_path))

        sqlite_store.write_session(session_id, data)
        file_store.write_session(session_id, data)

        # Read from both
        sqlite_result = sqlite_store.read_session(session_id)
        file_result = file_store.read_session(session_id)

        # Both should have the same turns
        self.assertEqual(len(sqlite_result["turns"]), len(file_result["turns"]))
        self.assertEqual(
            sqlite_result["turns"][0]["user_input"],
            file_result["turns"][0]["user_input"],
        )


if __name__ == "__main__":
    unittest.main()
