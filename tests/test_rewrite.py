from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from app.config import PipelineConfig
from app.rewrite import apply_state_aware_rewrite_guard, rewrite_query


class RewriteTests(unittest.TestCase):
    def test_meta_guard_rewrites_status_complaint_to_fact_query(self) -> None:
        result = apply_state_aware_rewrite_guard(
            user_input="Why does it lack of evidences?",
            standalone_query="Transformer 有什么用处 由什么组成 Why does it lack of evidences?",
            entities_from_history=["Transformer"],
            last_turn_decision="answer_with_evidence",
            last_turn_warnings=[],
        )
        self.assertTrue(result.rewrite_meta_detected)
        self.assertTrue(result.rewrite_guard_applied)
        self.assertIn("Transformer", result.standalone_query)
        self.assertNotIn("lack", result.standalone_query.lower())
        self.assertNotIn("evidence", result.standalone_query.lower())

    def test_meta_guard_prioritizes_repair_when_previous_turn_insufficient(self) -> None:
        result = apply_state_aware_rewrite_guard(
            user_input="你没回答全，为什么？",
            standalone_query="你没回答全，为什么？",
            entities_from_history=["RAG"],
            last_turn_decision="insufficient_evidence",
            last_turn_warnings=["insufficient_evidence_for_answer"],
        )
        self.assertTrue(result.rewrite_meta_detected)
        self.assertEqual(result.rewrite_guard_strategy, "meta_question_insufficient_evidence_repair")
        self.assertIn("RAG", result.standalone_query)

    def test_meta_guard_cleans_mechanical_concat_even_without_meta(self) -> None:
        result = apply_state_aware_rewrite_guard(
            user_input="Transformer components",
            standalone_query="Transformer components Transformer components",
            entities_from_history=["Transformer"],
            last_turn_decision=None,
            last_turn_warnings=[],
        )
        self.assertTrue(result.rewrite_guard_applied)
        self.assertIn("Transformer", result.standalone_query)
        self.assertNotEqual(result.standalone_query.lower(), "transformer components transformer components")

    def test_term_preservation_keeps_metrics(self) -> None:
        cfg = PipelineConfig()
        result = rewrite_query("Can you explain the F1 and BLEU improvements?", cfg)
        self.assertIn("F1", result.rewritten_query)
        self.assertIn("BLEU", result.rewritten_query)
        self.assertIn("term_preservation", result.strategy_hits)

    def test_keyword_expansion_adds_synonyms(self) -> None:
        cfg = PipelineConfig(
            rewrite_synonyms={"citation": ["reference", "bibliography"]},
            rewrite_max_keywords=10,
        )
        result = rewrite_query("citation quality", cfg)
        self.assertIn("citation", result.keywords_entities["keywords"])
        self.assertIn("reference", result.keywords_entities["keywords"])
        self.assertIn("keyword_expansion", result.strategy_hits)

    def test_question_to_retrieval_sentence_removes_filler(self) -> None:
        cfg = PipelineConfig()
        result = rewrite_query("Please help me what is the key method used?", cfg)
        self.assertNotIn("please", result.rewritten_query.lower())
        self.assertIn("question_to_retrieval_sentence", result.strategy_hits)

    def test_rewrite_disabled_returns_original(self) -> None:
        cfg = PipelineConfig(rewrite_enabled=False)
        question = "What is the method?"
        result = rewrite_query(question, cfg)
        self.assertEqual(result.rewritten_query, question)
        self.assertEqual(result.strategy_hits, ["rewrite_disabled"])
        self.assertEqual(result.rewrite_rule_query, question)
        self.assertIsNone(result.rewrite_llm_query)

    def test_llm_optional_flag_falls_back_when_enabled(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with patch.dict("os.environ", {}, clear=True):
            result = rewrite_query("What is citation method?", cfg)
        self.assertFalse(result.llm_used)
        self.assertTrue(result.llm_fallback)
        self.assertIn("llm_missing_api_key_fallback_to_rules", result.strategy_hits)
        self.assertIsNone(result.rewrite_llm_query)
        self.assertIsNotNone(result.llm_diagnostics)
        self.assertEqual(result.llm_diagnostics.get("stage"), "rewrite")
        self.assertEqual(result.llm_diagnostics.get("reason"), "missing_api_key")

    def test_llm_rewrite_success_uses_llm_query(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": True, "content": "citation method F1", "reason": None})(),
            ),
        ):
            result = rewrite_query("What is citation method with F1?", cfg, scope_mode="open")
        self.assertTrue(result.llm_used)
        self.assertFalse(result.llm_fallback)
        self.assertEqual(result.rewrite_llm_query, "citation method F1")
        self.assertEqual(result.rewritten_query, "citation method F1")
        self.assertIn("llm_rewrite_applied", result.strategy_hits)
        self.assertIsNone(result.llm_diagnostics)

    def test_llm_rewrite_uses_global_timeout_ms(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True, llm_timeout_ms=12345)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                autospec=True,
                return_value=type("R", (), {"ok": True, "content": "citation method", "reason": None})(),
            ) as mocked_call,
        ):
            result = rewrite_query("What is citation method?", cfg, scope_mode="open")
        self.assertTrue(result.llm_used)
        self.assertEqual(mocked_call.call_args.kwargs.get("timeout_ms"), 12345)

    def test_llm_rewrite_api_base_changes_with_config_only(self) -> None:
        cfg_primary = PipelineConfig(
            rewrite_use_llm=True,
            rewrite_llm_api_base="https://api.primary.example.com/v1",
        )
        cfg_secondary = PipelineConfig(
            rewrite_use_llm=True,
            rewrite_llm_api_base="https://api.secondary.example.com/v1",
        )
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                autospec=True,
                return_value=type("R", (), {"ok": True, "content": "citation method", "reason": None})(),
            ) as mocked_call,
        ):
            out1 = rewrite_query("What is citation method?", cfg_primary, scope_mode="open")
            out2 = rewrite_query("What is citation method?", cfg_secondary, scope_mode="open")
        self.assertTrue(out1.llm_used)
        self.assertTrue(out2.llm_used)
        self.assertEqual(mocked_call.call_count, 2)
        first_base = mocked_call.call_args_list[0].kwargs.get("api_base")
        second_base = mocked_call.call_args_list[1].kwargs.get("api_base")
        self.assertEqual(first_base, "https://api.primary.example.com/v1")
        self.assertEqual(second_base, "https://api.secondary.example.com/v1")

    def test_llm_rewrite_timeout_falls_back(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": False, "content": None, "reason": "timeout"})(),
            ),
        ):
            result = rewrite_query("What is citation method?", cfg, scope_mode="open")
        self.assertFalse(result.llm_used)
        self.assertTrue(result.llm_fallback)
        self.assertIn("llm_timeout_fallback_to_rules", result.strategy_hits)
        self.assertIsNotNone(result.llm_diagnostics)
        self.assertEqual(result.llm_diagnostics.get("fallback_warning"), "llm_timeout_fallback_to_rules")

    def test_llm_rewrite_rate_limit_falls_back(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": False, "content": None, "reason": "rate_limit"})(),
            ),
        ):
            result = rewrite_query("What is citation method?", cfg, scope_mode="open")
        self.assertFalse(result.llm_used)
        self.assertTrue(result.llm_fallback)
        self.assertIn("llm_rate_limit_fallback_to_rules", result.strategy_hits)

    def test_llm_rewrite_empty_response_falls_back(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": False, "content": None, "reason": "empty_response"})(),
            ),
        ):
            result = rewrite_query("What is citation method?", cfg, scope_mode="open")
        self.assertFalse(result.llm_used)
        self.assertTrue(result.llm_fallback)
        self.assertIn("llm_empty_response_fallback_to_rules", result.strategy_hits)

    def test_llm_polluted_status_query_fallback_records_rewrite_notes(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": True, "content": "Why no evidence in answer", "reason": None})(),
            ),
        ):
            result = rewrite_query("What is citation method?", cfg, scope_mode="open")
        self.assertFalse(result.llm_used)
        self.assertTrue(result.llm_fallback)
        self.assertIn("llm_polluted_status_query_fallback_to_rules", result.strategy_hits)
        self.assertEqual(result.rewrite_notes, "llm_polluted_status_query_fallback_to_rules")

    def test_llm_out_of_scope_fallback_records_rewrite_notes(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type(
                    "R",
                    (),
                    {"ok": True, "content": "alpha nebula galaxy telescope orbit comet cluster vacuum", "reason": None},
                )(),
            ),
        ):
            result = rewrite_query("alpha beta gamma delta epsilon", cfg, scope_mode="open")
        self.assertFalse(result.llm_used)
        self.assertTrue(result.llm_fallback)
        self.assertIn("llm_out_of_scope_fallback_to_rules", result.strategy_hits)
        self.assertEqual(result.rewrite_notes, "llm_out_of_scope_fallback_to_rules")

    def test_clarify_scope_skips_llm_rewrite(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with patch("app.rewrite.call_chat_completion") as mocked:
            result = rewrite_query("What is citation method?", cfg, scope_mode="clarify_scope")
        self.assertEqual(result.rewritten_query, result.rewrite_rule_query)
        self.assertIn("llm_skipped_clarify_scope", result.strategy_hits)
        mocked.assert_not_called()

    def test_fallback_disabled_skips_llm_attempt(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True, llm_fallback_enabled=False)
        with patch("app.rewrite.call_chat_completion") as mocked:
            result = rewrite_query("What is citation method?", cfg, scope_mode="open")
        self.assertFalse(result.llm_used)
        self.assertFalse(result.llm_fallback)
        self.assertIn("llm_fallback_disabled_skip_llm", result.strategy_hits)
        mocked.assert_not_called()

    def test_empty_question_has_non_empty_fallback_query(self) -> None:
        cfg = PipelineConfig()
        result = rewrite_query("   ", cfg)
        self.assertEqual(result.rewritten_query, "paper overview")
        self.assertIn("empty_input_fallback", result.strategy_hits)

    def test_keyword_expansion_supports_chinese_tokens(self) -> None:
        cfg = PipelineConfig(
            rewrite_synonyms={"引用": ["reference", "citation"]},
            rewrite_max_keywords=10,
        )
        result = rewrite_query("这篇论文的引用是什么", cfg)
        self.assertIn("引用", result.keywords_entities["keywords"])
        self.assertIn("reference", result.keywords_entities["keywords"])
        self.assertIn("keyword_expansion", result.strategy_hits)

    def test_compound_tokens_are_not_split(self) -> None:
        cfg = PipelineConfig()
        result = rewrite_query("Compare GUESS-18 and PLA/BPST Top-1", cfg)
        self.assertIn("guess-18", result.keywords_entities["keywords"])
        self.assertIn("pla/bpst", result.keywords_entities["keywords"])

    def test_keyword_budget_filters_noise_terms(self) -> None:
        cfg = PipelineConfig(
            rewrite_synonyms={"citation": ["reference"]},
            rewrite_max_keywords=3,
        )
        result = rewrite_query("What paper work citation?", cfg)
        keywords = result.keywords_entities["keywords"]
        self.assertNotIn("what", keywords)
        self.assertNotIn("paper", keywords)
        self.assertNotIn("work", keywords)
        self.assertIn("citation", keywords)
        self.assertIn("reference", keywords)

    def test_chinese_fragment_match_avoids_false_positive(self) -> None:
        cfg = PipelineConfig(
            rewrite_synonyms={"实验": ["experiment"]},
            rewrite_max_keywords=10,
        )
        result = rewrite_query("实验室安全规范", cfg)
        self.assertNotIn("experiment", result.keywords_entities["keywords"])
        self.assertNotIn("keyword_expansion", result.strategy_hits)

    def test_rewrite_result_contains_meta_guard_fields(self) -> None:
        cfg = PipelineConfig()
        result = rewrite_query("What is citation method?", cfg)
        self.assertFalse(result.rewrite_meta_detected)
        self.assertFalse(result.rewrite_guard_applied)
        self.assertEqual(result.rewrite_guard_strategy, "none")

    def test_meta_guard_samples_have_no_mechanical_concat(self) -> None:
        samples = [
            "Why does it lack of evidences?",
            "你没回答全，为什么？",
            "再找找具体组成",
            "没有证据吗",
            "why no evidence",
            "回答不完整，补充下",
            "still no proof?",
            "你是不是没找到证据",
            "please find more concrete components",
            "lack of evidences, retry",
        ]
        for text in samples:
            with self.subTest(text=text):
                result = apply_state_aware_rewrite_guard(
                    user_input=text,
                    standalone_query=f"Transformer 有什么用处 由什么组成 {text}",
                    entities_from_history=["Transformer"],
                    last_turn_decision="answer_with_evidence",
                    last_turn_warnings=["insufficient_evidence_for_answer"],
                )
                self.assertTrue(result.rewrite_meta_detected)
                self.assertIn("Transformer", result.standalone_query)
                self.assertNotIn("why", result.standalone_query.lower())
                self.assertNotIn("证据", result.standalone_query)

    def test_meta_guard_no_history_entities_keeps_domain_overlap(self) -> None:
        user_input = "回答不完整，请补充"
        standalone_query = "Transformer 的训练目标是什么 回答不完整，请补充"
        result = apply_state_aware_rewrite_guard(
            user_input=user_input,
            standalone_query=standalone_query,
            entities_from_history=[],
            last_turn_decision="answer_with_evidence",
            last_turn_warnings=[],
        )
        self.assertTrue(result.rewrite_meta_detected)
        self.assertEqual(result.rewrite_guard_strategy, "meta_question_no_entity_fallback")
        original_tokens = {
            t.lower()
            for t in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", standalone_query)
            if t.strip() and t not in {"回答", "不完整", "补充"}
        }
        rewritten_tokens = {
            t.lower() for t in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", result.standalone_query) if t.strip()
        }
        self.assertTrue(original_tokens.intersection(rewritten_tokens))

    def test_control_intent_reuses_anchor_query_not_control_phrase(self) -> None:
        cfg = PipelineConfig()
        result = rewrite_query(
            "用中文回答我",
            cfg,
            scope_mode="open",
            intent_type="style_control",
            anchor_query="Transformer 架构 组件",
        )
        self.assertEqual(result.rewritten_query, "Transformer 架构 组件")
        self.assertIn("control_intent_anchor_query_reused", result.strategy_hits)
        self.assertNotIn("用中文回答我", result.rewritten_query)

    def test_rewrite_quality_observability_exposes_entity_loss(self) -> None:
        cfg = PipelineConfig()
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": True, "content": "BERT benchmark summary", "reason": None})(),
            ),
        ):
            result = rewrite_query("Compare BERT on SQuAD 2020 benchmark", PipelineConfig(rewrite_use_llm=True), scope_mode="open")
        self.assertGreaterEqual(result.rewrite_entity_preservation_ratio, 0.8)
        self.assertGreater(result.rewrite_quality_score, 0.7)
        self.assertIn("BERT", result.rewritten_query)

    def test_llm_rewrite_term_loss_repaired_with_constraints(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with (
            patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
            patch(
                "app.rewrite.call_chat_completion",
                return_value=type("R", (), {"ok": True, "content": "benchmark summary only", "reason": None})(),
            ),
        ):
            result = rewrite_query("Compare BERT on SQuAD benchmark", cfg, scope_mode="open")
        self.assertTrue(result.llm_used)
        self.assertFalse(result.llm_fallback)
        self.assertIn("llm_rewrite_repaired_with_constraints", result.strategy_hits)
        self.assertIn("BERT", result.rewritten_query)
        self.assertIn("SQuAD", result.rewritten_query)


if __name__ == "__main__":
    unittest.main()
