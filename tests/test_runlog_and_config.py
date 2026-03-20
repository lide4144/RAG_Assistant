from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import PipelineConfig, load_and_validate_config, validate_config
from app.runlog import create_run_dir, validate_trace_schema


class RunlogTests(unittest.TestCase):
    def test_create_run_dir_is_unique_with_same_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d1 = create_run_dir(tmp, timestamp="20260217_170000")
            d2 = create_run_dir(tmp, timestamp="20260217_170000")
            self.assertNotEqual(d1, d2)
            self.assertTrue(d1.exists())
            self.assertTrue(d2.exists())
            self.assertTrue(d2.name.startswith("20260217_170000_"))

    def test_validate_trace_schema_accepts_m2_optional_fields(self) -> None:
        trace = {
            "input_question": "q",
            "session_id": "s1",
            "session_reset": False,
            "turn_number": 1,
            "history_used_turns": 0,
            "history_tokens_est": 0,
            "history_trimmed_turns": 0,
            "coreference_resolved": False,
            "standalone_query": "q",
            "intent_type": "retrieval_query",
            "anchor_query": None,
            "topic_query_source": "user_query",
            "prompt_tokens_est": 123,
            "discarded_evidence": [],
            "discarded_evidence_count": 0,
            "context_overflow_fallback": False,
            "rewrite_query": "q",
            "retrieval_top_k": [],
            "expansion_added_chunks": [],
            "rerank_top_n": [],
            "rerank_score_distribution": {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0},
            "final_decision": "answer_with_evidence",
            "decision": "answer",
            "decision_reason": "证据充分，可进入回答。",
            "final_interaction_authority": "planner",
            "interaction_decision_source": "planner:execute",
            "final_user_visible_posture": "execute",
            "kernel_constraint_summary": [],
            "guardrail_blocked": False,
            "posture_override_forbidden": False,
            "constraints_envelope": [],
            "clarify_questions": [],
            "sufficiency_gate": {"enabled": True, "decision": "answer", "reason": "证据充分，可进入回答。"},
            "final_answer": "a",
            "mode": "hybrid",
            "dense_backend": "embedding",
            "graph_expand_alpha": 2.0,
            "expansion_budget": 3,
            "final_evidence": [],
            "question": "q",
            "scope_mode": "open",
            "scope_reason": {"rule": "open_by_default_or_has_paper_clue"},
            "query_used": "q",
            "calibrated_query": "q calibration",
            "calibration_reason": {"rule": "intent_calibration", "matched_intents": []},
            "query_retry_used": False,
            "query_retry_reason": None,
            "answer_llm_diagnostics": None,
            "answer_citations": [],
            "output_warnings": [],
            "embedding_enabled": False,
            "embedding_provider": "siliconflow",
            "embedding_model": "BAAI/bge-large-zh-v1.5",
            "embedding_dim": 0,
            "embedding_batch_size": 32,
            "embedding_cache_enabled": True,
            "embedding_cache_hit": False,
            "embedding_cache_hits": 0,
            "embedding_cache_miss": 0,
            "embedding_api_calls": 0,
            "embedding_query_time_ms": 0,
            "embedding_build_time_ms": 0,
            "embedding_failed_count": 0,
            "embedding_failed_chunk_ids": [],
            "embedding_batch_failures": [],
            "rate_limited_count": 0,
            "backoff_total_ms": 0,
            "truncated_count": 0,
            "skipped_over_limit_count": 0,
            "skipped_empty": 0,
            "skipped_empty_chunk_ids": [],
            "dense_score_type": "cosine",
            "hybrid_fusion_weight": 0.6,
            "rewrite_rule_query": "q",
            "rewrite_llm_query": None,
            "keywords_entities": {"keywords": ["q"], "entities": []},
            "strategy_hits": ["term_preservation"],
            "rewrite_llm_used": False,
            "rewrite_llm_fallback": False,
            "rewrite_meta_detected": False,
            "rewrite_guard_applied": False,
            "rewrite_guard_strategy": "no_guard",
            "rewrite_notes": None,
            "answer_stream_enabled": False,
            "answer_stream_used": False,
            "answer_stream_first_token_ms": None,
            "answer_stream_fallback_reason": None,
            "answer_stream_events": [],
            "rewrite_llm_diagnostics": None,
            "papers_ranked": [],
            "evidence_grouped": [],
        }
        ok, errors = validate_trace_schema(trace)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

        trace["embedding_batch_failures"] = [
            {
                "batch_index": 1,
                "batch_total": 3,
                "count": 32,
                "status_code": 429,
                "trace_id": "trace-id",
                "response_body": "rate limited",
            }
        ]
        ok, errors = validate_trace_schema(trace)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

        trace["embedding_batch_failures"] = [{"status_code": 429}]
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("embedding_batch_failures[0] missing key: count" in err for err in errors))

        trace["embedding_batch_failures"] = []
        trace["expansion_added_chunks"] = [{"chunk_id": "c:1", "source": "graph_expand"}]
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("expansion_added_chunks[0] missing key: dense_backend" in err for err in errors))

        trace["expansion_added_chunks"] = []
        trace["answer_citations"] = [{"chunk_id": "c:1", "paper_id": "p1"}]
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("answer_citations[0] missing key: section_page" in err for err in errors))

        trace["answer_citations"] = [{"chunk_id": "c:1", "paper_id": "p1", "section_page": "p.1"}]
        ok, errors = validate_trace_schema(trace)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

        trace["output_warnings"] = ["llm_answer_timeout_fallback_to_template"]
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("answer_llm_diagnostics required" in err for err in errors))

        trace["answer_llm_diagnostics"] = {
            "stage": "answer",
            "provider": "siliconflow",
            "model": "m",
            "reason": "timeout",
            "status_code": None,
            "attempts_used": 2,
            "max_retries": 1,
            "elapsed_ms": 12001,
            "fallback_warning": "llm_answer_timeout_fallback_to_template",
            "timestamp": "2026-02-20T14:00:00Z",
        }
        ok, errors = validate_trace_schema(trace)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

        trace["answer_llm_diagnostics"]["response_body"] = "raw"
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("must not contain sensitive field: response_body" in err for err in errors))

        trace["answer_llm_diagnostics"].pop("response_body", None)
        trace["answer_stream_events"] = [{"event_index": 0, "t_ms": 5, "delta_chars": 10, "cumulative_chars": 10}]
        ok, errors = validate_trace_schema(trace)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

        trace["answer_stream_events"] = [{"event_index": "bad"}]
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("answer_stream_events[0].event_index must be int" in err for err in errors))

        trace["answer_stream_events"] = []
        trace["intent_type"] = "bad_intent"
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("intent_type must be one of retrieval_query|style_control|format_control|continuation_control" in err for err in errors))

        trace["intent_type"] = "retrieval_query"
        trace["topic_query_source"] = "bad_source"
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("topic_query_source must be one of user_query|anchor_query" in err for err in errors))

        trace["topic_query_source"] = "user_query"
        trace["intent_confidence"] = 1.2
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("intent_confidence must satisfy 0 <= value <= 1" in err for err in errors))

        trace["intent_confidence"] = 0.8
        trace["clarify_questions"] = ["q1", "q2"]
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("clarify_questions must contain at most 1 item" in err for err in errors))

        trace["clarify_questions"] = []
        trace["clarify_limit_hit"] = "bad"
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("clarify_limit_hit must be bool or null" in err for err in errors))

        trace["clarify_limit_hit"] = False
        trace["posture_override_forbidden"] = True
        ok, errors = validate_trace_schema(trace)
        self.assertFalse(ok)
        self.assertTrue(any("posture_override_forbidden must not be true" in err for err in errors))


