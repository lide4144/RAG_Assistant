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


def _grouped_from_text(texts: list[str]) -> list[dict[str, object]]:
    return [
        {
            "paper_id": "p1",
            "paper_title": "Paper One",
            "evidence": [
                {
                    "chunk_id": f"p1:{idx+1}",
                    "section_page": f"p.{idx+1}",
                    "quote": txt,
                    "content_type": "body",
                }
                for idx, txt in enumerate(texts)
            ],
        }
    ]


class SufficiencyGateUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = PipelineConfig()
        self.cfg.sufficiency_gate_enabled = True
        self.cfg.sufficiency_topic_match_threshold = 0.2
        self.cfg.sufficiency_key_element_min_coverage = 1.0

    def test_topic_mismatch_triggers_refuse(self) -> None:
        evidence = _grouped_from_text(
            [
                "This section discusses bibliography style and citation formatting details.",
                "Reference list normalization for metadata processing.",
            ]
        )
        gate = run_sufficiency_gate(
            question="蛋白质结构预测的主要方法是什么？",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "refuse")
        self.assertIn("主题", str(gate.get("reason", "")))

    def test_topic_tokenization_splits_mixed_text_without_spaces(self) -> None:
        tokens = _tokenize_for_matching("Transformer是什么")
        self.assertIn("transformer", tokens)
        self.assertNotIn("transformer是什么", tokens)

    def test_topic_tokenization_stable_with_full_width_punctuation(self) -> None:
        plain = _tokenize_for_matching("Transformer是什么")
        punctuated = _tokenize_for_matching("Transformer是什么？")
        self.assertIn("transformer", plain)
        self.assertIn("transformer", punctuated)

    def test_missing_key_elements_triggers_clarify(self) -> None:
        evidence = _grouped_from_text([
            "The method introduces a retrieval framework with two-stage ranking.",
            "Implementation steps are summarized but numeric metrics are not reported.",
        ])
        gate = run_sufficiency_gate(
            question="What is the precision value and what are the method steps?",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "clarify")
        self.assertIn("关键要素", str(gate.get("reason", "")))
        clarify_questions = gate.get("clarify_questions", [])
        self.assertGreaterEqual(len(clarify_questions), 1)
        self.assertLessEqual(len(clarify_questions), 1)

    def test_missing_experiment_condition_triggers_clarify(self) -> None:
        self.cfg.sufficiency_topic_match_threshold = 0.0
        evidence = _grouped_from_text(
            [
                "The method introduces a retrieval framework with two-stage ranking.",
                "It reports final metrics but does not describe protocol details.",
            ]
        )
        gate = run_sufficiency_gate(
            question="该方法在什么实验条件下评估？",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "clarify")
        self.assertIn("experiment_condition", gate.get("missing_key_elements", []))

    def test_open_summary_does_not_false_trigger_numeric_clarify(self) -> None:
        self.cfg.sufficiency_topic_match_threshold = 0.0
        evidence = _grouped_from_text(
            [
                "The corpus highlights retrieval architecture, rerank diagnostics and evidence policy.",
                "It discusses practical trade-offs and suggested follow-up investigations.",
            ]
        )
        gate = run_sufficiency_gate(
            question="帮我总结这个知识库最值得关注的方向",
            scope_mode="open",
            evidence_grouped=evidence,
            open_summary_intent=True,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "answer")
        self.assertNotIn("numeric", gate.get("missing_key_elements", []))

    def test_missing_subject_constraint_triggers_clarify(self) -> None:
        self.cfg.sufficiency_topic_match_threshold = 0.0
        evidence = _grouped_from_text(
            [
                "The paper explains the training pipeline and model architecture.",
                "Evaluation metrics are reported, but no target description is provided.",
            ]
        )
        gate = run_sufficiency_gate(
            question="结论针对哪些受试者人群？",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "clarify")
        self.assertIn("subject_constraint", gate.get("missing_key_elements", []))

    def test_question_type_numeric_mapping_triggers_clarify(self) -> None:
        self.cfg.sufficiency_topic_match_threshold = 0.0
        evidence = _grouped_from_text(
            [
                "The report discusses benchmark setup and evaluation flow.",
                "No quantitative result is provided in this excerpt.",
            ]
        )
        gate = run_sufficiency_gate(
            question="How much improvement is reported?",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "clarify")
        self.assertIn("numeric", gate.get("missing_key_elements", []))

    def test_question_type_fact_check_mapping_triggers_clarify(self) -> None:
        self.cfg.sufficiency_topic_match_threshold = 0.0
        evidence = _grouped_from_text(
            [
                "This excerpt contains a claim discussion without paper identity clues.",
                "The paragraph focuses on claim interpretation only.",
            ]
        )
        gate = run_sufficiency_gate(
            question="Is this claim true?",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "clarify")
        self.assertIn("scope", gate.get("missing_key_elements", []))

    def test_out_of_corpus_10_questions_not_answer(self) -> None:
        evidence = _grouped_from_text(
            [
                "The corpus focuses on retrieval pipeline diagnostics.",
                "No medical, legal, or astronomical facts are included.",
            ]
        )
        questions = [
            "2026年美联储主席是谁？",
            "比特币今天价格是多少？",
            "纽约明天的天气如何？",
            "2026年奥斯卡最佳影片是哪部？",
            "最新 iPhone 的芯片型号是什么？",
            "美国今天通过了哪项税法？",
            "SpaceX 下一次发射时间是什么时候？",
            "当前英超积分榜第一是谁？",
            "黄金现货现在每盎司多少钱？",
            "今年诺贝尔物理学奖得主是谁？",
        ]
        for q in questions:
            gate = run_sufficiency_gate(
                question=q,
                scope_mode="open",
                evidence_grouped=evidence,
                config=self.cfg,
            )
            self.assertIn(gate.get("decision"), {"refuse", "clarify"})

    def test_dual_path_topic_score_uses_robust_aggregation(self) -> None:
        evidence = _grouped_from_text(
            [
                "Transformer is a neural network architecture for sequence modeling.",
                "The section explains attention blocks and training details.",
            ]
        )
        gate = run_sufficiency_gate(
            question="Transformer是什么",
            query_used="transformer definition",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "answer")
        self.assertIn("topic_match_score_standalone", gate)
        self.assertIn("topic_match_score_query_used", gate)
        self.assertIn("topic_match_score_robust", gate)
        robust = float(gate.get("topic_match_score_robust", 0.0))
        standalone = float(gate.get("topic_match_score_standalone", 0.0))
        query_used = float(gate.get("topic_match_score_query_used", 0.0))
        self.assertEqual(robust, max(standalone, query_used))

    def test_control_intent_topic_match_uses_anchor_query_source(self) -> None:
        evidence = _grouped_from_text(
            [
                "Transformer architecture includes attention blocks and feed-forward layers.",
                "The method details model components and training setup.",
            ]
        )
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

    def test_topic_mismatch_with_cluster_signal_prefers_clarify(self) -> None:
        self.cfg.sufficiency_topic_match_threshold = 0.7
        evidence = _grouped_from_text(
            [
                "Transformer retrieval architecture with staged ranking.",
                "Transformer diagnostics discuss method stability and retrieval trade-offs.",
            ]
        )
        gate = run_sufficiency_gate(
            question="请分析 transformer 在工业金融风控中的落地路线与关键边界",
            scope_mode="open",
            evidence_grouped=evidence,
            config=self.cfg,
        )
        self.assertEqual(gate.get("decision"), "clarify")
        self.assertIn("topic_mismatch_cluster_minimal_clarify", gate.get("triggered_rules", []))


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
                "sufficiency_topic_match_threshold: 0.2\n"
                "sufficiency_key_element_min_coverage: 1.0\n"
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
            self.assertIsInstance(report.get("decision_reason"), str)
            self.assertEqual(report.get("final_refuse_source"), "sufficiency_gate")
            self.assertEqual(report.get("answer_citations"), [])
            self.assertIn("insufficient_evidence_for_answer", report.get("output_warnings", []))

    def test_run_qa_clarify_branch_outputs_only_clarify_questions(self) -> None:
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
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 1.0\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="这篇论文的方法步骤和准确率在什么实验条件下得到？",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-it-clarify",
                session_store=str(base / "session_store.json"),
                clear_session=False,
            )
            cands = [
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=0.9,
                    text="retrieval architecture with two-stage method",
                    clean_text="retrieval architecture with two-stage method",
                    paper_id="p1",
                    page_start=1,
                ),
                RetrievalCandidate(
                    chunk_id="p1:2",
                    score=0.8,
                    text="method steps are summarized without metrics",
                    clean_text="method steps are summarized without metrics",
                    paper_id="p1",
                    page_start=2,
                ),
            ]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("decision"), "clarify")
            clarify_questions = report.get("clarify_questions", [])
            self.assertGreaterEqual(len(clarify_questions), 1)
            self.assertLessEqual(len(clarify_questions), 1)
            expected_answer = "为确保回答基于充分证据，请先澄清以下问题："
            for idx, q in enumerate(clarify_questions, start=1):
                expected_answer += f"\n{idx}. {q}"
            self.assertEqual(report.get("answer"), expected_answer)
            self.assertEqual(report.get("answer_citations"), [])

    def test_run_qa_answer_branch_calls_build_answer_and_keeps_citations_consistent(self) -> None:
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
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 1.0\n"
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
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=0.9,
                    text="retrieval architecture and diagnostics",
                    clean_text="retrieval architecture and diagnostics",
                    paper_id="p1",
                    page_start=1,
                ),
                RetrievalCandidate(
                    chunk_id="p1:2",
                    score=0.8,
                    text="chunk scoring method details",
                    clean_text="chunk scoring method details",
                    paper_id="p1",
                    page_start=2,
                ),
            ]
            mocked_citations = [{"chunk_id": "p1:1", "paper_id": "p1", "section_page": "p.1"}]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
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
            grouped_ids = {
                str(item.get("chunk_id"))
                for group in report.get("evidence_grouped", [])
                for item in group.get("evidence", [])
            }
            cited_ids = {str(c.get("chunk_id")) for c in report.get("answer_citations", [])}
            self.assertTrue(cited_ids.issubset(grouped_ids))
            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            sufficiency_gate = trace.get("sufficiency_gate", {})
            self.assertIn("topic_match_score_standalone", sufficiency_gate)
            self.assertIn("topic_match_score_query_used", sufficiency_gate)
            self.assertIn("topic_match_score_robust", sufficiency_gate)

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
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
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
                        "reason": "证据充分，可进入回答。",
                        "clarify_questions": [],
                        "triggered_rules": [],
                        "topic_match_score": 1.0,
                        "topic_match_score_standalone": 1.0,
                        "topic_match_score_query_used": 1.0,
                        "topic_match_score_robust": 1.0,
                        "topic_query_source": "user_query",
                        "topic_query_text": "summary query",
                        "key_element_coverage": 1.0,
                        "missing_key_elements": [],
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

    def test_run_qa_open_summary_with_less_than_three_topics_falls_back_to_clarify(self) -> None:
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
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
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
                session_id="m8-it-assistant-fallback",
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
            self.assertEqual(report.get("decision"), "clarify")
            self.assertEqual(len(report.get("clarify_questions", [])), 1)

    def test_run_qa_evidence_policy_refuse_has_consistent_source_and_copy(self) -> None:
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
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
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
                session_id="m8-it-epg",
                session_store=str(base / "session_store.json"),
                clear_session=False,
            )
            cands = [
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=0.9,
                    text="retrieval architecture and diagnostics",
                    clean_text="retrieval architecture and diagnostics",
                    paper_id="p1",
                    page_start=1,
                ),
                RetrievalCandidate(
                    chunk_id="p1:2",
                    score=0.8,
                    text="chunk scoring method details",
                    clean_text="chunk scoring method details",
                    paper_id="p1",
                    page_start=2,
                ),
            ]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa._build_answer",
                    return_value=(
                        "The experiment reports 95.0 accuracy.",
                        [{"chunk_id": "p9:99", "paper_id": "p9", "section_page": "p.9"}],
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
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("decision"), "refuse")
            self.assertEqual(report.get("final_refuse_source"), "evidence_policy_gate")
            self.assertIn("Evidence Policy Gate", str(report.get("answer", "")))

    def test_run_qa_assistant_mode_downgrades_evidence_gate_refuse_to_clarify(self) -> None:
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
                "evidence_policy_enforced: true\n"
                "sufficiency_gate_enabled: true\n"
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
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
                session_id="m8-it-assistant-no-refuse",
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
                    "app.qa._build_assistant_summary_answer",
                    return_value=(
                        "主题总结回答",
                        [{"chunk_id": "p9:99", "paper_id": "p9", "section_page": "p.9"}],
                        ["下一步建议1"],
                        True,
                    ),
                ),
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("assistant_mode_used"))
            self.assertEqual(report.get("decision"), "clarify")
            self.assertEqual(report.get("final_refuse_source"), None)
            self.assertEqual(len(report.get("clarify_questions", [])), 1)

    def test_natural_two_turn_regression_no_template_refuse_copy(self) -> None:
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
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            session_store = str(base / "session_store.json")
            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.95, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p2:1", score=0.90, text="rerank diagnostics", clean_text="rerank diagnostics", paper_id="p2", page_start=1),
                RetrievalCandidate(chunk_id="p3:1", score=0.85, text="evidence policy robustness", clean_text="evidence policy robustness", paper_id="p3", page_start=1),
            ]

            def _run_once(question: str) -> dict[str, object]:
                args = Namespace(
                    q=question,
                    mode="hybrid",
                    chunks=str(chunks),
                    bm25_index=str(bm25_idx),
                    vec_index=str(vec_idx),
                    config=str(cfg),
                    top_k=5,
                    top_evidence=5,
                    embed_index=str(base / "embed.json"),
                    session_id="m8-natural-two-turn",
                    session_store=session_store,
                    clear_session=False,
                )
                with (
                    patch("app.qa.retrieve_candidates", return_value=cands),
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    code = run_qa(args)
                    self.assertEqual(code, 0)
                run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
                return json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))

            round1 = _run_once("帮我总结这个知识库最值得关注的方向")
            round2 = _run_once("那下一步我该先追问什么？")
            for report in (round1, round2):
                self.assertEqual(report.get("decision"), "answer")
                text = str(report.get("answer", ""))
                self.assertNotIn("Evidence Policy Gate", text)
                self.assertNotIn("无法回答", text)
                self.assertNotIn("证据不足", text)

    def test_natural_three_turn_regression_third_turn_forces_partial_answer(self) -> None:
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
                "assistant_mode_clarify_limit: 2\n"
                "assistant_mode_force_partial_answer_on_limit: true\n"
                "evidence_policy_enforced: false\n"
                "sufficiency_gate_enabled: true\n"
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            session_store = str(base / "session_store.json")
            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.95, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.90, text="rerank diagnostics", clean_text="rerank diagnostics", paper_id="p1", page_start=2),
            ]

            def _run_once(question: str) -> dict[str, object]:
                args = Namespace(
                    q=question,
                    mode="hybrid",
                    chunks=str(chunks),
                    bm25_index=str(bm25_idx),
                    vec_index=str(vec_idx),
                    config=str(cfg),
                    top_k=5,
                    top_evidence=5,
                    embed_index=str(base / "embed.json"),
                    session_id="m8-natural-three-turn",
                    session_store=session_store,
                    clear_session=False,
                )
                with (
                    patch("app.qa.retrieve_candidates", return_value=cands),
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    code = run_qa(args)
                    self.assertEqual(code, 0)
                run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
                return json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))

            round1 = _run_once("帮我总结这个知识库重点方向")
            round2 = _run_once("再总结一下这个知识库重点方向")
            round3 = _run_once("继续总结这个知识库重点方向")

            self.assertEqual(round1.get("decision"), "clarify")
            self.assertEqual(round2.get("decision"), "clarify")
            self.assertEqual(round3.get("decision"), "answer")
            self.assertTrue(round3.get("clarify_limit_hit"))
            self.assertTrue(round3.get("forced_partial_answer"))
            self.assertIn("低置信", str(round3.get("answer", "")))

    def test_session_reset_no_constraint_pollution_and_out_of_corpus_refuse(self) -> None:
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
                "sufficiency_topic_match_threshold: 0.2\n"
                "sufficiency_key_element_min_coverage: 1.0\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            session_store = str(base / "session_store.json")

            args1 = Namespace(
                q="这篇论文的方法步骤和准确率在什么实验条件下得到？",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-reset-check",
                session_store=session_store,
                clear_session=False,
            )
            args2 = Namespace(
                q="帮我总结这个知识库最值得关注的方向",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-reset-check",
                session_store=session_store,
                clear_session=True,
            )
            args3 = Namespace(
                q="纽约明天的天气如何？",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-reset-check",
                session_store=session_store,
                clear_session=False,
            )
            clarify_cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method steps are summarized without metrics", clean_text="method steps are summarized without metrics", paper_id="p1", page_start=2),
            ]
            summary_cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.95, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p2:1", score=0.90, text="rerank diagnostics", clean_text="rerank diagnostics", paper_id="p2", page_start=1),
                RetrievalCandidate(chunk_id="p3:1", score=0.85, text="evidence policy robustness", clean_text="evidence policy robustness", paper_id="p3", page_start=1),
            ]
            ooc_cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.7, text="retrieval architecture", clean_text="retrieval architecture", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.6, text="rerank diagnostics", clean_text="rerank diagnostics", paper_id="p1", page_start=2),
            ]

            with patch("sys.stdout", new_callable=io.StringIO):
                with patch("app.qa.retrieve_candidates", return_value=clarify_cands):
                    self.assertEqual(run_qa(args1), 0)
                with patch("app.qa.retrieve_candidates", return_value=summary_cands):
                    self.assertEqual(run_qa(args2), 0)
                with patch("app.qa.retrieve_candidates", return_value=ooc_cands):
                    self.assertEqual(run_qa(args3), 0)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            trace_reset = json.loads((run_dirs[-2] / "run_trace.json").read_text(encoding="utf-8"))
            report_ooc = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(trace_reset.get("session_reset_applied"))
            audit = trace_reset.get("session_reset_audit", {})
            self.assertFalse(audit.get("constraints_inherited_after_reset"))
            self.assertIn(report_ooc.get("decision"), {"refuse", "clarify"})

    def test_run_qa_mixed_style_prompt_with_uncertainty_sentence_does_not_false_refuse(self) -> None:
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
                "intent_router_enabled: true\n"
                "sufficiency_gate_enabled: true\n"
                "sufficiency_topic_match_threshold: 0.0\n"
                "sufficiency_key_element_min_coverage: 0.0\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="Transformer是什么，有什么用，用中文回答我",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
                session_id="m8-it-mixed-style",
                session_store=str(base / "session_store.json"),
                clear_session=False,
            )
            cands = [
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=0.9,
                    text="Transformer is defined as a self-attention architecture.",
                    clean_text="Transformer is defined as a self-attention architecture.",
                    paper_id="p1",
                    page_start=1,
                ),
                RetrievalCandidate(
                    chunk_id="p1:2",
                    score=0.8,
                    text="This section explains model components and usage scenarios.",
                    clean_text="This section explains model components and usage scenarios.",
                    paper_id="p1",
                    page_start=2,
                ),
            ]
            expected_answer = (
                "Transformer is defined as a self-attention architecture. "
                "然而，证据中没有明确说明 Transformer 的具体用途，因此信息不足。"
            )
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa._build_answer",
                    return_value=(
                        expected_answer,
                        [{"chunk_id": "p1:1", "paper_id": "p1", "section_page": "p.1"}],
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
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report.get("decision"), "answer")
            self.assertEqual(report.get("final_refuse_source"), None)
            self.assertEqual(report.get("answer"), expected_answer)
            self.assertNotIn("Evidence Policy Gate", str(report.get("answer", "")))


if __name__ == "__main__":
    unittest.main()
