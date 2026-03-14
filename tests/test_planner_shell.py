from __future__ import annotations

import unittest

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
            calls.append((kwargs["selected_path"], kwargs["planner_shell_fallback"], kwargs["planner_shell_fallback_reason"]))
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

    def test_executor_failure_falls_back_to_legacy_path(self) -> None:
        legacy_calls: list[tuple[str, bool]] = []

        def failing_fact_executor(payload, **kwargs):
            _ = (payload, kwargs)
            raise RuntimeError("boom")

        def legacy_executor(payload, **kwargs):
            _ = payload
            legacy_calls.append((kwargs["selected_path"], kwargs["planner_shell_fallback"]))
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