class ConfigTests(unittest.TestCase):
    def test_validate_config_falls_back_for_invalid_chunk_params(self) -> None:
        invalid = PipelineConfig(
            chunk_size=100,
            overlap=999,
            table_list_downweight=2.0,
            front_matter_downweight=2.0,
            reference_downweight=-1.0,
        )
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.chunk_size, 400)
        self.assertEqual(validated.overlap, 50)
        self.assertEqual(validated.table_list_downweight, 0.5)
        self.assertEqual(validated.front_matter_downweight, 0.3)
        self.assertEqual(validated.reference_downweight, 0.3)
        self.assertGreaterEqual(len(warnings), 1)

    def test_validate_config_rerank_top_n_must_be_positive(self) -> None:
        invalid = PipelineConfig()
        invalid.rerank.top_n = 0
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.rerank.top_n, 8)
        self.assertTrue(any("rerank.top_n" in w for w in warnings))

    def test_validate_config_sufficiency_threshold_fields(self) -> None:
        invalid = PipelineConfig(
            sufficiency_topic_match_threshold=1.5,
            sufficiency_key_element_min_coverage=-0.2,
        )
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.sufficiency_topic_match_threshold, 0.15)
        self.assertEqual(validated.sufficiency_key_element_min_coverage, 1.0)
        self.assertTrue(any("sufficiency_topic_match_threshold" in w for w in warnings))
        self.assertTrue(any("sufficiency_key_element_min_coverage" in w for w in warnings))

    def test_validate_config_intent_control_min_confidence_range(self) -> None:
        invalid = PipelineConfig(intent_control_min_confidence=1.5)
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.intent_control_min_confidence, 0.75)
        self.assertTrue(any("intent_control_min_confidence" in w for w in warnings))

    def test_validate_config_assistant_mode_clarify_limit_positive(self) -> None:
        invalid = PipelineConfig(assistant_mode_clarify_limit=0)
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.assistant_mode_clarify_limit, 2)
        self.assertTrue(any("assistant_mode_clarify_limit" in w for w in warnings))

    def test_load_and_validate_config_with_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg.yaml"
            cfg.write_text(
                "chunk_size: 450\n"
                "overlap: 40\n"
                "top_k_retrieval: 10\n",
                encoding="utf-8",
            )
            loaded, warnings = load_and_validate_config(cfg)
            self.assertEqual(loaded.chunk_size, 450)
            self.assertEqual(loaded.overlap, 40)
            self.assertEqual(loaded.top_k_retrieval, 10)
            self.assertEqual(warnings, [])

    def test_load_and_validate_config_supports_meta_guard_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg.yaml"
            cfg.write_text("rewrite_meta_guard_enabled: false\n", encoding="utf-8")
            loaded, warnings = load_and_validate_config(cfg)
            self.assertFalse(loaded.rewrite_meta_guard_enabled)
            self.assertEqual(warnings, [])

    def test_validate_config_rewrite_fields(self) -> None:
        invalid = PipelineConfig(
            rewrite_max_keywords=0,
            rewrite_synonyms={"k": "v"},  # type: ignore[arg-type]
            rewrite_meta_patterns=["", "  "],
            rewrite_meta_noise_terms="bad-type",  # type: ignore[arg-type]
            llm_timeout_ms=0,
            answer_llm_timeout_ms=0,
            llm_max_retries=-1,
            max_context_tokens=0,
            rewrite_llm_provider="",
            rewrite_llm_model="",
            answer_llm_provider="",
            answer_llm_model="",
        )
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.rewrite_max_keywords, 12)
        self.assertEqual(validated.rewrite_synonyms.get("k"), ["v"])
        self.assertEqual(validated.llm_timeout_ms, 12000)
        self.assertEqual(validated.answer_llm_timeout_ms, 30000)
        self.assertEqual(validated.llm_max_retries, 1)
        self.assertEqual(validated.max_context_tokens, 6000)
        self.assertEqual(validated.rewrite_llm_provider, "siliconflow")
        self.assertEqual(validated.answer_llm_model, "Pro/deepseek-ai/DeepSeek-V3.2")
        self.assertTrue(validated.rewrite_meta_patterns)
        self.assertTrue(validated.rewrite_meta_noise_terms)
        self.assertGreaterEqual(len(warnings), 1)

    def test_validate_config_warns_when_llm_enabled_without_api_key(self) -> None:
        cfg = PipelineConfig(rewrite_use_llm=True)
        with patch.dict("os.environ", {}, clear=True):
            _, warnings = validate_config(cfg)
        self.assertTrue(any("LLM route API key env missing" in w for w in warnings))

    def test_validate_config_normalizes_llm_router_fields(self) -> None:
        cfg = PipelineConfig(
            rewrite_llm_api_base="",
            rewrite_llm_api_key_env="",
            answer_llm_api_base="",
            answer_llm_api_key_env="",
            llm_router_retry=-1,
            llm_router_cooldown_sec=-2,
            llm_router_failure_threshold=0,
        )
        validated, warnings = validate_config(cfg)
        self.assertEqual(validated.rewrite_llm_api_base, "https://api.siliconflow.cn/v1")
        self.assertEqual(validated.answer_llm_api_key_env, "SILICONFLOW_API_KEY")
        self.assertEqual(validated.llm_router_retry, 1)
        self.assertEqual(validated.llm_router_cooldown_sec, 60)
        self.assertEqual(validated.llm_router_failure_threshold, 2)
        self.assertTrue(any("llm_router_failure_threshold" in w for w in warnings))

    def test_validate_config_graph_expansion_fields(self) -> None:
        invalid = PipelineConfig(
            graph_expand_alpha=-1.0,
            graph_expand_max_candidates=0,
            graph_path="",
            graph_expand_author_keywords=[],
            graph_expand_reference_keywords=[],
        )
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.graph_expand_alpha, 2.0)
        self.assertEqual(validated.graph_expand_max_candidates, 200)
        self.assertEqual(validated.graph_path, "data/processed/graph.json")
        self.assertTrue(validated.graph_expand_author_keywords)
        self.assertTrue(validated.graph_expand_reference_keywords)
        self.assertGreaterEqual(len(warnings), 1)

    def test_validate_config_graph_entity_llm_fields(self) -> None:
        invalid = PipelineConfig(
            graph_entity_llm_provider="",
            graph_entity_llm_base_url="",
            graph_entity_llm_api_key_env="",
            graph_entity_llm_model="",
            graph_entity_llm_timeout_ms=0,
            graph_entity_llm_max_concurrency=0,
            graph_entity_llm_max_retries=-1,
        )
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.graph_entity_llm_provider, "siliconflow")
        self.assertEqual(validated.graph_entity_llm_base_url, "https://api.siliconflow.cn/v1")
        self.assertEqual(validated.graph_entity_llm_api_key_env, "SILICONFLOW_API_KEY")
        self.assertEqual(validated.graph_entity_llm_model, "Pro/deepseek-ai/DeepSeek-V3.2")
        self.assertEqual(validated.graph_entity_llm_timeout_ms, 12000)
        self.assertEqual(validated.graph_entity_llm_max_concurrency, 4)
        self.assertEqual(validated.graph_entity_llm_max_retries, 1)
        self.assertGreaterEqual(len(warnings), 1)

    def test_validate_config_marker_fields(self) -> None:
        invalid = PipelineConfig(
            marker_timeout_sec=0,
            title_confidence_threshold=2.0,
            title_blacklist_patterns=[],
        )
        validated, warnings = validate_config(invalid)
        self.assertEqual(validated.marker_timeout_sec, 30.0)
        self.assertEqual(validated.title_confidence_threshold, 0.6)
        self.assertTrue(validated.title_blacklist_patterns)
        self.assertTrue(any("marker_timeout_sec" in w for w in warnings))
        self.assertTrue(any("title_confidence_threshold" in w for w in warnings))
        self.assertTrue(any("title_blacklist_patterns" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
