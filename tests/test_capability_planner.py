from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app import capability_planner
from app.capability_planner import build_rule_based_plan, execute_catalog_lookup
from app.config import PipelineConfig
from app.qa import run_qa
from app.retrieve import RetrievalCandidate


class CapabilityPlannerTests(unittest.TestCase):
    def test_rule_planner_builds_catalog_then_summary_plan(self) -> None:
        result = build_rule_based_plan(
            user_input="列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异",
            standalone_query="列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异",
            dialog_state="normal",
            history_topic_anchors=[],
            pending_clarify=None,
            max_steps=3,
            catalog_limit=20,
        )
        self.assertEqual(result.primary_capability, "cross_doc_summary")
        self.assertEqual(result.strictness, "summary")
        self.assertEqual([step["action"] for step in result.action_plan], ["catalog_lookup", "cross_doc_summary"])
        self.assertEqual(result.action_plan[1]["params"].get("format"), "table")

    def test_rule_planner_upgrades_strict_fact_escape(self) -> None:
        result = build_rule_based_plan(
            user_input="对比这 3 篇论文的准确率具体数值",
            standalone_query="对比这 3 篇论文的准确率具体数值",
            dialog_state="normal",
            history_topic_anchors=[],
            pending_clarify=None,
            max_steps=3,
            catalog_limit=20,
        )
        self.assertEqual(result.primary_capability, "fact_qa")
        self.assertEqual(result.strictness, "strict_fact")
        self.assertEqual(result.action_plan[-1]["action"], "fact_qa")

    def test_rule_planner_emits_paper_assistant_tool_for_research_guidance(self) -> None:
        result = build_rule_based_plan(
            user_input="帮我比较这些论文并给出下一步研究建议",
            standalone_query="帮我比较这些论文并给出下一步研究建议",
            dialog_state="normal",
            history_topic_anchors=[],
            pending_clarify=None,
            max_steps=3,
            catalog_limit=20,
        )
        self.assertEqual(result.primary_capability, "paper_assistant")
        self.assertEqual(result.strictness, "summary")
        self.assertEqual(result.action_plan[-1]["action"], "paper_assistant")

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
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
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

    def test_planner_exception_falls_back_to_single_step_fact_qa(self) -> None:
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

            planner_calls = {"count": 0}

            def fake_planner(**kwargs):
                planner_calls["count"] += 1
                if planner_calls["count"] == 1:
                    return capability_planner.build_rule_based_plan(**kwargs)
                raise RuntimeError("planner boom")

            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa.build_rule_based_plan", side_effect=fake_planner),
            ):
                run_qa(self._args(q="这篇论文讲了什么", session_id="s-fallback", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertTrue(trace.get("planner_fallback"))
            self.assertEqual(trace.get("planner_fallback_reason"), "planner_exception")
            self.assertEqual(trace.get("planner_source"), "fallback")
            self.assertEqual(trace.get("primary_capability"), "fact_qa")
            self.assertEqual(trace.get("strictness"), "strict_fact")
            self.assertEqual(trace.get("action_plan"), [{"action": "fact_qa", "query": "这篇论文讲了什么", "depends_on": [], "produces": None, "params": {}}])
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
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch("app.qa.expand_candidates_with_graph", side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []})),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
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
