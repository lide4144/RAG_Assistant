from __future__ import annotations

import unittest
from unittest.mock import patch

from app.capability_planner import PlannerResult
from app.kernel_api import KernelChatRequest, KernelChatResponse, SourceItem
from app.planner_shell import run_planner_shell


def _response(trace_id: str = "trace-shell") -> KernelChatResponse:
    return KernelChatResponse(
        traceId=trace_id,
        answer="shell answer [1]",
        sources=[
            SourceItem(
                source_type="local",
                source_id="chunk-1",
                title="Paper A",
                snippet="snippet",
                locator="p.1",
                score=0.9,
            )
        ],
    )


class PlannerShellTests(unittest.TestCase):
    def test_fact_qa_query_uses_primary_route_without_passthrough(self) -> None:
        calls: list[tuple[str, bool, str | None]] = []

        def fact_executor(payload, **kwargs):
            _ = payload
            calls.append((kwargs["selected_path"], kwargs["runtime_fallback"], kwargs["runtime_fallback_reason"]))
            return _response()

        result = run_planner_shell(
            KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-1"),
            fact_qa_executor=fact_executor,
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertEqual(result["response"].traceId, "trace-shell")
        self.assertEqual(calls, [("fact_qa", False, None)])
        self.assertEqual(result["observation"]["selected_path"], "fact_qa")
        self.assertFalse(result["observation"]["planner_shell_passthrough"])
        self.assertEqual(result["observation"]["runtime_contract_version"], "agent-first-v1")
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_calls"]], ["fact_qa"])
        self.assertEqual(result["observation"]["tool_results"][0]["status"], "succeeded")
        self.assertEqual(result["observation"]["tool_results"][0]["metadata"]["trace_id"], "trace-shell")

    def test_summary_query_uses_passthrough_compat_route(self) -> None:
        calls: list[str] = []

        def compat_executor(payload, **kwargs):
            _ = payload
            calls.append(kwargs["selected_path"])
            return _response("compat")

        result = run_planner_shell(
            KernelChatRequest(sessionId="s1", mode="local", query="总结这几篇论文的差异", history=[], traceId="trace-2"),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=compat_executor,
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertEqual(calls, ["summary_passthrough"])
        self.assertEqual(result["response"].traceId, "compat")
        self.assertTrue(result["observation"]["planner_shell_passthrough"])
        self.assertEqual(result["observation"]["selected_path"], "summary_passthrough")
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_calls"]], ["cross_doc_summary"])

    def test_paper_assistant_query_maps_to_runtime_tool_contract(self) -> None:
        calls: list[str] = []

        def compat_executor(payload, **kwargs):
            _ = payload
            calls.append(kwargs["selected_path"])
            return _response("assistant")

        result = run_planner_shell(
            KernelChatRequest(
                sessionId="s1",
                mode="local",
                query="帮我分析 Transformer 压缩方向的论文并给出下一步研究建议",
                history=[],
                traceId="trace-2a",
            ),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=compat_executor,
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertEqual(calls, ["summary_passthrough"])
        self.assertEqual(result["response"].traceId, "assistant")
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_calls"]], ["paper_assistant"])

    def test_runtime_clarifies_research_assistant_when_scope_is_missing(self) -> None:
        result = run_planner_shell(
            KernelChatRequest(sessionId="s1", mode="local", query="帮我比较这些论文并给出下一步研究建议", history=[], traceId="trace-clarify"),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertEqual(result["observation"]["selected_path"], "planner_runtime_clarify")
        self.assertTrue(result["observation"]["short_circuit"]["triggered"])
        self.assertEqual(result["observation"]["short_circuit"]["reason"], "paper_assistant_missing_prerequisites")
        self.assertIn("请先说明", result["response"].answer)
        self.assertEqual(result["observation"]["tool_results"][0]["status"], "clarify_required")

    def test_unsupported_tool_sets_planner_fallback_observation(self) -> None:
        planner_result = PlannerResult(
            planner_used=True,
            planner_source="rule_based",
            planner_fallback=False,
            planner_fallback_reason=None,
            planner_confidence=0.8,
            is_new_topic=False,
            should_clear_pending_clarify=False,
            relation_to_previous="same_topic_or_no_pending",
            standalone_query="q",
            primary_capability="unknown_tool",
            strictness="summary",
            action_plan=[{"action": "unknown_tool", "query": "q"}],
        )

        with patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-unsupported"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertTrue(result["observation"]["planner_shell_fallback"])
        self.assertEqual(result["observation"]["planner_shell_fallback_reason"], "unsupported_tool:unknown_tool")
        self.assertEqual(result["observation"]["tool_results"][0]["status"], "failed")
        self.assertEqual(result["observation"]["tool_results"][0]["error"]["code"], "unsupported_tool")

    def test_missing_dependencies_sets_tool_fallback_observation(self) -> None:
        planner_result = PlannerResult(
            planner_used=True,
            planner_source="rule_based",
            planner_fallback=False,
            planner_fallback_reason=None,
            planner_confidence=0.8,
            is_new_topic=False,
            should_clear_pending_clarify=False,
            relation_to_previous="same_topic_or_no_pending",
            standalone_query="q",
            primary_capability="cross_doc_summary",
            strictness="summary",
            action_plan=[{"action": "cross_doc_summary", "query": "q", "depends_on": ["paper_set"]}],
        )

        with patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-missing-dep"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertTrue(result["observation"]["tool_fallback"])
        self.assertEqual(result["observation"]["tool_fallback_reason"], "missing_dependencies:paper_set")
        self.assertEqual(result["observation"]["failed_tool"], "cross_doc_summary")
        self.assertEqual(result["observation"]["tool_results"][0]["error"]["code"], "missing_dependencies")

    def test_action_plan_step_limit_exceeded_sets_planner_fallback_observation(self) -> None:
        planner_result = PlannerResult(
            planner_used=True,
            planner_source="rule_based",
            planner_fallback=False,
            planner_fallback_reason=None,
            planner_confidence=0.8,
            is_new_topic=False,
            should_clear_pending_clarify=False,
            relation_to_previous="same_topic_or_no_pending",
            standalone_query="q",
            primary_capability="cross_doc_summary",
            strictness="summary",
            action_plan=[
                {"action": "catalog_lookup", "query": "q", "produces": "paper_set"},
                {"action": "cross_doc_summary", "query": "q", "depends_on": ["paper_set"]},
                {"action": "control", "query": "q"},
                {"action": "fact_qa", "query": "q"},
            ],
        )

        with patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-step-limit"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertTrue(result["observation"]["planner_shell_fallback"])
        self.assertEqual(result["observation"]["planner_shell_fallback_reason"], "action_plan_step_limit_exceeded")
        self.assertEqual(result["observation"]["selected_path"], "legacy_fallback")

    def test_executor_failure_falls_back_to_legacy_path(self) -> None:
        legacy_calls: list[tuple[str, bool]] = []

        def failing_fact_executor(payload, **kwargs):
            _ = (payload, kwargs)
            raise RuntimeError("boom")

        def legacy_executor(payload, **kwargs):
            _ = payload
            legacy_calls.append((kwargs["selected_path"], kwargs["runtime_fallback"]))
            return _response("legacy")

        result = run_planner_shell(
            KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的年份是多少", history=[], traceId="trace-3"),
            fact_qa_executor=failing_fact_executor,
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=legacy_executor,
        )

        self.assertEqual(legacy_calls, [("legacy_fallback", True)])
        self.assertEqual(result["response"].traceId, "legacy")
        self.assertEqual(result["observation"]["selected_path"], "legacy_fallback")
        self.assertTrue(result["observation"]["planner_shell_fallback"])


if __name__ == "__main__":
    unittest.main()
