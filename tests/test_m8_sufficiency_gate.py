from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig
from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.qa import _tokenize_for_matching, run_qa, run_sufficiency_gate
from app.retrieve import RetrievalCandidate


def _grouped_from_text(texts: list[str], *, content_type: str = "body") -> list[dict[str, object]]:
    return [
        {
            "paper_id": "p1",
            "paper_title": "Paper One",
            "evidence": [
                {
                    "chunk_id": f"p1:{idx+1}",
                    "section_page": f"p.{idx+1}",
                    "quote": txt,
                    "content_type": content_type,
                }
                for idx, txt in enumerate(texts)
            ],
        }
    ]


class SufficiencyGateUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = PipelineConfig()
        self.cfg.sufficiency_gate_enabled = True
        self.cfg.embedding.enabled = False
        self.cfg.sufficiency_semantic_policy = "balanced"
        self.cfg.sufficiency_semantic_threshold_balanced = 0.25
        self.cfg.sufficiency_judge_use_llm = True

    def _judge_answer(self, *, decision_hint: str, missing_aspects: list[str] | None = None) -> dict[str, object]:
        missing = list(missing_aspects or [])
        return {
            "decision_hint": decision_hint,
            "judge_status": "ok" if decision_hint != "uncertain" else "uncertain",
            "judge_source": "semantic_evidence_judge_llm_v1",
            "confidence": "high",
            "coverage_summary": {
                "topic_aligned": decision_hint != "mismatch",
                "covered_aspects": [] if decision_hint == "mismatch" else ["covered"],
                "missing_aspects": missing,
                "matched_anchors": ["transformer"],
                "anchor_count": 1,
                "evidence_groups": 1,
            },
            "missing_aspects": missing,
            "allows_partial_answer": decision_hint == "partial",
            "semantic_policy": "balanced",
            "semantic_threshold": 0.25,
            "output_warnings": [],
        }

    def test_topic_mismatch_triggers_refuse(self) -> None:
        evidence = _grouped_from_text(
            [
                "This section discusses bibliography style and citation formatting details.",
                "Reference list normalization for metadata processing.",
            ]
        )
        with patch("app.sufficiency.judge_semantic_evidence", return_value=self._judge_answer(decision_hint="mismatch")):
            gate = run_sufficiency_gate(
                question="比特币今天价格是多少？",
                scope_mode="open",
                evidence_grouped=evidence,
                config=self.cfg,
            )
        self.assertEqual(gate.get("decision"), "refuse")
        self.assertEqual(gate.get("reason_code"), "topic_mismatch")

    def test_topic_tokenization_splits_mixed_text_without_spaces(self) -> None:
        tokens = _tokenize_for_matching("Transformer是什么")
        self.assertIn("transformer", tokens)
        self.assertNotIn("transformer是什么", tokens)

    def test_topic_tokenization_stable_with_full_width_punctuation(self) -> None:
        plain = _tokenize_for_matching("Transformer是什么")
        punctuated = _tokenize_for_matching("Transformer是什么？")
        self.assertIn("transformer", plain)
        self.assertIn("transformer", punctuated)

    def test_partial_coverage_returns_structured_missing_aspects(self) -> None:
        evidence = _grouped_from_text(
            [
                "The method introduces a retrieval framework with two-stage ranking.",
                "Implementation steps are summarized for the ranking pipeline.",
            ]
        )
        with patch(
            "app.sufficiency.judge_semantic_evidence",
            return_value=self._judge_answer(decision_hint="partial", missing_aspects=["precision value"]),
        ):
            gate = run_sufficiency_gate(
                question="What is the precision value and what are the method steps?",
                scope_mode="open",
                evidence_grouped=evidence,
                config=self.cfg,
            )
        self.assertEqual(gate.get("decision"), "answer")
        self.assertTrue(gate.get("allows_partial_answer"))
        self.assertEqual(gate.get("reason_code"), "partial_coverage")
        self.assertTrue(gate.get("missing_aspects"))
        self.assertIn("coverage_summary", gate)
        self.assertIn("judge_source", gate)
        self.assertIn("validator_source", gate)
        self.assertIn("partial_coverage", gate.get("output_warnings", []))

    def test_open_summary_returns_partial_answer_contract(self) -> None:
        evidence = _grouped_from_text(
            [
                "The corpus highlights retrieval architecture, rerank diagnostics and evidence policy.",
                "It discusses practical trade-offs and suggested follow-up investigations.",
            ]
        )
        with patch("app.sufficiency.judge_semantic_evidence", return_value=self._judge_answer(decision_hint="answer")):
            gate = run_sufficiency_gate(
                question="帮我总结这个知识库最值得关注的方向",
                scope_mode="open",
                evidence_grouped=evidence,
                open_summary_intent=True,
                config=self.cfg,
            )
        self.assertEqual(gate.get("decision"), "answer")
        self.assertTrue(gate.get("allows_partial_answer") or gate.get("reason_code") == "ready_to_answer")
        self.assertIn("coverage_summary", gate)

    def test_control_intent_topic_match_uses_anchor_query_source(self) -> None:
        evidence = _grouped_from_text(
            [
                "Transformer architecture includes attention blocks and feed-forward layers.",
                "The method details model components and training setup.",
            ]
        )
        with patch("app.sufficiency.judge_semantic_evidence", return_value=self._judge_answer(decision_hint="answer")):
            gate = run_sufficiency_gate(
                question="用中文回答我",
                query_used="用中文回答我",
                topic_query_source="anchor_query",
                topic_query_text="Transformer architecture components",
                scope_mode="open",
                evidence_grouped=evidence,
                config=self.cfg,
            )
        self.assertEqual(gate.get("decision"), "answer")
        self.assertEqual(gate.get("topic_query_source"), "anchor_query")
        self.assertEqual(gate.get("topic_query_text"), "Transformer architecture components")

    def test_hard_validator_blocks_noisy_only_evidence(self) -> None:
        evidence = _grouped_from_text(
            [
                "Metadata and front matter only.",
                "Reference appendix only.",
            ],
            content_type="reference",
        )
        gate = run_sufficiency_gate(
            question="Summarize the retrieved topic.",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "refuse")
        self.assertEqual(gate.get("reason_code"), "insufficient_evidence_count_or_quality")
        self.assertIn("insufficient_evidence_count_or_quality", gate.get("output_warnings", []))


