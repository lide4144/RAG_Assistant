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
    def _planner_result(self, **overrides) -> PlannerResult:
        payload = {
            "decision_version": "planner-policy-v1",
            "user_goal": "q",
            "planner_used": True,
            "planner_source": "rule",
            "planner_fallback": False,
            "planner_fallback_reason": None,
            "planner_confidence": 0.8,
            "is_new_topic": False,
            "should_clear_pending_clarify": False,
            "relation_to_previous": "same_topic_or_no_pending",
            "standalone_query": "q",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "selected_tools_or_skills": ["fact_qa"],
            "fallback": {"type": None, "reason": None},
            "clarify_question": None,
            "action_plan": [{"action": "fact_qa", "query": "q"}],
        }
        payload.update(overrides)
        return PlannerResult(**payload)

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
        self.assertEqual(result["observation"]["planner"]["decision_result"], "local_execute")
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_calls"]], ["fact_qa"])
        self.assertEqual(result["observation"]["tool_results"][0]["status"], "succeeded")
        self.assertEqual(result["observation"]["tool_results"][0]["metadata"]["trace_id"], "trace-shell")
        self.assertEqual(result["observation"]["tool_calls"][0]["call_id"], "tool-1")
        self.assertEqual(result["observation"]["tool_calls"][0]["streaming_mode"], "text_stream")
        self.assertEqual(result["observation"]["tool_calls"][0]["evidence_policy"], "citation_required")
        self.assertTrue(any(row["tool_name"] == "title_term_localization" for row in result["observation"]["tool_registry_entries"]))

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
        self.assertEqual(result["observation"]["planner"]["decision_result"], "local_execute")
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

        self.assertEqual(calls, ["research_assistant_passthrough"])
        self.assertEqual(result["response"].traceId, "assistant")
        self.assertEqual(result["observation"]["planner"]["decision_result"], "delegate_research_assistant")
        self.assertEqual(result["observation"]["selected_path"], "research_assistant_passthrough")
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_calls"]], ["paper_assistant"])
        self.assertTrue(any(row["provenance_type"] == "explanatory" for row in result["observation"]["tool_results"][0]["sources"]))

    def test_planner_clarify_route_sets_clarification_decision(self) -> None:
        result = run_planner_shell(
            KernelChatRequest(sessionId="s1", mode="local", query="帮我比较这些论文并给出下一步研究建议", history=[], traceId="trace-clarify"),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertEqual(result["observation"]["selected_path"], "planner_runtime_clarify")
        self.assertEqual(result["observation"]["planner"]["decision_result"], "clarify")
        self.assertTrue(result["observation"]["planner"]["requires_clarification"])
        self.assertFalse(result["observation"]["short_circuit"]["triggered"])
        self.assertIn("请先说明", result["response"].answer)
        self.assertEqual(result["response"].answer.count("\n1."), 1)

    def test_runtime_still_short_circuits_invalid_research_assistant_plan(self) -> None:
        planner_result = self._planner_result(
            user_goal="帮我比较这些论文并给出下一步研究建议",
            standalone_query="帮我比较这些论文并给出下一步研究建议",
            primary_capability="paper_assistant",
            strictness="summary",
            decision_result="delegate_research_assistant",
            research_mode="paper_assistant",
            selected_tools_or_skills=["paper_assistant"],
            action_plan=[
                {
                    "action": "paper_assistant",
                    "query": "帮我比较这些论文并给出下一步研究建议",
                    "params": {"style": "research_assistant"},
                }
            ],
        )

        with patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="帮我比较这些论文并给出下一步研究建议", history=[], traceId="trace-clarify-runtime"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["observation"]["selected_path"], "planner_runtime_clarify")
        self.assertTrue(result["observation"]["short_circuit"]["triggered"])
        self.assertEqual(result["observation"]["short_circuit"]["reason"], "paper_assistant_missing_prerequisites")
        self.assertEqual(result["observation"]["tool_results"][0]["status"], "clarify_required")

    def test_planner_input_context_includes_session_conversation_state(self) -> None:
        planner_result = self._planner_result()

        with (
            patch(
                "app.planner_runtime.load_planner_conversation_state",
                return_value={
                    "recent_topic_anchors": ["Transformer", "压缩"],
                    "pending_clarify": {
                        "original_question": "这篇论文准确率是多少",
                        "clarify_question": "请补充具体论文。",
                    },
                    "previous_planner": {
                        "decision_result": "local_execute",
                        "primary_capability": "fact_qa",
                        "strictness": "strict_fact",
                        "selected_tools_or_skills": ["fact_qa"],
                    },
                },
            ),
            patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result) as mocked_planner,
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文作者是谁", history=[], traceId="trace-context"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        planner_kwargs = mocked_planner.call_args.kwargs
        self.assertEqual(planner_kwargs["history_topic_anchors"], ["Transformer", "压缩"])
        self.assertEqual(planner_kwargs["pending_clarify"]["clarify_question"], "请补充具体论文。")
        conversation_context = result["observation"]["planner_input_context"]["conversation_context"]
        self.assertEqual(conversation_context["recent_topic_anchors"], ["Transformer", "压缩"])
        self.assertEqual(conversation_context["previous_planner"]["primary_capability"], "fact_qa")

    def test_unsupported_tool_sets_planner_fallback_observation(self) -> None:
        planner_result = self._planner_result(
            primary_capability="unknown_tool",
            strictness="summary",
            selected_tools_or_skills=["unknown_tool"],
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
        planner_result = self._planner_result(
            primary_capability="cross_doc_summary",
            strictness="summary",
            selected_tools_or_skills=["cross_doc_summary"],
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
        planner_result = self._planner_result(
            primary_capability="cross_doc_summary",
            strictness="summary",
            selected_tools_or_skills=["catalog_lookup", "cross_doc_summary", "control", "fact_qa"],
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

    def test_multi_step_plan_executes_catalog_then_summary(self) -> None:
        planner_result = self._planner_result(
            primary_capability="cross_doc_summary",
            strictness="summary",
            selected_tools_or_skills=["catalog_lookup", "cross_doc_summary"],
            action_plan=[
                {"action": "catalog_lookup", "query": "总结这些 Transformer 论文", "produces": "paper_set"},
                {"action": "cross_doc_summary", "query": "总结这些 Transformer 论文", "depends_on": ["paper_set"]},
            ],
        )
        compat_calls: list[dict[str, object]] = []

        def compat_executor(payload, **kwargs):
            _ = payload
            compat_calls.append(
                {
                    "selected_path": kwargs["selected_path"],
                    "tool_names": [row["tool_name"] for row in kwargs["tool_calls"]],
                    "prior_tool_results": len(kwargs["prior_tool_results"]),
                    "available_artifacts": dict(kwargs["available_artifacts"]),
                    "record_runtime_observation": kwargs["record_runtime_observation"],
                }
            )
            return _response("summary")

        with (
            patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result),
            patch(
                "app.planner_runtime.execute_catalog_lookup",
                return_value={
                    "state": "ready",
                    "matched_count": 2,
                    "selected_count": 2,
                    "truncated": False,
                    "paper_set": [{"paper_id": "p1", "title": "Paper 1"}],
                    "short_circuit": False,
                    "short_circuit_reason": None,
                },
            ),
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="总结这些 Transformer 论文", history=[], traceId="trace-multi"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=compat_executor,
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["response"].traceId, "summary")
        self.assertEqual(result["observation"]["selected_path"], "summary_passthrough")
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_calls"]], ["catalog_lookup", "cross_doc_summary"])
        self.assertEqual([row["tool_name"] for row in result["observation"]["tool_results"]], ["catalog_lookup", "cross_doc_summary"])
        self.assertEqual(result["observation"]["tool_results"][0]["artifacts"][0]["artifact_name"], "paper_set")
        self.assertEqual(compat_calls, [
            {
                "selected_path": "summary_passthrough",
                "tool_names": ["catalog_lookup", "cross_doc_summary"],
                "prior_tool_results": 1,
                "available_artifacts": {"paper_set": [{"paper_id": "p1", "title": "Paper 1"}]},
                "record_runtime_observation": True,
            }
        ])

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

    def test_delegate_web_route_uses_web_delegate_selected_path(self) -> None:
        planner_result = self._planner_result(
            user_goal="请联网查看最近的 RAG 综述",
            standalone_query="请联网查看最近的 RAG 综述",
            primary_capability="web_research",
            strictness="summary",
            decision_result="delegate_web",
            knowledge_route="web",
            selected_tools_or_skills=["web_research"],
            action_plan=[],
        )
        calls: list[str] = []

        def legacy_executor(payload, **kwargs):
            _ = payload
            calls.append(kwargs["selected_path"])
            return _response("legacy-web")

        with patch("app.planner_runtime.build_rule_based_plan", return_value=planner_result):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="请联网查看最近的 RAG 综述", history=[], traceId="trace-web"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=legacy_executor,
            )

        self.assertEqual(calls, ["web_delegate_passthrough"])
        self.assertEqual(result["observation"]["selected_path"], "web_delegate_passthrough")
        self.assertEqual(result["observation"]["planner"]["decision_result"], "delegate_web")


if __name__ == "__main__":
    unittest.main()
