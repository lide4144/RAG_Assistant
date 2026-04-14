"""Integration tests for soft evidence handling.

Tests the complete flow from sufficiency gate to answer generation.
"""

import sys
import re
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sufficiency import run_sufficiency_gate


class MockConfig:
    """Mock configuration for integration testing."""

    def __init__(self):
        self.sufficiency_gate_enabled = True
        self.sufficiency_semantic_threshold_balanced = 0.25
        self.sufficiency_semantic_threshold_strict = 0.35
        self.sufficiency_semantic_threshold_explore = 0.15
        self.sufficiency_semantic_policy = "balanced"
        self.answer_use_llm = False  # Disable LLM for testing
        self.llm_fallback_enabled = True


def test_low_confidence_response_structure():
    """Test that low confidence mode returns correct response structure."""
    config = MockConfig()

    # Single evidence
    evidence = [
        {
            "evidence": [
                {
                    "chunk_id": "chunk_001",
                    "content_type": "body",
                    "quote": "Deep learning is a subset of machine learning.",
                }
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

    # Check response structure
    assert "decision" in result
    assert "answer_mode" in result
    assert "allows_model_knowledge" in result
    assert "confidence_level" in result
    assert "evidence_count" in result
    assert "reason" in result
    assert "reason_code" in result
    assert "severity" in result

    # Check values
    assert result["decision"] == "answer"
    assert result["answer_mode"] == "low_confidence_with_model_knowledge"
    assert result["allows_model_knowledge"] is True
    assert result["confidence_level"] == "low"
    assert result["evidence_count"] == 1
    assert result["severity"] == "warning"
    assert "请谨慎参考" in result["reason"]

    print("✓ Low confidence response structure test passed")


def test_evidence_only_response_structure():
    """Test that normal mode returns correct response structure."""
    config = MockConfig()

    # Multiple evidence
    evidence = [
        {
            "evidence": [
                {
                    "chunk_id": "chunk_001",
                    "content_type": "body",
                    "quote": "Deep learning is a subset of machine learning.",
                },
                {
                    "chunk_id": "chunk_002",
                    "content_type": "body",
                    "quote": "Neural networks are the foundation of deep learning.",
                },
            ]
        }
    ]

    result = run_sufficiency_gate(
        question="What is deep learning?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    # Check evidence count is correct
    assert result["evidence_count"] == 2

    # With 2+ evidence, judge is called which may fail without API config
    # If judge works, check the expected values
    if result["decision"] == "answer":
        assert result["answer_mode"] == "evidence_only"
        assert result["confidence_level"] == "medium"
    else:
        # Judge failed - expected without proper API config
        assert result["reason_code"] in [
            "judge_system_error",
            "traceable_evidence_missing",
        ]

    print("✓ Evidence only response structure test passed")


def test_backward_compatibility():
    """Test that existing code can handle new fields gracefully."""
    config = MockConfig()
    evidence = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test"}]}
    ]

    result = run_sufficiency_gate(
        question="Test question?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    # Old code should be able to access these fields without error
    decision = result.get("decision")
    reason = result.get("reason")
    reason_code = result.get("reason_code")

    # New fields should exist
    answer_mode = result.get("answer_mode")
    allows_model_knowledge = result.get("allows_model_knowledge")
    confidence_level = result.get("confidence_level")

    assert decision is not None
    assert reason is not None
    assert answer_mode is not None
    assert allows_model_knowledge is not None
    assert confidence_level is not None

    print("✓ Backward compatibility test passed")


def test_constraints_envelope_structure():
    """Test that constraints envelope has correct structure for low confidence mode."""
    config = MockConfig()
    evidence = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test"}]}
    ]

    result = run_sufficiency_gate(
        question="What is X?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    envelope = result.get("constraints_envelope")
    assert envelope is not None
    assert envelope.get("constraint_type") == "partial_answer"
    assert envelope.get("reason_code") == "insufficient_evidence_allow_model_knowledge"
    assert envelope.get("severity") == "warning"
    assert envelope.get("allows_partial_answer") is True
    assert "suggested_next_actions" in envelope
    assert len(envelope.get("suggested_next_actions", [])) > 0

    print("✓ Constraints envelope structure test passed")


def test_evidence_count_accuracy():
    """Test that evidence count is accurate for various scenarios."""
    config = MockConfig()

    # Test cases with different evidence counts
    test_cases = [
        ([], 0, "refuse"),
        (
            [
                {
                    "evidence": [
                        {"chunk_id": "c1", "content_type": "body", "quote": "test"}
                    ]
                }
            ],
            1,
            "answer",
        ),
        (
            [
                {
                    "evidence": [
                        {"chunk_id": "c1", "content_type": "body", "quote": "test1"},
                        {"chunk_id": "c2", "content_type": "body", "quote": "test2"},
                    ]
                }
            ],
            2,
            "answer",
        ),
        (
            [
                {
                    "evidence": [
                        {"chunk_id": "c1", "content_type": "body", "quote": "test1"}
                    ]
                },
                {
                    "evidence": [
                        {"chunk_id": "c2", "content_type": "body", "quote": "test2"}
                    ]
                },
            ],
            2,
            "answer",
        ),
    ]

    for evidence, expected_count, expected_decision in test_cases:
        result = run_sufficiency_gate(
            question="Test?",
            scope_mode="open",
            evidence_grouped=evidence,
            config=config,
        )

        actual_count = result.get("evidence_count", 0)
        actual_decision = result.get("decision")

        assert actual_count == expected_count, (
            f"Expected evidence_count={expected_count}, got {actual_count}"
        )
        # For 0 or 1 evidence, we expect specific decisions
        # For 2+ evidence, judge is called which may fail without API
        if expected_count <= 1:
            assert actual_decision == expected_decision, (
                f"Expected decision={expected_decision}, got {actual_decision}"
            )
        # For 2+ evidence, we accept either answer (judge works) or refuse (judge fails)

    print("✓ Evidence count accuracy test passed")


def test_confidence_level_mapping():
    """Test that confidence levels map correctly to evidence counts."""
    config = MockConfig()

    test_cases = [
        # (evidence_count, expected_confidence_level)
        (1, "low"),
        (2, "medium"),
        (3, "high"),
        (5, "high"),
        (10, "high"),
    ]

    for count, expected_level in test_cases:
        evidence = [
            {
                "evidence": [
                    {"chunk_id": f"c{i}", "content_type": "body", "quote": f"test{i}"}
                    for i in range(count)
                ]
            }
        ]

        result = run_sufficiency_gate(
            question="Test?",
            scope_mode="open",
            evidence_grouped=evidence,
            config=config,
        )

        actual_level = result.get("confidence_level")
        # For count=1, we expect low confidence (low confidence mode)
        # For count>=2, judge is called which may fail, but initial confidence_level should still be set
        if count == 1 or result["decision"] == "answer":
            assert actual_level == expected_level, (
                f"For {count} evidence, expected {expected_level}, got {actual_level}"
            )

    print("✓ Confidence level mapping test passed")


def test_triggered_rules():
    """Test that appropriate rules are triggered."""
    config = MockConfig()

    # Single evidence should trigger insufficient_evidence_allow_model_knowledge
    evidence = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test"}]}
    ]
    result = run_sufficiency_gate(
        question="Test?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    triggered = result.get("triggered_rules", [])
    assert "insufficient_evidence_allow_model_knowledge" in triggered

    # Zero evidence should trigger insufficient_evidence_count_or_quality
    result = run_sufficiency_gate(
        question="Test?",
        scope_mode="open",
        evidence_grouped=[],
        config=config,
    )

    triggered = result.get("triggered_rules", [])
    assert "insufficient_evidence_count_or_quality" in triggered

    print("✓ Triggered rules test passed")


def test_output_warnings():
    """Test that appropriate warnings are added to output."""
    config = MockConfig()

    evidence = [
        {"evidence": [{"chunk_id": "c1", "content_type": "body", "quote": "test"}]}
    ]
    result = run_sufficiency_gate(
        question="Test?",
        scope_mode="open",
        evidence_grouped=evidence,
        config=config,
    )

    warnings = result.get("output_warnings", [])
    assert "insufficient_evidence_allow_model_knowledge" in warnings

    print("✓ Output warnings test passed")


if __name__ == "__main__":
    print("\n=== Testing Soft Evidence Integration ===\n")

    test_low_confidence_response_structure()
    test_evidence_only_response_structure()
    test_backward_compatibility()
    test_constraints_envelope_structure()
    test_evidence_count_accuracy()
    test_confidence_level_mapping()
    test_triggered_rules()
    test_output_warnings()

    print("\n✅ All soft evidence integration tests passed!")
