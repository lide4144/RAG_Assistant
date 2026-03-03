from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig
from app.qa import run_qa
from app.rewrite import RewriteGuardResult
from app.retrieve import RetrievalCandidate
from app.session_state import clear_session


class M76MultiTurnTests(unittest.TestCase):
    def _candidate_seed(self) -> list[RetrievalCandidate]:
        return [
            RetrievalCandidate(
                chunk_id="c:00001",
                score=0.9,
                content_type="body",
                payload={"source": "hybrid", "dense_backend": "tfidf", "retrieval_mode": "hybrid"},
                paper_id="p1",
                page_start=1,
                section="Intro",
                text="RAG combines retrieval with generation.",
                clean_text="rag combines retrieval generation",
            ),
            RetrievalCandidate(
                chunk_id="c:00002",
                score=0.85,
                content_type="body",
                payload={"source": "hybrid", "dense_backend": "tfidf", "retrieval_mode": "hybrid"},
                paper_id="p1",
                page_start=2,
                section="Method",
                text="Fine-tuning updates model weights while RAG uses external evidence.",
                clean_text="fine tuning updates weights rag external evidence",
            ),
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
        )

    def test_coreference_rewrite_contains_rag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "RAG Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="什么是 RAG？", session_id="s-rag", store=store, chunks=chunks))
                run_qa(self._args(q="它和微调有什么区别？", session_id="s-rag", store=store, chunks=chunks))

            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertIn("RAG", trace.get("standalone_query", ""))
            self.assertTrue(trace.get("coreference_resolved"))

    def test_clarify_merge_builds_independent_query_without_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Vision Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="这篇论文的作者是谁？", session_id="s-clarify", store=store, chunks=chunks))
                run_qa(self._args(q="作者是何恺明那篇", session_id="s-clarify", store=store, chunks=chunks))

            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertIn("何恺明", trace.get("standalone_query", ""))
            self.assertIn("这篇论文的作者是谁", trace.get("standalone_query", ""))
            self.assertNotEqual(trace.get("final_decision"), "need_scope_clarification")

    def test_session_store_is_dehydrated_and_clearable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=base / "run_01"),
            ):
                (base / "run_01").mkdir(parents=True, exist_ok=False)
                run_qa(self._args(q="RAG 是什么", session_id="s-hydrate", store=store, chunks=chunks))

            payload = json.loads(store.read_text(encoding="utf-8"))
            turn = payload["sessions"]["s-hydrate"]["turns"][0]
            self.assertIn("user_input", turn)
            self.assertIn("answer", turn)
            self.assertIn("cited_chunk_ids", turn)
            self.assertNotIn("text", turn)
            self.assertNotIn("clean_text", turn)

            self.assertTrue(clear_session("s-hydrate", store))
            payload = json.loads(store.read_text(encoding="utf-8"))
            self.assertNotIn("s-hydrate", payload.get("sessions", {}))

    def test_history_tokens_est_stays_small_across_five_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                for i in range(5):
                    run_qa(self._args(q=f"第{i+1}轮问题：RAG 与微调关系？", session_id="s-5", store=store, chunks=chunks))

            trace_5 = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertLess(trace_5.get("history_tokens_est", 99999), 2000)

    def test_clear_session_forces_history_used_turns_zero_on_next_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="第一轮：RAG 是什么", session_id="s-clear", store=store, chunks=chunks))
                args2 = self._args(q="第二轮：重新开始新主题", session_id="s-clear", store=store, chunks=chunks)
                args2.clear_session = True
                run_qa(args2)

            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("history_used_turns"), 0)
            self.assertTrue(trace.get("session_reset"))
            self.assertTrue(report.get("session_reset"))
            audit = trace.get("session_reset_audit", {})
            self.assertTrue(audit.get("session_reset_applied"))
            self.assertFalse(audit.get("constraints_inherited_after_reset"))

    def test_open_summary_after_clarify_drops_transient_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            store.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "s-open-summary-drop": {
                                "turns": [
                                    {
                                        "turn_number": 1,
                                        "user_input": "这篇论文准确率是多少？",
                                        "standalone_query": "这篇论文准确率是多少",
                                        "answer": "请提供更多约束",
                                        "cited_chunk_ids": [],
                                        "decision": "need_scope_clarification",
                                        "output_warnings": ["insufficient_evidence_for_answer"],
                                        "entity_mentions": ["论文"],
                                        "topic_anchors": ["论文"],
                                        "transient_constraints": ["numeric", "subject_constraint"],
                                    }
                                ],
                                "pending_clarify": {
                                    "original_question": "这篇论文准确率是多少",
                                    "clarify_question": "请补充具体评测指标。",
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
            config.intent_router_enabled = True
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)
            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
            ):
                run_qa(self._args(q="帮我总结一下这个知识库重点方向", session_id="s-open-summary-drop", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertTrue(trace.get("history_constraint_dropped"))
            self.assertIn("numeric", trace.get("dropped_constraints", []))
            self.assertEqual(trace.get("intent_type"), "retrieval_query")

    def test_standalone_query_does_not_leak_history_answer_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            run_dirs: list[Path] = []
            leak_phrase = "DO_NOT_LEAK_HISTORY_ANSWER_SENTENCE"
            store.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "s-no-leak": {
                                "turns": [
                                    {
                                        "turn_number": 1,
                                        "user_input": "什么是RAG",
                                        "standalone_query": "什么是RAG",
                                        "answer": f"超长历史回答 {leak_phrase} " * 20,
                                        "cited_chunk_ids": ["c:00001"],
                                        "decision": "answer_with_evidence",
                                        "entity_mentions": ["RAG"],
                                    }
                                ],
                                "pending_clarify": None,
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="它和微调有什么区别？", session_id="s-no-leak", store=store, chunks=chunks))

            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            standalone_query = str(trace.get("standalone_query", ""))
            self.assertIn("RAG", standalone_query)
            self.assertNotIn(leak_phrase, standalone_query)

    def test_meta_question_follow_up_rewrites_to_fact_query_and_exposes_trace_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="Transformer 有什么用处、由什么组成？", session_id="s-meta", store=store, chunks=chunks))
                run_qa(self._args(q="Why does it lack of evidences?", session_id="s-meta", store=store, chunks=chunks))

            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            standalone_query = str(trace.get("standalone_query", ""))
            self.assertIn("Transformer", standalone_query)
            self.assertNotIn("lack", standalone_query.lower())
            self.assertNotIn("evidence", standalone_query.lower())
            self.assertTrue(trace.get("rewrite_meta_detected"))
            self.assertTrue(trace.get("rewrite_guard_applied"))
            self.assertIsInstance(trace.get("rewrite_guard_strategy"), str)

    def test_clarify_merge_happens_before_meta_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            store.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "s-order": {
                                "turns": [
                                    {
                                        "turn_number": 1,
                                        "user_input": "这篇论文的作者是谁？",
                                        "standalone_query": "这篇论文的作者是谁？",
                                        "answer": "请提供论文标题/作者/年份/会议等线索。",
                                        "cited_chunk_ids": [],
                                        "decision": "need_scope_clarification",
                                        "output_warnings": ["insufficient_evidence_for_answer"],
                                        "entity_mentions": ["Transformer"],
                                    }
                                ],
                                "pending_clarify": {
                                    "original_question": "这篇论文的作者是谁？",
                                    "clarify_question": "请提供论文标题/作者/年份/会议等线索。",
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
            run_dirs: list[Path] = []
            captured: dict[str, str] = {}

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            def _guard_spy(*, user_input: str, standalone_query: str, **kwargs: object) -> RewriteGuardResult:
                captured["user_input"] = user_input
                captured["standalone_query"] = standalone_query
                return RewriteGuardResult(
                    standalone_query=standalone_query,
                    rewrite_meta_detected=True,
                    rewrite_guard_applied=True,
                    rewrite_guard_strategy="meta_question_insufficient_evidence_repair",
                    rewrite_notes="spy",
                )

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
                patch("app.qa.rewrite_with_history_context", side_effect=lambda u, _: (u, False)),
                patch("app.qa.apply_state_aware_rewrite_guard", side_effect=_guard_spy),
            ):
                run_qa(self._args(q="Why does it lack of evidences?", session_id="s-order", store=store, chunks=chunks))

            self.assertIn("用户补充：Why does it lack of evidences?", captured.get("user_input", ""))
            self.assertIn("这篇论文的作者是谁？", captured.get("standalone_query", ""))

    def test_meta_guard_can_be_disabled_by_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.rewrite_meta_guard_enabled = False
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
                patch("app.qa.apply_state_aware_rewrite_guard") as guard_mock,
            ):
                run_qa(self._args(q="Why does it lack of evidences?", session_id="s-disable-guard", store=store, chunks=chunks))

            guard_mock.assert_not_called()
            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertFalse(trace.get("rewrite_meta_detected"))
            self.assertFalse(trace.get("rewrite_guard_applied"))
            self.assertEqual(trace.get("rewrite_guard_strategy"), "none")

    def test_control_intent_reuses_recent_anchor_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = True
            config.style_control_reuse_last_topic = True
            config.style_control_max_turn_distance = 3
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="Transformer 有什么用处？", session_id="s-control-anchor", store=store, chunks=chunks))
                run_qa(self._args(q="用中文回答我", session_id="s-control-anchor", store=store, chunks=chunks))

            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("intent_type"), "style_control")
            self.assertEqual(trace.get("topic_query_source"), "anchor_query")
            self.assertIsInstance(trace.get("anchor_query"), str)
            self.assertIn("Transformer", str(trace.get("query_used", "")))
            anchor_resolution = trace.get("anchor_resolution", {})
            self.assertTrue(anchor_resolution.get("recent_cited_chunk_ids"))
            self.assertTrue(anchor_resolution.get("recent_evidence_terms"))

    def test_style_control_follow_up_keeps_answer_when_output_contains_uncertainty_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "RAG Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = True
            config.style_control_reuse_last_topic = True
            config.style_control_max_turn_distance = 3
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            expected_answer = (
                "RAG is defined as combining retrieval with generation. "
                "然而，证据中没有明确说明该方法在所有场景下的收益，因此信息不足。"
            )
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
                patch(
                    "app.qa._build_answer",
                    return_value=(
                        expected_answer,
                        [{"chunk_id": "c:00001", "paper_id": "p1", "section_page": "p.1"}],
                        False,
                        False,
                        None,
                        {
                            "answer_stream_enabled": False,
                            "answer_stream_used": False,
                            "answer_stream_first_token_ms": None,
                            "answer_stream_fallback_reason": None,
                            "answer_stream_events": [],
                        },
                        {
                            "prompt_tokens_est": 0,
                            "discarded_evidence": [],
                            "discarded_evidence_count": 0,
                            "history_trimmed_turns": 0,
                            "context_overflow_fallback": False,
                        },
                    ),
                ),
            ):
                run_qa(self._args(q="RAG 是什么？", session_id="s-style-uncertain", store=store, chunks=chunks))
                run_qa(self._args(q="用中文回答我", session_id="s-style-uncertain", store=store, chunks=chunks))

            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("intent_type"), "style_control")
            self.assertEqual(trace.get("topic_query_source"), "anchor_query")
            self.assertEqual(report.get("decision"), "answer")
            self.assertIsNone(report.get("final_refuse_source"))
            self.assertEqual(report.get("answer"), expected_answer)
            self.assertNotIn("Evidence Policy Gate", str(report.get("answer", "")))

    def test_format_and_continuation_control_are_routed_with_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = True
            config.style_control_reuse_last_topic = True
            config.style_control_max_turn_distance = 3
            run_dirs: list[Path] = []

            def _mk_run_dir(_: str) -> Path:
                out = base / f"run_{len(run_dirs) + 1:02d}"
                out.mkdir(parents=True, exist_ok=False)
                run_dirs.append(out)
                return out

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", side_effect=_mk_run_dir),
            ):
                run_qa(self._args(q="Transformer 有什么用处？", session_id="s-control-types", store=store, chunks=chunks))
                run_qa(self._args(q="请用要点列表回答", session_id="s-control-types", store=store, chunks=chunks))
                run_qa(self._args(q="继续", session_id="s-control-types", store=store, chunks=chunks))

            format_trace = json.loads((run_dirs[1] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(format_trace.get("intent_type"), "format_control")
            self.assertEqual(format_trace.get("topic_query_source"), "anchor_query")
            self.assertIn("Transformer", str(format_trace.get("query_used", "")))

            continuation_trace = json.loads((run_dirs[2] / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(continuation_trace.get("intent_type"), "continuation_control")
            self.assertEqual(continuation_trace.get("topic_query_source"), "anchor_query")
            self.assertIn("Transformer", str(continuation_trace.get("query_used", "")))

    def test_control_phrase_with_router_disabled_falls_back_to_retrieval_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = False
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
            ):
                run_qa(self._args(q="用中文回答我", session_id="s-router-off", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("intent_type"), "retrieval_query")
            self.assertEqual(trace.get("topic_query_source"), "user_query")

    def test_fact_question_with_router_enabled_still_uses_retrieval_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = True
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
            ):
                run_qa(self._args(q="Transformer 的核心思想是什么？", session_id="s-fact-query", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("intent_type"), "retrieval_query")
            self.assertEqual(trace.get("topic_query_source"), "user_query")

    def test_low_confidence_control_intent_falls_back_to_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = True
            config.intent_control_min_confidence = 0.9
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
            ):
                run_qa(self._args(q="请用中文回答 Transformer 的核心思想", session_id="s-low-confidence", store=store, chunks=chunks))

            trace = json.loads((run_dir / "run_trace.json").read_text(encoding="utf-8"))
            self.assertEqual(trace.get("intent_type"), "retrieval_query")
            self.assertIn("intent_low_confidence_fallback_to_retrieval", trace.get("output_warnings", []))
            self.assertIsInstance(trace.get("intent_confidence"), float)
            self.assertTrue(str(trace.get("intent_fallback_reason", "")).startswith("low_confidence_control_intent"))

    def test_control_intent_anchor_too_old_triggers_clarify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "chunks_clean.jsonl").write_text("", encoding="utf-8")
            (base / "papers.json").write_text(json.dumps([{"paper_id": "p1", "title": "Transformer Paper"}]), encoding="utf-8")
            store = base / "session_store.json"
            chunks = base / "chunks_clean.jsonl"
            store.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "s-control-stale": {
                                "turns": [
                                    {
                                        "turn_number": 1,
                                        "user_input": "Transformer 有什么用处？",
                                        "standalone_query": "Transformer 有什么用处",
                                        "answer": "A",
                                        "cited_chunk_ids": ["c:00001"],
                                        "decision": "answer_with_evidence",
                                        "output_warnings": [],
                                        "entity_mentions": ["Transformer"],
                                    },
                                    {
                                        "turn_number": 2,
                                        "user_input": "谢谢",
                                        "standalone_query": "",
                                        "answer": "B",
                                        "cited_chunk_ids": [],
                                        "decision": "answer_with_evidence",
                                        "output_warnings": [],
                                        "entity_mentions": [],
                                    },
                                    {
                                        "turn_number": 3,
                                        "user_input": "收到",
                                        "standalone_query": "",
                                        "answer": "C",
                                        "cited_chunk_ids": [],
                                        "decision": "answer_with_evidence",
                                        "output_warnings": [],
                                        "entity_mentions": [],
                                    },
                                ],
                                "pending_clarify": None,
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = PipelineConfig()
            config.embedding.enabled = False
            config.intent_router_enabled = True
            config.style_control_reuse_last_topic = True
            config.style_control_max_turn_distance = 1
            run_dir = base / "run_01"
            run_dir.mkdir(parents=True, exist_ok=False)

            rerank_outcome = type(
                "R",
                (),
                {
                    "candidates": self._candidate_seed(),
                    "score_distribution": {"count": 2, "min": 0.0, "max": 1.0, "mean": 0.5, "p50": 0.5, "p90": 0.9},
                    "warnings": [],
                },
            )()
            with (
                patch("app.qa.ensure_indexes", return_value={}),
                patch("app.qa.load_indexes_and_config", return_value=(None, None, None, config, [])),
                patch("app.qa.retrieve_candidates", return_value=self._candidate_seed()),
                patch(
                    "app.qa.expand_candidates_with_graph",
                    side_effect=lambda cands, **_: (cands, {"expansion_budget": 0, "added_chunk_ids": []}),
                ),
                patch("app.qa.rerank_candidates", return_value=rerank_outcome),
                patch("app.qa.create_run_dir", return_value=run_dir),
            ):
                run_qa(self._args(q="继续", session_id="s-control-stale", store=store, chunks=chunks))

            report = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("decision"), "clarify")
            self.assertIn("control_intent_anchor_missing_or_stale", report.get("output_warnings", []))


if __name__ == "__main__":
    unittest.main()
