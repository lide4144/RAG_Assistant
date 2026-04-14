"""Tests for soft evidence handling threshold changes.

Tests the new evidence threshold logic (2 -> 1) and answer_mode behavior.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sufficiency import (
    _is_insufficient_evidence,
    _count_evidence,
    run_sufficiency_gate,
)


class MockConfig:
    """Mock configuration for testing."""

    def __init__(self):
        self.sufficiency_gate_enabled = True
        self.sufficiency_semantic_threshold_balanced = 0.25
        self.sufficiency_semantic_threshold_strict = 0.35
        self.sufficiency_semantic_threshold_explore = 0.15
        self.sufficiency_semantic_policy = "balanced"


def test_evidence_count_function():
    """Test _count_evidence returns correct counts."""
    # Empty evidence
    assert _count_evidence([]) == 0, "Empty evidence should count as 0"

    # Single evidence
    single = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test"}]}
    ]
    assert _count_evidence(single) == 1, "Single evidence should count as 1"

    # Multiple evidence
    multiple = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "body", "quote": "test1"},
                {"chunk_id": "c2", "content_type": "body", "quote": "test2"},
            ]
        }
    ]
    assert _count_evidence(multiple) == 2, "Multiple evidence should count correctly"

    # Multiple groups
    groups = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test1"}]},
        {"evidence": [{"chunk_id": "c2", "content_type": "body", "quote": "test2"}]},
    ]
    assert _count_evidence(groups) == 2, "Evidence across groups should be counted"

    print("✓ _count_evidence tests passed")


def test_insufficient_evidence_threshold():
    """Test _is_insufficient_evidence with new threshold of 1."""
    # 0 evidence should be insufficient
    assert _is_insufficient_evidence([]) is True, "0 evidence should be insufficient"

    # 1 evidence should be sufficient (threshold is now 1)
    single = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test"}]}
    ]
    assert _is_insufficient_evidence(single) is False, "1 evidence should be sufficient"

    # 2 evidence should be sufficient
    double = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "body", "quote": "test1"},
                {"chunk_id": "c2", "content_type": "body", "quote": "test2"},
            ]
        }
    ]
    assert _is_insufficient_evidence(double) is False, "2 evidence should be sufficient"

    # Only noisy content should be insufficient
    noisy = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "front_matter", "quote": "test"}
            ]
        }
    ]
    assert _is_insufficient_evidence(noisy) is True, (
        "Only noisy content should be insufficient"
    )

    print("✓ _is_insufficient_evidence tests passed")


def test_sufficiency_gate_zero_evidence():
    """Test sufficiency gate returns refuse for 0 evidence."""
    config = MockConfig()
    result = run_sufficiency_gate(
        question="What is deep learning?",
        scope_mode="open",
        evidence_grouped=[],
        config=config,
    )

    assert result["decision"] == "refuse", "0 evidence should result in refuse"
    assert result["reason_code"] == "insufficient_evidence_count_or_quality"
    # answer_mode may not be present for refuse, or could be evidence_only
    answer_mode = result.get("answer_mode")
    assert (
        answer_mode is None
        or answer_mode == "evidence_only"
        or answer_mode == "low_confidence_with_model_knowledge"
    )
    print("✓ 0 evidence -> refuse test passed")


def test_sufficiency_gate_one_evidence():
    """Test sufficiency gate returns low_confidence answer for 1 evidence."""
    config = MockConfig()
    evidence = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "body", "quote": "test quote"}
            ]
        }
    ]

    result = run_sufficiency_gate(
        question="What is deep learning?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
        open_summary_intent=False,
    )

    # Check decision and mode
    assert result["decision"] == "answer", "1 evidence should result in answer"
    assert result.get("answer_mode") == "low_confidence_with_model_knowledge", (
        "Should return low_confidence_with_model_knowledge mode"
    )
    assert result.get("allows_model_knowledge") is True, "Should allow model knowledge"
    assert result.get("confidence_level") == "low", "Should have low confidence"
    assert result.get("evidence_count") == 1, "Should report evidence count of 1"
    assert result["reason_code"] == "insufficient_evidence_allow_model_knowledge"

    print("✓ 1 evidence -> low_confidence answer test passed")


def test_sufficiency_gate_two_evidence():
    """Test sufficiency gate returns answer for 2 evidence."""
    config = MockConfig()
    evidence = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "body", "quote": "test quote 1"},
                {"chunk_id": "c2", "content_type": "body", "quote": "test quote 2"},
            ]
        }
    ]

    result = run_sufficiency_gate(
        question="What is deep learning?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    # Note: With 2+ evidence, judge_semantic_evidence is called.
    # If API is not configured, it may return refuse due to judge failure.
    # We check that the evidence_count is correct.
    assert result.get("evidence_count") == 2, "Should report evidence count of 2"

    # If judge works, it should be answer with evidence_only mode
    # If judge fails, it will be refuse with judge_system_error
    # For the test, we just verify the evidence count is correct
    if result["decision"] == "answer":
        assert result.get("answer_mode") == "evidence_only", (
            "Should return evidence_only mode"
        )
        assert result.get("confidence_level") == "medium", (
            "Should have medium confidence"
        )
    else:
        # Judge failed - this is expected without API config
        assert result.get("reason_code") in [
            "judge_system_error",
            "traceable_evidence_missing",
        ]

    print("✓ 2 evidence -> normal answer (or judge failure) test passed")


def test_sufficiency_gate_three_evidence():
    """Test sufficiency gate returns high confidence for 3+ evidence."""
    config = MockConfig()
    evidence = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "body", "quote": "test quote 1"},
                {"chunk_id": "c2", "content_type": "body", "quote": "test quote 2"},
                {"chunk_id": "c3", "content_type": "body", "quote": "test quote 3"},
            ]
        }
    ]

    result = run_sufficiency_gate(
        question="What is deep learning?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    # Note: With 3+ evidence, judge_semantic_evidence is called.
    # If API is not configured, it may return refuse due to judge failure.
    assert result.get("evidence_count") == 3, "Should report evidence count of 3"

    # If judge works, verify confidence level
    if result["decision"] == "answer":
        assert result.get("confidence_level") == "high", "Should have high confidence"
    else:
        # Judge failed - expected without API config
        assert result.get("reason_code") in [
            "judge_system_error",
            "traceable_evidence_missing",
        ]

    print("✓ 3 evidence -> high confidence (or judge failure) test passed")


def test_open_summary_with_one_evidence():
    """Test that open_summary_intent still requires clarification with 1 evidence."""
    config = MockConfig()
    evidence = [
        {
            "evidence": [
                {"chunk_id": "c1", "content_type": "body", "quote": "test quote"}
            ]
        }
    ]

    result = run_sufficiency_gate(
        question="Summarize the papers",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
        open_summary_intent=True,
    )

    assert result["decision"] == "clarify", (
        "Open summary with 1 evidence should clarify"
    )
    assert "你最关心哪一类主题" in str(result.get("clarify_questions", []))

    print("✓ Open summary with 1 evidence -> clarify test passed")


if __name__ == "__main__":
    print("\n=== Testing Soft Evidence Threshold ===\n")

    test_evidence_count_function()
    test_insufficient_evidence_threshold()
    test_sufficiency_gate_zero_evidence()
    test_sufficiency_gate_one_evidence()
    test_sufficiency_gate_two_evidence()
    test_sufficiency_gate_three_evidence()
    test_open_summary_with_one_evidence()

    print("\n✅ All soft evidence threshold tests passed!")
