from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.capability_planner import PlannerResult
from app.kernel_api import KernelChatRequest, KernelChatResponse, SourceItem
from app.llm_client import LLMCallResult
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
            "planner_source": "llm",
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

    def _llm_decision(self, **overrides) -> dict[str, object]:
        payload: dict[str, object] = {
            "decision_version": "planner-policy-v1",
            "user_goal": "q",
            "planner_used": True,
            "planner_source": "llm",
            "planner_confidence": 0.9,
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
        return payload

    def _llm_decision_from_result(self, result: PlannerResult) -> dict[str, object]:
        return self._llm_decision(
            user_goal=result.user_goal,
            planner_used=result.planner_used,
            planner_confidence=result.planner_confidence,
            is_new_topic=result.is_new_topic,
            should_clear_pending_clarify=result.should_clear_pending_clarify,
            relation_to_previous=result.relation_to_previous,
            standalone_query=result.standalone_query,
            primary_capability=result.primary_capability,
            strictness=result.strictness,
            decision_result=result.decision_result,
            knowledge_route=result.knowledge_route,
            research_mode=result.research_mode,
            requires_clarification=result.requires_clarification,
            selected_tools_or_skills=list(result.selected_tools_or_skills),
            fallback=dict(result.fallback),
            clarify_question=result.clarify_question,
            action_plan=[dict(step) for step in result.action_plan],
        )

    def _run_with_llm_decision(
        self,
        request: KernelChatRequest,
        *,
        llm_decision: dict[str, object],
        fact_qa_executor=None,
        compat_executor=None,
        legacy_executor=None,
    ):
        with patch.dict(
            os.environ,
            {"PLANNER_LLM_DECISION_JSON": json.dumps(llm_decision, ensure_ascii=False)},
            clear=False,
        ):
            return run_planner_shell(
                request,
                fact_qa_executor=fact_qa_executor or (lambda payload, **kwargs: _response()),
                compat_executor=compat_executor or (lambda payload, **kwargs: _response("compat")),
                legacy_executor=legacy_executor or (lambda payload, **kwargs: _response("legacy")),
            )

    def test_fact_qa_query_uses_primary_route_without_passthrough(self) -> None:
        calls: list[tuple[str, bool, str | None]] = []

        def fact_executor(payload, **kwargs):
            _ = payload
            calls.append((kwargs["selected_path"], kwargs["runtime_fallback"], kwargs["runtime_fallback_reason"]))
            return _response()

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-1"),
            llm_decision=self._llm_decision(
                user_goal="这篇论文的作者是谁",
                standalone_query="这篇论文的作者是谁",
                action_plan=[{"action": "fact_qa", "query": "这篇论文的作者是谁"}],
            ),
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

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="总结这几篇论文的差异", history=[], traceId="trace-2"),
            llm_decision=self._llm_decision(
                user_goal="总结这几篇论文的差异",
                standalone_query="总结这几篇论文的差异",
                primary_capability="cross_doc_summary",
                strictness="summary",
                selected_tools_or_skills=["cross_doc_summary"],
                action_plan=[{"action": "cross_doc_summary", "query": "总结这几篇论文的差异"}],
            ),
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

        result = self._run_with_llm_decision(
            KernelChatRequest(
                sessionId="s1",
                mode="local",
                query="帮我分析 Transformer 压缩方向的论文并给出下一步研究建议",
                history=[],
                traceId="trace-2a",
            ),
            llm_decision=self._llm_decision(
                user_goal="帮我分析 Transformer 压缩方向的论文并给出下一步研究建议",
                standalone_query="帮我分析 Transformer 压缩方向的论文并给出下一步研究建议",
                primary_capability="paper_assistant",
                strictness="summary",
                decision_result="delegate_research_assistant",
                research_mode="paper_assistant",
                selected_tools_or_skills=["paper_assistant"],
                action_plan=[
                    {
                        "action": "paper_assistant",
                        "query": "帮我分析 Transformer 压缩方向的论文并给出下一步研究建议",
                        "params": {"style": "research_assistant"},
                    }
                ],
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
        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="帮我比较这些论文并给出下一步研究建议", history=[], traceId="trace-clarify"),
            llm_decision=self._llm_decision(
                user_goal="帮我比较这些论文并给出下一步研究建议",
                standalone_query="帮我比较这些论文并给出下一步研究建议",
                primary_capability="paper_assistant",
                strictness="summary",
                decision_result="clarify",
                requires_clarification=True,
                selected_tools_or_skills=[],
                clarify_question="请先说明你要比较的是哪些论文，或给出论文标题、作者、年份。",
                action_plan=[],
            ),
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

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="帮我比较这些论文并给出下一步研究建议", history=[], traceId="trace-clarify-runtime"),
            llm_decision=self._llm_decision_from_result(planner_result),
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
        ):
            result = self._run_with_llm_decision(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文作者是谁", history=[], traceId="trace-context"),
                llm_decision=self._llm_decision(
                    user_goal="这篇论文作者是谁",
                    standalone_query="这篇论文作者是谁",
                    action_plan=[{"action": "fact_qa", "query": "这篇论文作者是谁"}],
                ),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        conversation_context = result["observation"]["planner_input_context"]["conversation_context"]
        self.assertEqual(conversation_context["recent_topic_anchors"], ["Transformer", "压缩"])
        self.assertEqual(conversation_context["pending_clarify"]["clarify_question"], "请补充具体论文。")
        self.assertEqual(conversation_context["previous_planner"]["primary_capability"], "fact_qa")

    def test_unsupported_tool_rejects_llm_plan_before_execution(self) -> None:
        planner_result = self._planner_result(
            primary_capability="unknown_tool",
            strictness="summary",
            selected_tools_or_skills=["unknown_tool"],
            action_plan=[{"action": "unknown_tool", "query": "q"}],
        )

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-unsupported"),
            llm_decision=self._llm_decision_from_result(planner_result),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertTrue(result["observation"]["planner_shell_fallback"])
        self.assertEqual(result["observation"]["planner_shell_fallback_reason"], "unsupported_tool:unknown_tool")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertEqual(result["observation"]["tool_results"], [])
        self.assertIn("系统暂不支持", result["response"].answer)
        self.assertIn("unknown_tool", result["response"].answer)

    def test_missing_dependencies_rejects_llm_plan_before_tool_dispatch(self) -> None:
        planner_result = self._planner_result(
            primary_capability="cross_doc_summary",
            strictness="summary",
            selected_tools_or_skills=["cross_doc_summary"],
            action_plan=[{"action": "cross_doc_summary", "query": "q", "depends_on": ["paper_set"]}],
        )

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-missing-dep"),
            llm_decision=self._llm_decision_from_result(planner_result),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertFalse(result["observation"]["tool_fallback"])
        self.assertTrue(result["observation"]["planner_shell_fallback"])
        self.assertEqual(result["observation"]["planner_shell_fallback_reason"], "missing_dependencies:paper_set")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("缺少必要的前置结果", result["response"].answer)
        self.assertIn("paper_set", result["response"].answer)

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

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="q", history=[], traceId="trace-step-limit"),
            llm_decision=self._llm_decision_from_result(planner_result),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=lambda payload, **kwargs: _response("legacy"),
        )

        self.assertTrue(result["observation"]["planner_shell_fallback"])
        self.assertEqual(result["observation"]["planner_shell_fallback_reason"], "action_plan_step_limit_exceeded")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertIn("执行步骤过多", result["response"].answer)

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

        with patch(
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
        ):
            result = self._run_with_llm_decision(
                KernelChatRequest(sessionId="s1", mode="local", query="总结这些 Transformer 论文", history=[], traceId="trace-multi"),
                llm_decision=self._llm_decision_from_result(planner_result),
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

    def test_executor_failure_enters_controlled_terminate(self) -> None:
        legacy_calls: list[tuple[str, bool]] = []

        def failing_fact_executor(payload, **kwargs):
            _ = (payload, kwargs)
            raise RuntimeError("boom")

        def legacy_executor(payload, **kwargs):
            _ = payload
            legacy_calls.append((kwargs["selected_path"], kwargs["runtime_fallback"]))
            return _response("legacy")

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的年份是多少", history=[], traceId="trace-3"),
            llm_decision=self._llm_decision(
                user_goal="这篇论文的年份是多少",
                standalone_query="这篇论文的年份是多少",
                action_plan=[{"action": "fact_qa", "query": "这篇论文的年份是多少"}],
            ),
            fact_qa_executor=failing_fact_executor,
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=legacy_executor,
        )

        self.assertEqual(legacy_calls, [])
        self.assertEqual(result["response"].traceId, "trace-3")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
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

        result = self._run_with_llm_decision(
            KernelChatRequest(sessionId="s1", mode="local", query="请联网查看最近的 RAG 综述", history=[], traceId="trace-web"),
            llm_decision=self._llm_decision_from_result(planner_result),
            fact_qa_executor=lambda payload, **kwargs: _response(),
            compat_executor=lambda payload, **kwargs: _response("compat"),
            legacy_executor=legacy_executor,
        )

        self.assertEqual(calls, ["web_delegate_passthrough"])
        self.assertEqual(result["observation"]["selected_path"], "web_delegate_passthrough")
        self.assertEqual(result["observation"]["planner"]["decision_result"], "delegate_web")

    def test_shadow_compare_records_llm_diagnostics_without_changing_primary_answer(self) -> None:
        llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.92,
            "user_goal": "总结这几篇论文的差异",
            "standalone_query": "总结这几篇论文的差异",
            "is_new_topic": False,
            "should_clear_pending_clarify": False,
            "relation_to_previous": "same_topic_or_no_pending",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "clarify_question": None,
            "selected_tools_or_skills": ["fact_qa"],
            "action_plan": [{"action": "fact_qa", "query": "总结这几篇论文的差异"}],
            "fallback": {"type": None, "reason": None},
        }
        with patch.dict(os.environ, {"PLANNER_SOURCE_MODE": "shadow_compare", "PLANNER_LLM_DECISION_JSON": json.dumps(llm_decision)}, clear=False):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="总结这几篇论文的差异", history=[], traceId="trace-shadow"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["response"].traceId, "trace-shell")
        self.assertEqual(result["observation"]["planner_source_mode"], "shadow_compare")
        self.assertEqual(result["observation"]["planner_execution_source"], "llm")
        self.assertIsNotNone(result["observation"]["shadow_compare"])
        self.assertEqual(result["observation"]["shadow_compare"]["actual_execution_source"], "llm")
        self.assertNotIn("rule_decision", result["observation"]["shadow_compare"])
        self.assertNotIn("diff", result["observation"]["shadow_compare"])
        self.assertEqual(result["observation"]["shadow_compare"]["review"]["allowed_labels"], ["accepted", "needs_followup", "incorrect", "blocked"])

    def test_shadow_compare_calls_real_llm_planner_path_when_override_absent(self) -> None:
        llm_payload = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.91,
            "user_goal": "总结这几篇论文的差异",
            "standalone_query": "总结这几篇论文的差异",
            "is_new_topic": False,
            "should_clear_pending_clarify": False,
            "relation_to_previous": "same_topic_or_no_pending",
            "primary_capability": "cross_doc_summary",
            "strictness": "summary",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "clarify_question": None,
            "selected_tools_or_skills": ["cross_doc_summary"],
            "action_plan": [{"action": "cross_doc_summary", "query": "总结这几篇论文的差异"}],
            "fallback": {"type": None, "reason": None},
        }
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=True,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "shadow_compare", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
            patch(
                "app.planner_runtime.call_chat_completion",
                return_value=LLMCallResult(
                    ok=True,
                    content=json.dumps(llm_payload, ensure_ascii=False),
                    reason=None,
                    attempts_used=1,
                    max_retries=0,
                    elapsed_ms=12,
                    provider_used="siliconflow",
                    model_used="planner-model",
                ),
            ) as mocked_llm,
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="总结这几篇论文的差异", history=[], traceId="trace-shadow-real-llm"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(mocked_llm.call_count, 1)
        self.assertEqual(result["observation"]["planner_source_mode"], "shadow_compare")
        self.assertEqual(result["observation"]["planner_execution_source"], "llm")
        self.assertEqual(result["observation"]["planner_llm_diagnostics"]["status"], "ok")
        self.assertEqual(result["observation"]["planner_candidates"]["llm"]["planner_source"], "llm")
        self.assertEqual(result["observation"]["shadow_compare"]["llm_decision"]["primary_capability"], "cross_doc_summary")

    def test_llm_planner_uses_request_config_path(self) -> None:
        llm_payload = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.91,
            "user_goal": "总结这几篇论文的差异",
            "standalone_query": "总结这几篇论文的差异",
            "is_new_topic": False,
            "should_clear_pending_clarify": False,
            "relation_to_previous": "same_topic_or_no_pending",
            "primary_capability": "cross_doc_summary",
            "strictness": "summary",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "clarify_question": None,
            "selected_tools_or_skills": ["cross_doc_summary"],
            "action_plan": [{"action": "cross_doc_summary", "query": "总结这几篇论文的差异"}],
            "fallback": {"type": None, "reason": None},
        }
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=True,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "shadow_compare", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])) as mocked_load_config,
            patch(
                "app.planner_runtime.call_chat_completion",
                return_value=LLMCallResult(
                    ok=True,
                    content=json.dumps(llm_payload, ensure_ascii=False),
                    reason=None,
                    attempts_used=1,
                    max_retries=0,
                    elapsed_ms=12,
                    provider_used="siliconflow",
                    model_used="planner-model",
                ),
            ),
        ):
            _ = run_planner_shell(
                KernelChatRequest(
                    sessionId="s1",
                    mode="local",
                    query="总结这几篇论文的差异",
                    history=[],
                    traceId="trace-shadow-config",
                    configPath="/tmp/runtime-config.yaml",
                ),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(mocked_load_config.call_count, 2)
        self.assertEqual(mocked_load_config.call_args_list[0].args, ("/tmp/runtime-config.yaml",))
        self.assertEqual(mocked_load_config.call_args_list[1].args, ("/tmp/runtime-config.yaml",))

    def test_llm_primary_mode_accepts_valid_llm_decision(self) -> None:
        llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.95,
            "user_goal": "这篇论文的作者是谁",
            "standalone_query": "这篇论文的作者是谁",
            "is_new_topic": False,
            "should_clear_pending_clarify": False,
            "relation_to_previous": "same_topic_or_no_pending",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "clarify_question": None,
            "selected_tools_or_skills": ["fact_qa"],
            "action_plan": [{"action": "fact_qa", "query": "这篇论文的作者是谁"}],
            "fallback": {"type": None, "reason": None},
        }
        calls: list[str] = []

        def fact_executor(payload, **kwargs):
            _ = payload
            calls.append(kwargs["selected_path"])
            return _response("llm-primary")

        with patch.dict(os.environ, {"PLANNER_SOURCE_MODE": "llm_primary", "PLANNER_LLM_DECISION_JSON": json.dumps(llm_decision)}, clear=False):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-llm-primary"),
                fact_qa_executor=fact_executor,
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(calls, ["fact_qa"])
        self.assertEqual(result["observation"]["planner_source_mode"], "llm_primary")
        self.assertEqual(result["observation"]["planner_execution_source"], "llm")
        self.assertEqual(result["observation"]["planner"]["planner_source"], "llm")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "accept")

    def test_llm_primary_mode_rejects_invalid_llm_decision_into_controlled_terminate(self) -> None:
        invalid_llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.95,
            "user_goal": "这篇论文的作者是谁",
            "standalone_query": "这篇论文的作者是谁",
            "is_new_topic": False,
            "should_clear_pending_clarify": False,
            "relation_to_previous": "same_topic_or_no_pending",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "clarify_question": None,
            "selected_tools_or_skills": ["unknown_tool"],
            "action_plan": [{"action": "unknown_tool", "query": "这篇论文的作者是谁"}],
            "fallback": {"type": None, "reason": None},
        }

        with patch.dict(os.environ, {"PLANNER_SOURCE_MODE": "llm_primary", "PLANNER_LLM_DECISION_JSON": json.dumps(invalid_llm_decision)}, clear=False):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-llm-fallback"),
                fact_qa_executor=lambda payload, **kwargs: _response("rule-fallback"),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["response"].traceId, "trace-llm-fallback")
        self.assertEqual(result["observation"]["planner_source_mode"], "llm_primary")
        self.assertEqual(result["observation"]["planner_execution_source"], "fallback")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("unsupported_tool:unknown_tool", result["observation"]["planner_validation"]["reason_codes"])

    def test_llm_primary_mode_rejects_invalid_llm_schema_into_controlled_terminate(self) -> None:
        invalid_llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": "high",
            "user_goal": "这篇论文的作者是谁",
            "standalone_query": "这篇论文的作者是谁",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "selected_tools_or_skills": ["fact_qa"],
            "fallback": "none",
            "action_plan": [{"action": "fact_qa", "query": "这篇论文的作者是谁"}],
        }
        calls: list[tuple[str, bool]] = []
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=True,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        def fact_executor(payload, **kwargs):
            _ = payload
            calls.append((kwargs["selected_path"], kwargs["runtime_fallback"]))
            return _response("schema-fallback")

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "llm_primary", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
            patch(
                "app.planner_runtime.call_chat_completion",
                return_value=LLMCallResult(
                    ok=True,
                    content=json.dumps(invalid_llm_decision, ensure_ascii=False),
                    reason=None,
                    attempts_used=1,
                    max_retries=0,
                    elapsed_ms=12,
                    provider_used="siliconflow",
                    model_used="planner-model",
                ),
            ),
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-llm-schema"),
                fact_qa_executor=fact_executor,
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(calls, [])
        self.assertEqual(result["response"].traceId, "trace-llm-schema")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertTrue(result["observation"]["planner_runtime_fallback"])
        self.assertEqual(result["observation"]["planner_execution_source"], "fallback")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("invalid_type:planner_confidence", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("invalid_type:fallback", result["observation"]["planner_validation"]["reason_codes"])

    def test_shadow_compare_respects_planner_use_llm_flag_even_when_api_key_exists(self) -> None:
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=False,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "shadow_compare", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
            patch("app.planner_runtime.call_chat_completion") as mocked_llm,
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="总结这几篇论文的差异", history=[], traceId="trace-llm-disabled"),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        mocked_llm.assert_not_called()
        self.assertEqual(result["observation"]["planner_source_mode"], "shadow_compare")
        self.assertEqual(result["observation"]["planner_execution_source"], "fallback")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_llm_diagnostics"]["reason"], "planner_legacy_disabled")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("planner_legacy_disabled", result["observation"]["planner_validation"]["reason_codes"])

    def test_llm_primary_mode_rejects_raw_schema_before_normalization(self) -> None:
        invalid_llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.9,
            "user_goal": "这篇论文的作者是谁",
            "standalone_query": "这篇论文的作者是谁",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "selected_tools_or_skills": "fact_qa",
            "fallback": {"type": None, "reason": None},
            "action_plan": ["bad-step", {"action": "fact_qa", "query": "这篇论文的作者是谁"}],
        }
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=True,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "llm_primary", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
            patch(
                "app.planner_runtime.call_chat_completion",
                return_value=LLMCallResult(
                    ok=True,
                    content=json.dumps(invalid_llm_decision, ensure_ascii=False),
                    reason=None,
                    attempts_used=1,
                    max_retries=0,
                    elapsed_ms=12,
                    provider_used="siliconflow",
                    model_used="planner-model",
                ),
            ),
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-llm-raw-schema"),
                fact_qa_executor=lambda payload, **kwargs: _response("raw-schema-fallback"),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["response"].traceId, "trace-llm-raw-schema")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_execution_source"], "fallback")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("invalid_type:selected_tools_or_skills", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("invalid_type:action_plan_step", result["observation"]["planner_validation"]["reason_codes"])
        self.assertEqual(result["observation"]["planner_candidates"]["llm"]["selected_tools_or_skills"], "fact_qa")
        self.assertEqual(result["observation"]["planner_candidates"]["llm"]["action_plan"][0], "bad-step")

    def test_runtime_uses_configured_planner_limits_for_policy_flags(self) -> None:
        planner_cfg = SimpleNamespace(
            planner_max_steps=5,
            planner_max_papers=42,
            planner_summary_min_papers=7,
        )

        with (
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
        ):
            result = self._run_with_llm_decision(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文作者是谁", history=[], traceId="trace-configured-limits"),
                llm_decision=self._llm_decision(
                    user_goal="这篇论文作者是谁",
                    standalone_query="这篇论文作者是谁",
                    action_plan=[{"action": "fact_qa", "query": "这篇论文作者是谁"}],
                ),
                fact_qa_executor=lambda payload, **kwargs: _response(),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        policy_flags = result["observation"]["planner_input_context"]["policy_flags"]
        self.assertEqual(policy_flags["max_steps"], 5)
        self.assertEqual(policy_flags["catalog_limit"], 42)
        self.assertEqual(policy_flags["summary_min_papers"], 7)

    def test_llm_primary_mode_rejects_string_boolean_fields(self) -> None:
        invalid_llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": "yes",
            "planner_confidence": 0.9,
            "user_goal": "请先确认范围",
            "standalone_query": "请先确认范围",
            "is_new_topic": "false",
            "should_clear_pending_clarify": "false",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "clarify",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": "false",
            "clarify_question": "请补充具体论文。",
            "selected_tools_or_skills": [],
            "fallback": {"type": None, "reason": None},
            "action_plan": [],
        }
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=True,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "llm_primary", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
            patch(
                "app.planner_runtime.call_chat_completion",
                return_value=LLMCallResult(
                    ok=True,
                    content=json.dumps(invalid_llm_decision, ensure_ascii=False),
                    reason=None,
                    attempts_used=1,
                    max_retries=0,
                    elapsed_ms=12,
                    provider_used="siliconflow",
                    model_used="planner-model",
                ),
            ),
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="请先确认范围", history=[], traceId="trace-bool-schema"),
                fact_qa_executor=lambda payload, **kwargs: _response("bool-schema-fallback"),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["response"].traceId, "trace-bool-schema")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_execution_source"], "fallback")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("invalid_type:planner_used", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("invalid_type:is_new_topic", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("invalid_type:should_clear_pending_clarify", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("invalid_type:requires_clarification", result["observation"]["planner_validation"]["reason_codes"])

    def test_llm_primary_mode_rejects_missing_declared_contract_fields(self) -> None:
        invalid_llm_decision = {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": 0.9,
            "user_goal": "这篇论文的作者是谁",
            "standalone_query": "这篇论文的作者是谁",
            "primary_capability": "fact_qa",
            "strictness": "strict_fact",
            "decision_result": "local_execute",
            "knowledge_route": "local",
            "research_mode": "none",
            "requires_clarification": False,
            "selected_tools_or_skills": ["fact_qa"],
            "fallback": {"type": None, "reason": None},
            "action_plan": [{"action": "fact_qa", "query": "这篇论文的作者是谁"}],
        }
        planner_cfg = SimpleNamespace(
            planner_provider="siliconflow",
            planner_model="planner-model",
            planner_api_base="https://planner.example.com",
            planner_api_key_env="SILICONFLOW_API_KEY",
            planner_use_llm=True,
            planner_timeout_ms=6000,
            llm_max_retries=0,
        )

        with (
            patch.dict(
                os.environ,
                {"PLANNER_SOURCE_MODE": "llm_primary", "PLANNER_LLM_DECISION_JSON": "", "SILICONFLOW_API_KEY": "test-key"},
                clear=False,
            ),
            patch("app.planner_runtime.load_and_validate_config", return_value=(planner_cfg, [])),
            patch(
                "app.planner_runtime.call_chat_completion",
                return_value=LLMCallResult(
                    ok=True,
                    content=json.dumps(invalid_llm_decision, ensure_ascii=False),
                    reason=None,
                    attempts_used=1,
                    max_retries=0,
                    elapsed_ms=12,
                    provider_used="siliconflow",
                    model_used="planner-model",
                ),
            ),
        ):
            result = run_planner_shell(
                KernelChatRequest(sessionId="s1", mode="local", query="这篇论文的作者是谁", history=[], traceId="trace-missing-contract-fields"),
                fact_qa_executor=lambda payload, **kwargs: _response("missing-contract-fallback"),
                compat_executor=lambda payload, **kwargs: _response("compat"),
                legacy_executor=lambda payload, **kwargs: _response("legacy"),
            )

        self.assertEqual(result["response"].traceId, "trace-missing-contract-fields")
        self.assertEqual(result["observation"]["selected_path"], "controlled_terminate")
        self.assertEqual(result["observation"]["planner_execution_source"], "fallback")
        self.assertEqual(result["observation"]["planner_validation"]["status"], "reject")
        self.assertIn("missing_field:is_new_topic", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("missing_field:should_clear_pending_clarify", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("missing_field:relation_to_previous", result["observation"]["planner_validation"]["reason_codes"])
        self.assertIn("missing_field:clarify_question", result["observation"]["planner_validation"]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
