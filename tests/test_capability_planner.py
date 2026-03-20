from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app import capability_planner
from app.capability_planner import (
    PLANNER_SOURCE_LLM,
    build_planner_fallback,
    execute_catalog_lookup,
    paper_assistant_clarification,
    parse_planner_result,
    serialize_planner_result,
)
from app.config import PipelineConfig
from app.qa import run_qa
from app.retrieve import RetrievalCandidate


class CapabilityPlannerTests(unittest.TestCase):
    def _planner_payload(self, **overrides) -> dict[str, object]:
        payload: dict[str, object] = {
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
        payload.update(overrides)
        return payload

    def test_planner_result_round_trip_preserves_decision_schema(self) -> None:
        result = parse_planner_result(self._planner_payload(), default_query="总结这几篇论文的差异")
        serialized = serialize_planner_result(result)
        serialized["planner_source"] = PLANNER_SOURCE_LLM
        parsed = parse_planner_result(serialized, default_query="总结这几篇论文的差异")
        self.assertEqual(parsed.primary_capability, result.primary_capability)
        self.assertEqual(parsed.decision_result, result.decision_result)
        self.assertEqual(parsed.action_plan, result.action_plan)
        self.assertEqual(parsed.planner_source, PLANNER_SOURCE_LLM)

    def test_parse_planner_result_preserves_catalog_then_summary_plan(self) -> None:
        result = parse_planner_result(
            self._planner_payload(
                user_goal="列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异",
                standalone_query="列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异",
                selected_tools_or_skills=["catalog_lookup", "cross_doc_summary"],
                action_plan=[
                    {"action": "catalog_lookup", "query": "列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异", "produces": "paper_set", "params": {"limit": 3}},
                    {"action": "cross_doc_summary", "query": "列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异", "depends_on": ["paper_set"], "params": {"format": "table"}},
                ],
            ),
            default_query="列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异",
        )
        self.assertEqual([step["action"] for step in result.action_plan], ["catalog_lookup", "cross_doc_summary"])
        self.assertEqual(result.action_plan[1]["params"].get("format"), "table")

    def test_paper_assistant_clarification_requires_scope_for_deictic_requests(self) -> None:
        missing, question = paper_assistant_clarification("帮我比较这些论文并给出下一步研究建议")
        self.assertEqual(missing, ["paper_scope"])
        self.assertIn("请先说明", question or "")

    def test_build_planner_fallback_uses_controlled_terminate(self) -> None:
        result = build_planner_fallback(
            user_input="请联网查看最近的 RAG 综述",
            standalone_query="请联网查看最近的 RAG 综述",
            reason="planner_llm_disabled",
            rejection_layer="llm_call",
        )
        self.assertEqual(result.decision_result, "controlled_terminate")
        self.assertEqual(result.planner_source, "fallback")
        self.assertEqual(result.fallback["rejection_layer"], "llm_call")

    def test_catalog_lookup_truncates_and_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            papers_path = Path(tmp) / "papers.json"
            payload = [
                {
                    "paper_id": f"p{i}",
                    "title": f"大模型论文 {i}",
                    "source_type": "pdf",
                    "imported_at": f"2026-03-12T0{i}:00:00+00:00",
                    "status": "ready",
                }
                for i in range(5)
            ]
            papers_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = execute_catalog_lookup(query="列出大模型论文", papers_path=papers_path, max_papers=2)
        self.assertEqual(result["matched_count"], 5)
        self.assertEqual(result["selected_count"], 2)
        self.assertTrue(result["truncated"])


class CapabilityPlannerIntegrationTests(unittest.TestCase):
    def _candidate_seed(self) -> list[RetrievalCandidate]:
        return [
            RetrievalCandidate(
                chunk_id="c:00001",
                score=0.9,
                content_type="body",
                payload={"source": "hybrid", "dense_backend": "tfidf", "retrieval_mode": "hybrid"},
                paper_id="p-new",
                page_start=1,
                section="Intro",
                text="知识库中包含关于大模型方法差异的证据。",
                clean_text="知识库 包含 大模型 方法 差异 证据",
            )
        ]

    def _args(self, *, q: str, session_id: str, store: Path, chunks: Path) -> Namespace:
        return Namespace(
            q=q,
            mode="hybrid",
            chunks=str(chunks),
            bm25_index=str(chunks.parent / "bm25.json"),
            vec_index=str(chunks.parent / "vec.json"),
            embed_index=str(chunks.parent / "embed.json"),
            config="configs/default.yaml",
            top_k=5,
            top_evidence=5,
            session_id=session_id,
            session_store=str(store),
            clear_session=False,
            topic_name="",
            topic_paper_ids="",
            run_id="",
            run_dir="",
        )

    def test_waiting_followup_new_topic_clears_pending_clarify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            chunks.write_text("", encoding="utf-8")
            (base / "papers.json").write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "p-new",
                            "title": "大模型综述",
                            "source_type": "pdf",
                            "imported_at": "2026-03-12T08:00:00+00:00",
                            "status": "ready",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = base / "session_store.json"
            store.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "s-new-topic": {
                                "turns": [
                                    {
                                        "turn_number": 1,
                                        "user_input": "这篇论文准确率是多少？",
                                        "standalone_query": "这篇论文准确率是多少",
                                        "answer": "请先补充具体论文。",
                                        "cited_chunk_ids": [],
                                        "decision": "need_scope_clarification",
                                        "output_warnings": ["insufficient_evidence_for_answer"],
                                        "entity_mentions": ["论文"],
                                        "topic_anchors": ["准确率", "论文"],
                                        "transient_constraints": ["numeric"],
                                    }
                                ],
                                "pending_clarify": {
                                    "original_question": "这篇论文准确率是多少",
                                    "clarify_question": "请补充具体论文。",
                                },
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = PipelineConfig()
            config.embedding.enabled = False
            config.planner_enabled = True
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)
            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 1, "min": 0.9, "max": 0.9, "mean": 0.9, "p50": 0.9, "p90": 0.9},
                    "warnings": [],
                },
            )()
            planner_result = parse_planner_result(
                {
                    "decision_version": "planner-policy-v1",
                    "planner_source": "llm",
                    "planner_used": True,
                    "planner_confidence": 0.93,
                    "user_goal": "库中有哪些论文",
                    "standalone_query": "库中有哪些论文",
                    "is_new_topic": True,
                    "should_clear_pending_clarify": True,
                    "relation_to_previous": "new_topic_catalog_request",
                    "primary_capability": "catalog_lookup",
                    "strictness": "catalog",
                    "decision_result": "local_execute",
                    "knowledge_route": "local",
                    "research_mode": "none",
                    "requires_clarification": False,
                    "clarify_question": None,
                    "selected_tools_or_skills": ["catalog_lookup"],
                    "action_plan": [{"action": "catalog_lookup", "query": "库中有哪些论文", "produces": "paper_set", "params": {"limit": 20}}],
                    "fallback": {"type": None, "reason": None},
                },
                default_query="库中有哪些论文",
            )
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa._resolve_primary_planner_result", return_value=(planner_result, None)),
            ):
                run_qa(self._args(q="库中有哪些论文", session_id="s-new-topic", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertTrue(trace.get("is_new_topic"))
            self.assertTrue(trace.get("should_clear_pending_clarify"))
            self.assertEqual(trace.get("primary_capability"), "catalog_lookup")
            self.assertEqual(trace.get("strictness"), "catalog")
            self.assertEqual(trace.get("standalone_query"), "库中有哪些论文")
            self.assertNotIn("准确率", trace.get("standalone_query", ""))
            self.assertEqual(trace.get("final_decision"), "answer_with_catalog")
            self.assertEqual(trace.get("final_interaction_authority"), "planner")
            self.assertEqual(trace.get("final_user_visible_posture"), "execute")

    def test_control_intent_trace_comes_from_planner_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            chunks.write_text("", encoding="utf-8")
            (base / "papers.json").write_text("[]", encoding="utf-8")
            store = base / "session_store.json"
            store.write_text(json.dumps({"sessions": {}}, ensure_ascii=False), encoding="utf-8")
            config = PipelineConfig()
            config.embedding.enabled = False
            config.planner_enabled = True
            config.intent_router_enabled = True
            run_dir = base / "run_control"
            run_dir.mkdir(parents=True, exist_ok=False)
            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 1, "min": 0.9, "max": 0.9, "mean": 0.9, "p50": 0.9, "p90": 0.9},
                    "warnings": [],
                },
            )()
            planner_result = capability_planner.parse_planner_result(
                {
                    "decision_version": "planner-policy-v1",
                    "planner_source": "llm",
                    "planner_used": True,
                    "planner_confidence": 0.93,
                    "user_goal": "换成表格展示，并继续上一轮比较",
                    "standalone_query": "换成表格展示，并继续上一轮比较",
                    "is_new_topic": False,
                    "should_clear_pending_clarify": False,
                    "relation_to_previous": "followup_overlap",
                    "primary_capability": "control",
                    "strictness": "summary",
                    "decision_result": "local_execute",
                    "knowledge_route": "local",
                    "research_mode": "none",
                    "requires_clarification": False,
                    "clarify_question": None,
                    "selected_tools_or_skills": ["control"],
                    "action_plan": [{"action": "control", "query": "换成表格展示，并继续上一轮比较"}],
                    "fallback": {"type": None, "reason": None},
                },
                default_query="换成表格展示，并继续上一轮比较",
            )

            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa._resolve_primary_planner_result", return_value=(planner_result, None)),
            ):
                run_qa(self._args(q="换成表格展示，并继续上一轮比较", session_id="s-control", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("primary_capability"), "control")
            self.assertEqual(trace.get("intent_route_source"), "planner_decision")
            self.assertFalse(trace.get("intent_route_fallback"))
            self.assertEqual(trace.get("intent_type"), "continuation_control")

    def test_tail_constraints_do_not_mark_posture_override_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            chunks.write_text("", encoding="utf-8")
            (base / "papers.json").write_text("[]", encoding="utf-8")
            store = base / "session_store.json"
            store.write_text(json.dumps({"sessions": {}}, ensure_ascii=False), encoding="utf-8")
            config = PipelineConfig()
            config.embedding.enabled = False
            config.planner_enabled = True
            config.evidence_policy_enforced = True
            run_dir = base / "run_posture"
            run_dir.mkdir(parents=True, exist_ok=False)
            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 1, "min": 0.9, "max": 0.9, "mean": 0.9, "p50": 0.9, "p90": 0.9},
                    "warnings": [],
                },
            )()

            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch(
                    "app.qa._apply_evidence_policy_gate",
                    return_value=(
                        "",
                        [],
                        {
                            "enabled": True,
                            "triggered": True,
                            "constraints_envelope": {
                                "constraint_type": "citation_legality",
                                "reason_code": "evidence_policy_gate_claim_not_supported",
                                "severity": "warning",
                                "retryable": True,
                                "blocking_scope": "response",
                                "user_safe_summary": "关键结论缺少可追溯证据。",
                                "evidence_snapshot": {},
                                "citation_status": "missing",
                                "suggested_next_actions": [],
                                "guardrail_blocked": False,
                                "allows_partial_answer": False,
                                "clarify_questions": [],
                            },
                        },
                    ),
                ),
            ):
                run_qa(self._args(q="这篇论文讲了什么", session_id="s-posture", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertFalse(trace.get("posture_override_forbidden"))
            self.assertNotIn("legacy_posture_override_attempts", trace)
            self.assertEqual(trace.get("final_interaction_authority"), "planner_policy")
            self.assertTrue(str(trace.get("interaction_decision_source") or "").startswith("planner_policy:"))

    def test_primary_planner_exception_enters_controlled_terminate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            chunks.write_text("", encoding="utf-8")
            (base / "papers.json").write_text("[]", encoding="utf-8")
            store = base / "session_store.json"
            store.write_text(json.dumps({"sessions": {}}, ensure_ascii=False), encoding="utf-8")
            config = PipelineConfig()
            config.embedding.enabled = False
            config.planner_enabled = True
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)
            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 1, "min": 0.9, "max": 0.9, "mean": 0.9, "p50": 0.9, "p90": 0.9},
                    "warnings": [],
                },
            )()

            def fake_planner(**kwargs):
                raise RuntimeError("planner boom")

            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa._resolve_primary_planner_result", side_effect=fake_planner),
            ):
                run_qa(self._args(q="这篇论文讲了什么", session_id="s-fallback", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertTrue(trace.get("planner_fallback"))
            self.assertEqual(trace.get("planner_fallback_reason"), "planner_exception")
            self.assertEqual(trace.get("planner_source"), "fallback")
            self.assertEqual(trace.get("primary_capability"), "fact_qa")
            self.assertEqual(trace.get("strictness"), "strict_fact")
            self.assertEqual(trace.get("decision_result"), "controlled_terminate")
            self.assertEqual(trace.get("action_plan"), [])
            self.assertEqual(trace.get("execution_trace"), [])

    def test_empty_catalog_short_circuits_followup_summary_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            chunks.write_text("", encoding="utf-8")
            (base / "papers.json").write_text("[]", encoding="utf-8")
            store = base / "session_store.json"
            store.write_text(json.dumps({"sessions": {}}, ensure_ascii=False), encoding="utf-8")
            config = PipelineConfig()
            config.embedding.enabled = False
            config.planner_enabled = True
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)
            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 1, "min": 0.9, "max": 0.9, "mean": 0.9, "p50": 0.9, "p90": 0.9},
                    "warnings": [],
                },
            )()
            planner_result = parse_planner_result(
                {
                    "decision_version": "planner-policy-v1",
                    "planner_source": "llm",
                    "planner_used": True,
                    "planner_confidence": 0.94,
                    "user_goal": "列出昨天上传的论文，并用表格对比方法差异",
                    "standalone_query": "列出昨天上传的论文，并用表格对比方法差异",
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
                    "selected_tools_or_skills": ["catalog_lookup", "cross_doc_summary"],
                    "action_plan": [
                        {"action": "catalog_lookup", "query": "列出昨天上传的论文，并用表格对比方法差异", "produces": "paper_set", "params": {"limit": 20}},
                        {"action": "cross_doc_summary", "query": "列出昨天上传的论文，并用表格对比方法差异", "depends_on": ["paper_set"], "params": {"format": "table"}},
                    ],
                    "fallback": {"type": None, "reason": None},
                },
                default_query="列出昨天上传的论文，并用表格对比方法差异",
            )
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa._resolve_primary_planner_result", return_value=(planner_result, None)),
            ):
                run_qa(self._args(q="列出昨天上传的论文，并用表格对比方法差异", session_id="s-empty-catalog", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("primary_capability"), "cross_doc_summary")
            self.assertEqual(trace.get("strictness"), "summary")
            self.assertEqual([step["action"] for step in trace.get("action_plan", [])], ["catalog_lookup", "cross_doc_summary"])
            self.assertEqual(trace.get("short_circuit"), {"triggered": True, "reason": "catalog_lookup_empty", "step": "catalog_lookup"})
            self.assertEqual(
                trace.get("execution_trace"),
                [
                    {
                        "step": 1,
                        "action": "catalog_lookup",
                        "state": "short_circuit",
                        "depends_on": [],
                        "produces": ["paper_set"],
                        "matched_count": 0,
                        "selected_count": 0,
                        "truncated": False,
                        "short_circuit": True,
                        "short_circuit_reason": "catalog_lookup_empty",
                    },
                    {
                        "step": 2,
                        "action": "cross_doc_summary",
                        "state": "short_circuit",
                        "depends_on": ["paper_set"],
                        "produces": [],
                        "short_circuit": True,
                        "short_circuit_reason": "missing_paper_set_dependency",
                    },
                ],
            )
            self.assertEqual(trace.get("final_answer"), "未找到符合条件的论文，因此未继续执行后续步骤。")
            self.assertEqual(trace.get("final_decision"), "answer_with_catalog")


if __name__ == "__main__":
    unittest.main()
