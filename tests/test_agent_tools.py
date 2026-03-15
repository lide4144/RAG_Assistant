from __future__ import annotations

import unittest

from app.agent_tools import (
    ToolRegistryEntry,
    build_tool_call_envelope,
    build_tool_failure,
    build_tool_result_envelope,
    validate_tool_call_envelope,
    validate_tool_registry_entry,
)


class AgentToolsContractTests(unittest.TestCase):
    def test_registry_entry_rejects_invalid_streaming_and_failure_type(self) -> None:
        entry = ToolRegistryEntry(
            tool_name="bad_tool",
            capability_family="qa",
            version="v1",
            planner_visible=True,
            kind="tool",
            route="fact_qa",
            passthrough=False,
            streaming_mode="bad-mode",  # type: ignore[arg-type]
            evidence_policy="citation_required",
            failure_types=("invalid_input", "not_real"),  # type: ignore[arg-type]
        )

        errors = validate_tool_registry_entry(entry)

        self.assertTrue(any("invalid streaming_mode" in err for err in errors))
        self.assertTrue(any("invalid failure_types" in err for err in errors))

    def test_call_envelope_must_match_registered_streaming_mode(self) -> None:
        entry = ToolRegistryEntry(
            tool_name="fact_qa",
            capability_family="qa",
            version="v1",
            planner_visible=True,
            kind="tool",
            route="fact_qa",
            passthrough=False,
            streaming_mode="text_stream",
            evidence_policy="citation_required",
            failure_types=("invalid_input", "execution_error"),
        )
        envelope = build_tool_call_envelope(
            entry,
            call_id="tool-1",
            query="q",
            arguments={"query": "q"},
            execution_mode="final_only",
        )

        errors = validate_tool_call_envelope(envelope, {"fact_qa": entry})

        self.assertEqual(errors, ["fact_qa: execution_mode does not match registry streaming_mode"])

    def test_result_envelope_keeps_failure_and_backward_compatible_aliases(self) -> None:
        tool_call = {
            "id": "tool-1",
            "call_id": "tool-1",
            "tool_name": "catalog_lookup",
            "produces": ["paper_set"],
        }
        failure = build_tool_failure("empty_result", message="no papers found", stop_plan=True)

        envelope = build_tool_result_envelope(
            tool_call,
            status="failed",
            output={"selected_path": "catalog_passthrough"},
            artifacts=[{"artifact_name": "paper_set", "available": False}],
            sources=[{"source_id": "catalog_lookup", "provenance_type": "metadata"}],
            observability={"selected_path": "catalog_passthrough"},
            failure=failure,
        )

        self.assertEqual(envelope["failure"]["failure_type"], "empty_result")
        self.assertEqual(envelope["error"]["code"], "empty_result")
        self.assertEqual(envelope["result"]["selected_path"], "catalog_passthrough")
        self.assertEqual(envelope["artifacts"][0]["artifact_name"], "paper_set")


if __name__ == "__main__":
    unittest.main()
