"""Integration tests for session storage backends.

Tests the integration between session_state.py and storage backends.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from app import session_state
from app.db import create_store, FileStore, SQLiteStore


class TestSessionStorageIntegration(unittest.TestCase):
    """Integration tests for session storage with session_state module."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.json_path = Path(self.temp_dir.name) / "test.json"

        # Clear store cache and environment before each test
        session_state._STORE_CACHE.clear()

        # Clean up any existing env vars
        for key in ["SESSION_BACKEND", "SESSION_STORE_PATH", "SESSION_SQLITE_PATH"]:
            if key in os.environ:
                del os.environ[key]

    def tearDown(self):
        """Clean up test environment."""
        # Clean up environment
        for key in ["SESSION_BACKEND", "SESSION_STORE_PATH", "SESSION_SQLITE_PATH"]:
            if key in os.environ:
                del os.environ[key]
        session_state._STORE_CACHE.clear()
        self.temp_dir.cleanup()

    def test_append_turn_record_with_sqlite(self):
        """Test that append_turn_record writes to SQLite correctly."""
        session_id = "test-session-001"

        # Set environment for SQLite
        os.environ["SESSION_BACKEND"] = "sqlite"
        os.environ["SESSION_SQLITE_PATH"] = str(self.db_path)

        # Clear cache to pick up new env vars
        session_state._STORE_CACHE.clear()

        try:
            # Append a turn
            turn_number = session_state.append_turn_record(
                session_id,
                user_input="What is GraphRAG?",
                standalone_query="What is GraphRAG?",
                answer="GraphRAG is a retrieval-augmented generation method using knowledge graphs.",
                cited_chunk_ids=["chunk-1", "chunk-2"],
                decision="qa",
                output_warnings=[],
            )

            self.assertEqual(turn_number, 1)

            # Verify the session was written
            store = SQLiteStore(str(self.db_path))
            session = store.read_session(session_id)

            self.assertEqual(len(session["turns"]), 1)
            self.assertEqual(session["turns"][0]["user_input"], "What is GraphRAG?")
            self.assertEqual(session["turns"][0]["decision"], "qa")
            self.assertEqual(
                session["turns"][0]["cited_chunk_ids"], ["chunk-1", "chunk-2"]
            )

        finally:
            # Clean up environment
            del os.environ["SESSION_BACKEND"]
            del os.environ["SESSION_SQLITE_PATH"]

    def test_load_history_window_from_sqlite(self):
        """Test that load_history_window reads from SQLite correctly."""
        session_id = "test-session-002"

        # Set environment for SQLite
        os.environ["SESSION_BACKEND"] = "sqlite"
        os.environ["SESSION_SQLITE_PATH"] = str(self.db_path)

        # Clear cache
        session_state._STORE_CACHE.clear()

        try:
            # First, append some turns
            for i in range(3):
                session_state.append_turn_record(
                    session_id,
                    user_input=f"Question {i + 1}",
                    standalone_query=f"Question {i + 1}",
                    answer=f"Answer {i + 1}",
                    cited_chunk_ids=[f"chunk-{i + 1}"],
                    decision="qa",
                    output_warnings=[],
                )

            # Load history window
            window, token_est = session_state.load_history_window(
                session_id,
                window_size=2,
            )

            # Should get last 2 turns + summary memory
            # Note: window may include summary/semantic memory items
            real_turns = [
                t
                for t in window
                if t.get("turn_type")
                not in {"summary_memory", "semantic_recall_memory"}
            ]
            self.assertEqual(len(real_turns), 2)
            self.assertEqual(real_turns[0]["user_input"], "Question 2")
            self.assertEqual(real_turns[1]["user_input"], "Question 3")

        finally:
            del os.environ["SESSION_BACKEND"]
            del os.environ["SESSION_SQLITE_PATH"]

    def test_clear_session_with_sqlite(self):
        """Test that clear_session removes data from SQLite."""
        session_id = "test-session-003"

        # Set environment for SQLite
        os.environ["SESSION_BACKEND"] = "sqlite"
        os.environ["SESSION_SQLITE_PATH"] = str(self.db_path)

        # Clear cache
        session_state._STORE_CACHE.clear()

        try:
            # Create a session
            session_state.append_turn_record(
                session_id,
                user_input="Test question",
                standalone_query="Test question",
                answer="Test answer",
                cited_chunk_ids=["chunk-1"],
                decision="qa",
                output_warnings=[],
            )

            # Verify session exists
            store = SQLiteStore(str(self.db_path))
            self.assertTrue(store.exists(session_id))

            # Clear the session
            cleared = session_state.clear_session(session_id)
            self.assertTrue(cleared)

            # Verify session is gone
            self.assertFalse(store.exists(session_id))

        finally:
            del os.environ["SESSION_BACKEND"]
            del os.environ["SESSION_SQLITE_PATH"]

    def test_backend_behavior_consistency(self):
        """Test that file and SQLite backends behave consistently."""
        session_id = "test-session-004"
        test_data = {
            "turns": [
                {
                    "turn_number": 1,
                    "user_input": "Test input",
                    "standalone_query": "Test standalone",
                    "answer": "Test answer",
                    "decision": "qa",
                    "cited_chunk_ids": ["chunk1"],
                    "entity_mentions": ["AI"],
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

        # Test FileStore
        file_store = FileStore(str(self.json_path))
        file_store.write_session(session_id, test_data)
        file_session = file_store.read_session(session_id)

        # Test SQLiteStore
        sqlite_store = SQLiteStore(str(self.db_path))
        sqlite_store.write_session(session_id, test_data)
        sqlite_session = sqlite_store.read_session(session_id)

        # Compare key fields
        self.assertEqual(len(file_session["turns"]), len(sqlite_session["turns"]))
        self.assertEqual(
            file_session["turns"][0]["user_input"],
            sqlite_session["turns"][0]["user_input"],
        )
        self.assertEqual(
            file_session["turns"][0]["cited_chunk_ids"],
            sqlite_session["turns"][0]["cited_chunk_ids"],
        )
        self.assertEqual(
            file_session["state"]["dialog_state"],
            sqlite_session["state"]["dialog_state"],
        )

    def test_session_state_with_file_backend(self):
        """Test session_state functions with file backend."""
        # Use unique session id with uuid to avoid conflicts
        import uuid

        session_id = f"file-test-{uuid.uuid4().hex[:8]}"

        os.environ["SESSION_BACKEND"] = "file"
        os.environ["SESSION_STORE_PATH"] = str(self.json_path)
        session_state._STORE_CACHE.clear()

        try:
            # Clear any existing session first
            session_state.clear_session(session_id)

            # Append turn
            turn_number = session_state.append_turn_record(
                session_id,
                user_input="File backend test",
                standalone_query="File backend test",
                answer="Test answer",
                cited_chunk_ids=["chunk-1"],
                decision="qa",
                output_warnings=[],
            )

            self.assertEqual(turn_number, 1)

            # Load history
            window, _ = session_state.load_history_window(session_id)
            real_turns = [
                t
                for t in window
                if t.get("turn_type")
                not in {"summary_memory", "semantic_recall_memory"}
            ]
            self.assertEqual(len(real_turns), 1)

            # Clear session
            cleared = session_state.clear_session(session_id)
            self.assertTrue(cleared)

        finally:
            if "SESSION_BACKEND" in os.environ:
                del os.environ["SESSION_BACKEND"]
            if "SESSION_STORE_PATH" in os.environ:
                del os.environ["SESSION_STORE_PATH"]

    def test_session_state_backend_switching(self):
        """Test that backend can be switched via environment."""
        import uuid

        session_id1 = f"switch-test-1-{uuid.uuid4().hex[:8]}"
        session_id2 = f"switch-test-2-{uuid.uuid4().hex[:8]}"

        # Create stores directly
        file_store = FileStore(str(self.json_path))
        sqlite_store = SQLiteStore(str(self.db_path))

        # Write to file backend
        file_store.write_session(
            session_id1,
            {"turns": [{"turn_number": 1, "user_input": "File test"}], "state": {}},
        )

        # Write to sqlite backend
        sqlite_store.write_session(
            session_id2,
            {"turns": [{"turn_number": 1, "user_input": "SQLite test"}], "state": {}},
        )

        # Verify isolation
        self.assertTrue(file_store.exists(session_id1))
        self.assertFalse(file_store.exists(session_id2))

        self.assertTrue(sqlite_store.exists(session_id2))
        self.assertFalse(sqlite_store.exists(session_id1))


class TestMultiBackendCompatibility(unittest.TestCase):
    """Test compatibility across different storage backends."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.json_path = Path(self.temp_dir.name) / "test.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_store_factory(self):
        """Test create_store factory function."""
        # File backend
        file_store = create_store("file", store_path=str(self.json_path))
        self.assertIsInstance(file_store, FileStore)

        # SQLite backend
        sqlite_store = create_store("sqlite", db_path=str(self.db_path))
        self.assertIsInstance(sqlite_store, SQLiteStore)

    def test_all_backends_support_required_operations(self):
        """Test that all backends support required operations."""
        session_id = "test-session"
        data = {
            "turns": [{"turn_number": 1, "user_input": "Test"}],
            "state": {"dialog_state": "normal"},
        }

        backends = [
            ("file", FileStore(str(self.json_path))),
            ("sqlite", SQLiteStore(str(self.db_path))),
        ]

        for name, store in backends:
            with self.subTest(backend=name):
                # Write
                store.write_session(session_id, data)
                self.assertTrue(store.exists(session_id))

                # Read
                session = store.read_session(session_id)
                self.assertEqual(len(session["turns"]), 1)

                # List
                sessions = store.list_sessions()
                self.assertEqual(len(sessions), 1)

                # Delete
                deleted = store.delete_session(session_id)
                self.assertTrue(deleted)
                self.assertFalse(store.exists(session_id))


if __name__ == "__main__":
    unittest.main()
