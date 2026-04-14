"""Tests for user honesty preferences (soft evidence handling).

Tests the user preference storage and retrieval for low confidence warnings.
"""

import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.session_state import (
    load_user_honesty_preferences,
    save_user_honesty_preference,
    _read_store,
    _write_store,
)


def test_load_default_preferences():
    """Test loading preferences for a new session returns defaults."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        session_id = "test_session_new"
        result = load_user_honesty_preferences(
            session_id,
            store_path=store_path,
        )

        assert result["hide_low_confidence_warnings"] is False
        assert result["acknowledged_at"] is None
        assert result["acknowledgment_count"] == 0

        print("✓ Default preferences test passed")
    finally:
        Path(store_path).unlink(missing_ok=True)


def test_save_and_load_preferences():
    """Test saving and loading preferences."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        session_id = "test_session_save"

        # Save preference
        save_user_honesty_preference(
            session_id,
            hide_warnings=True,
            store_path=store_path,
        )

        # Load and verify
        result = load_user_honesty_preferences(
            session_id,
            store_path=store_path,
        )

        assert result["hide_low_confidence_warnings"] is True
        assert result["acknowledged_at"] is not None
        assert result["acknowledgment_count"] == 1

        # Save again and check count increments
        save_user_honesty_preference(
            session_id,
            hide_warnings=True,
            store_path=store_path,
        )

        result = load_user_honesty_preferences(
            session_id,
            store_path=store_path,
        )

        assert result["acknowledgment_count"] == 2

        print("✓ Save and load preferences test passed")
    finally:
        Path(store_path).unlink(missing_ok=True)


def test_preference_expiration():
    """Test that preferences expire after max_age_hours."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        session_id = "test_session_expire"

        # Create session with old acknowledged_at
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        store_data = {
            "sessions": {
                session_id: {
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
                            "hide_low_confidence_warnings": True,
                            "acknowledged_at": old_time,
                            "acknowledgment_count": 5,
                        },
                    },
                }
            }
        }
        _write_store(store_path, store_data)

        # Load with default max_age (24 hours) - should reset
        result = load_user_honesty_preferences(
            session_id,
            store_path=store_path,
            max_age_hours=24,
        )

        # Should be reset due to expiration
        assert result["hide_low_confidence_warnings"] is False
        assert result["acknowledged_at"] is None
        assert result["acknowledgment_count"] == 0

        print("✓ Preference expiration test passed")
    finally:
        Path(store_path).unlink(missing_ok=True)


def test_preference_not_expired():
    """Test that preferences within max_age are preserved."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        session_id = "test_session_not_expire"

        # Create session with recent acknowledged_at
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        store_data = {
            "sessions": {
                session_id: {
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
                            "hide_low_confidence_warnings": True,
                            "acknowledged_at": recent_time,
                            "acknowledgment_count": 3,
                        },
                    },
                }
            }
        }
        _write_store(store_path, store_data)

        # Load with max_age 24 hours - should preserve
        result = load_user_honesty_preferences(
            session_id,
            store_path=store_path,
            max_age_hours=24,
        )

        # Should be preserved
        assert result["hide_low_confidence_warnings"] is True
        assert result["acknowledged_at"] == recent_time
        assert result["acknowledgment_count"] == 3

        print("✓ Preference not expired test passed")
    finally:
        Path(store_path).unlink(missing_ok=True)


def test_preference_disabled_expiration():
    """Test that max_age_hours=0 disables expiration."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        session_id = "test_session_no_expire"

        # Create session with very old acknowledged_at
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        store_data = {
            "sessions": {
                session_id: {
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
                            "hide_low_confidence_warnings": True,
                            "acknowledged_at": old_time,
                            "acknowledgment_count": 10,
                        },
                    },
                }
            }
        }
        _write_store(store_path, store_data)

        # Load with max_age=0 - should not expire
        result = load_user_honesty_preferences(
            session_id,
            store_path=store_path,
            max_age_hours=0,  # Disabled
        )

        # Should be preserved even though very old
        assert result["hide_low_confidence_warnings"] is True
        assert result["acknowledged_at"] == old_time
        assert result["acknowledgment_count"] == 10

        print("✓ Preference disabled expiration test passed")
    finally:
        Path(store_path).unlink(missing_ok=True)


def test_session_isolation():
    """Test that preferences are isolated per session."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        session_1 = "test_session_1"
        session_2 = "test_session_2"

        # Set preference for session 1
        save_user_honesty_preference(
            session_1,
            hide_warnings=True,
            store_path=store_path,
        )

        # Session 2 should have defaults
        result_2 = load_user_honesty_preferences(
            session_2,
            store_path=store_path,
        )

        assert result_2["hide_low_confidence_warnings"] is False
        assert result_2["acknowledged_at"] is None
        assert result_2["acknowledgment_count"] == 0

        # Session 1 should still have saved preference
        result_1 = load_user_honesty_preferences(
            session_1,
            store_path=store_path,
        )

        assert result_1["hide_low_confidence_warnings"] is True
        assert result_1["acknowledgment_count"] == 1

        print("✓ Session isolation test passed")
    finally:
        Path(store_path).unlink(missing_ok=True)


if __name__ == "__main__":
    print("\n=== Testing User Honesty Preferences ===\n")

    test_load_default_preferences()
    test_save_and_load_preferences()
    test_preference_expiration()
    test_preference_not_expired()
    test_preference_disabled_expiration()
    test_session_isolation()

    print("\n✅ All user honesty preferences tests passed!")