class SufficiencyGateIntegrationTests(unittest.TestCase):
    def _write_chunks_clean(self, path: Path) -> None:
        rows = [
            {
                "chunk_id": "p1:1",
                "paper_id": "p1",
                "page_start": 1,
                "section": "intro",
                "content_type": "body",
                "text": "This corpus is about retrieval architecture and rerank diagnostics.",
                "clean_text": "This corpus is about retrieval architecture and rerank diagnostics.",
            },
            {
                "chunk_id": "p1:2",
                "paper_id": "p1",
                "page_start": 2,
                "section": "method",
                "content_type": "body",
                "text": "The method describes chunk scoring but no external world facts.",
                "clean_text": "The method describes chunk scoring but no external world facts.",
            },
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_run_qa_refuse_branch_outputs_decision_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: false\n"
                "sufficiency_gate_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="2026年美联储主席是谁？",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-it",
                session_store=str(base / "session_store.json"),
                clear_session=False,
            )
            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="rerank diagnostics", clean_text="rerank diagnostics", paper_id="p1", page_start=2),
            ]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("decision"), "refuse")
            self.assertEqual(report.get("final_refuse_source"), "sufficiency_gate")
            self.assertIn("insufficient_evidence_for_answer", report.get("output_warnings", []))

    def test_run_qa_answer_branch_traces_new_sufficiency_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: false\n"
                "assistant_mode_enabled: false\n"
                "sufficiency_gate_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="Summarize the retrieved topic.",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-it-answer",
                session_store=str(base / "session_store.json"),
                clear_session=False,
            )
            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="retrieval architecture and diagnostics", clean_text="retrieval architecture and diagnostics", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="chunk scoring method details", clean_text="chunk scoring method details", paper_id="p1", page_start=2),
            ]
            mocked_citations = [{"chunk_id": "p1:1", "paper_id": "p1", "section_page": "p.1"}]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.run_sufficiency_gate",
                    return_value={
                        "enabled": True,
                        "decision": "answer",
                        "reason": "证据充分，可进入回答。",
                        "reason_code": "ready_to_answer",
                        "severity": "info",
                        "clarify_questions": [],
                        "output_warnings": [],
                        "semantic_policy": "balanced",
                        "triggered_rules": [],
                        "clarify_limit_hit": False,
                        "forced_partial_answer": False,
                        "missing_aspects": [],
                        "coverage_summary": {"topic_aligned": True},
                        "judge_source": "semantic_evidence_judge_llm_v1",
                        "validator_source": "deterministic_validator_v1",
                        "allows_partial_answer": False,
                    },
                ),
                patch(
                    "app.qa._build_answer",
                    return_value=(
                        "The retrieved topic is retrieval diagnostics.",
                        mocked_citations,
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
                ) as mocked_build_answer,
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
                mocked_build_answer.assert_called_once()

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("decision"), "answer")
            self.assertEqual(report.get("answer_citations"), mocked_citations)
            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            sufficiency_gate = trace.get("sufficiency_gate", {})
            self.assertIn("coverage_summary", sufficiency_gate)
            self.assertIn("judge_source", sufficiency_gate)
            self.assertIn("validator_source", sufficiency_gate)

    def test_run_qa_open_summary_uses_assistant_mode_outputs_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: false\n"
                "assistant_mode_enabled: true\n"
                "assistant_mode_force_legacy_gate: false\n"
                "evidence_policy_enforced: false\n"
                "sufficiency_gate_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="帮我总结这个知识库最值得关注的方向",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-it-assistant",
                session_store=str(base / "session_store.json"),
                clear_session=False,
            )
            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.95, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p2:1", score=0.90, text="rerank diagnostics", clean_text="rerank diagnostics", paper_id="p2", page_start=1),
                RetrievalCandidate(chunk_id="p3:1", score=0.85, text="evidence policy robustness", clean_text="evidence policy robustness", paper_id="p3", page_start=1),
            ]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.run_sufficiency_gate",
                    return_value={
                        "enabled": True,
                        "decision": "answer",
                        "reason": "当前证据仅覆盖了问题的一部分，将按可追溯部分回答。",
                        "reason_code": "partial_coverage",
                        "clarify_questions": [],
                        "semantic_policy": "balanced",
                        "triggered_rules": ["partial_coverage"],
                        "clarify_limit_hit": False,
                        "forced_partial_answer": False,
                        "output_warnings": ["partial_coverage"],
                        "missing_aspects": ["研究重点"],
                        "coverage_summary": {"topic_aligned": True},
                        "judge_source": "semantic_evidence_judge_llm_v1",
                        "validator_source": "deterministic_validator_v1",
                        "allows_partial_answer": True,
                    },
                ),
                patch(
                    "app.qa._build_evidence_grouped",
                    return_value=(
                        [
                            {"paper_id": "p1", "paper_title": "P1", "evidence": [{"chunk_id": "p1:1", "section_page": "p.1", "quote": "retrieval architecture", "content_type": "body"}]},
                            {"paper_id": "p2", "paper_title": "P2", "evidence": [{"chunk_id": "p2:1", "section_page": "p.1", "quote": "rerank diagnostics", "content_type": "body"}]},
                            {"paper_id": "p3", "paper_title": "P3", "evidence": [{"chunk_id": "p3:1", "section_page": "p.1", "quote": "evidence policy robustness", "content_type": "body"}]},
                        ],
                        [],
                    ),
                ),
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("assistant_mode_used"))
            self.assertEqual(report.get("decision"), "answer")
            self.assertGreaterEqual(len(report.get("answer_citations", [])), 3)
            self.assertGreaterEqual(len(report.get("assistant_summary_suggestions", [])), 1)


if __name__ == "__main__":
    unittest.main()
