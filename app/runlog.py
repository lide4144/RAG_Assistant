from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.fs_utils import atomic_text_writer
from app.paths import RUNS_DIR

REQUIRED_KEYS = {
    "input_question",
    "session_reset",
    "rewrite_query",
    "retrieval_top_k",
    "expansion_added_chunks",
    "rerank_top_n",
    "rerank_score_distribution",
    "final_decision",
    "final_answer",
    "prompt_tokens_est",
    "discarded_evidence_count",
    "history_trimmed_turns",
    "context_overflow_fallback",
    "keywords_entities",
    "strategy_hits",
    "rewrite_llm_used",
    "rewrite_llm_fallback",
    "rewrite_meta_detected",
    "rewrite_guard_applied",
    "rewrite_guard_strategy",
    "rewrite_notes",
    "answer_stream_enabled",
    "answer_stream_used",
    "answer_stream_first_token_ms",
    "answer_stream_fallback_reason",
    "rewrite_rule_query",
    "rewrite_llm_query",
    "calibrated_query",
    "calibration_reason",
    "query_retry_used",
    "query_retry_reason",
    "answer_citations",
    "output_warnings",
    "embedding_enabled",
    "embedding_provider",
    "embedding_model",
    "embedding_dim",
    "embedding_batch_size",
    "embedding_cache_enabled",
    "embedding_cache_hit",
    "embedding_cache_hits",
    "embedding_cache_miss",
    "embedding_api_calls",
    "embedding_query_time_ms",
    "embedding_build_time_ms",
    "embedding_failed_count",
    "embedding_failed_chunk_ids",
    "embedding_batch_failures",
    "rate_limited_count",
    "backoff_total_ms",
    "truncated_count",
    "skipped_over_limit_count",
    "skipped_empty",
    "skipped_empty_chunk_ids",
    "dense_score_type",
    "hybrid_fusion_weight",
    "intent_type",
    "anchor_query",
    "topic_query_source",
    "dense_backend",
    "graph_expand_alpha",
    "expansion_budget",
}


def create_run_dir(base_dir: str | Path = RUNS_DIR, timestamp: str | None = None) -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    stem = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base / stem
    suffix = 1
    while candidate.exists():
        candidate = base / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def save_json(data: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(output) as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))


def validate_trace_schema(trace: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    missing = REQUIRED_KEYS - set(trace.keys())
    if missing:
        errors.append(f"missing required keys: {sorted(missing)}")

    for key in ("retrieval_top_k", "expansion_added_chunks", "rerank_top_n"):
        value = trace.get(key)
        if value is not None and not isinstance(value, list):
            errors.append(f"{key} must be list or null")
    rerank_score_distribution = trace.get("rerank_score_distribution")
    if rerank_score_distribution is not None and not isinstance(rerank_score_distribution, dict):
        errors.append("rerank_score_distribution must be object or null")
    expansion_added_chunks = trace.get("expansion_added_chunks")
    if isinstance(expansion_added_chunks, list):
        for i, row in enumerate(expansion_added_chunks):
            if not isinstance(row, dict):
                errors.append(f"expansion_added_chunks[{i}] must be object")
                continue
            for required_key in ("chunk_id", "source", "dense_backend", "retrieval_mode"):
                if required_key not in row:
                    errors.append(f"expansion_added_chunks[{i}] missing key: {required_key}")
            chunk_id = row.get("chunk_id")
            if chunk_id is not None and not isinstance(chunk_id, str):
                errors.append(f"expansion_added_chunks[{i}].chunk_id must be string or null")
            source = row.get("source")
            if source is not None and not isinstance(source, str):
                errors.append(f"expansion_added_chunks[{i}].source must be string or null")
            dense_backend_item = row.get("dense_backend")
            if dense_backend_item is not None and not isinstance(dense_backend_item, str):
                errors.append(f"expansion_added_chunks[{i}].dense_backend must be string or null")
            retrieval_mode = row.get("retrieval_mode")
            if retrieval_mode is not None and not isinstance(retrieval_mode, str):
                errors.append(f"expansion_added_chunks[{i}].retrieval_mode must be string or null")
            for optional_key in ("embedding_provider", "embedding_model", "embedding_version"):
                value = row.get(optional_key)
                if value is not None and not isinstance(value, str):
                    errors.append(f"expansion_added_chunks[{i}].{optional_key} must be string or null")

    for key in ("input_question", "rewrite_query", "final_decision", "final_answer"):
        value = trace.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{key} must be string or null")
    decision = trace.get("decision")
    if decision is not None and not isinstance(decision, str):
        errors.append("decision must be string or null")
    if isinstance(decision, str) and decision not in {"answer", "refuse", "clarify"}:
        errors.append("decision must be one of answer|refuse|clarify")
    decision_reason = trace.get("decision_reason")
    if decision_reason is not None and not isinstance(decision_reason, str):
        errors.append("decision_reason must be string or null")
    final_refuse_source = trace.get("final_refuse_source")
    if final_refuse_source is not None and not isinstance(final_refuse_source, str):
        errors.append("final_refuse_source must be string or null")
    if isinstance(final_refuse_source, str) and final_refuse_source not in {"sufficiency_gate", "evidence_policy_gate"}:
        errors.append("final_refuse_source must be one of sufficiency_gate|evidence_policy_gate")
    clarify_questions = trace.get("clarify_questions")
    if clarify_questions is not None and not isinstance(clarify_questions, list):
        errors.append("clarify_questions must be list or null")
    if isinstance(clarify_questions, list):
        if len(clarify_questions) > 1:
            errors.append("clarify_questions must contain at most 1 item")
        for i, item in enumerate(clarify_questions):
            if not isinstance(item, str):
                errors.append(f"clarify_questions[{i}] must be string")
    history_constraint_dropped = trace.get("history_constraint_dropped")
    if history_constraint_dropped is not None and not isinstance(history_constraint_dropped, bool):
        errors.append("history_constraint_dropped must be bool or null")
    dropped_constraints = trace.get("dropped_constraints")
    if dropped_constraints is not None and not isinstance(dropped_constraints, list):
        errors.append("dropped_constraints must be list or null")
    if isinstance(dropped_constraints, list):
        for i, item in enumerate(dropped_constraints):
            if not isinstance(item, str):
                errors.append(f"dropped_constraints[{i}] must be string")
    assistant_mode_enabled = trace.get("assistant_mode_enabled")
    if assistant_mode_enabled is not None and not isinstance(assistant_mode_enabled, bool):
        errors.append("assistant_mode_enabled must be bool or null")
    assistant_mode_used = trace.get("assistant_mode_used")
    if assistant_mode_used is not None and not isinstance(assistant_mode_used, bool):
        errors.append("assistant_mode_used must be bool or null")
    assistant_summary_suggestions = trace.get("assistant_summary_suggestions")
    if assistant_summary_suggestions is not None and not isinstance(assistant_summary_suggestions, list):
        errors.append("assistant_summary_suggestions must be list or null")
    if isinstance(assistant_summary_suggestions, list):
        for i, item in enumerate(assistant_summary_suggestions):
            if not isinstance(item, str):
                errors.append(f"assistant_summary_suggestions[{i}] must be string")
    clarify_count = trace.get("clarify_count")
    if clarify_count is not None and not isinstance(clarify_count, int):
        errors.append("clarify_count must be int or null")
    if isinstance(clarify_count, int) and clarify_count < 0:
        errors.append("clarify_count must be >= 0")
    clarify_limit_hit = trace.get("clarify_limit_hit")
    if clarify_limit_hit is not None and not isinstance(clarify_limit_hit, bool):
        errors.append("clarify_limit_hit must be bool or null")
    forced_partial_answer = trace.get("forced_partial_answer")
    if forced_partial_answer is not None and not isinstance(forced_partial_answer, bool):
        errors.append("forced_partial_answer must be bool or null")
    gate_trigger_reason = trace.get("gate_trigger_reason")
    if gate_trigger_reason is not None and not isinstance(gate_trigger_reason, list):
        errors.append("gate_trigger_reason must be list or null")
    if isinstance(gate_trigger_reason, list):
        for i, item in enumerate(gate_trigger_reason):
            if not isinstance(item, str):
                errors.append(f"gate_trigger_reason[{i}] must be string")
    session_reset_audit = trace.get("session_reset_audit")
    if session_reset_audit is not None and not isinstance(session_reset_audit, dict):
        errors.append("session_reset_audit must be object or null")
    sufficiency_gate = trace.get("sufficiency_gate")
    if sufficiency_gate is not None and not isinstance(sufficiency_gate, dict):
        errors.append("sufficiency_gate must be object or null")
    session_id = trace.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        errors.append("session_id must be string or null")
    session_reset = trace.get("session_reset")
    if session_reset is not None and not isinstance(session_reset, bool):
        errors.append("session_reset must be bool or null")
    session_reset_applied = trace.get("session_reset_applied")
    if session_reset_applied is not None and not isinstance(session_reset_applied, bool):
        errors.append("session_reset_applied must be bool or null")
    turn_number = trace.get("turn_number")
    if turn_number is not None and not isinstance(turn_number, int):
        errors.append("turn_number must be int or null")
    if isinstance(turn_number, int) and turn_number <= 0:
        errors.append("turn_number must be > 0")
    history_used_turns = trace.get("history_used_turns")
    if history_used_turns is not None and not isinstance(history_used_turns, int):
        errors.append("history_used_turns must be int or null")
    if isinstance(history_used_turns, int) and history_used_turns < 0:
        errors.append("history_used_turns must be >= 0")
    history_tokens_est = trace.get("history_tokens_est")
    if history_tokens_est is not None and not isinstance(history_tokens_est, int):
        errors.append("history_tokens_est must be int or null")
    if isinstance(history_tokens_est, int) and history_tokens_est < 0:
        errors.append("history_tokens_est must be >= 0")
    history_trimmed_turns = trace.get("history_trimmed_turns")
    if history_trimmed_turns is not None and not isinstance(history_trimmed_turns, int):
        errors.append("history_trimmed_turns must be int or null")
    if isinstance(history_trimmed_turns, int) and history_trimmed_turns < 0:
        errors.append("history_trimmed_turns must be >= 0")
    prompt_tokens_est = trace.get("prompt_tokens_est")
    if prompt_tokens_est is not None and not isinstance(prompt_tokens_est, int):
        errors.append("prompt_tokens_est must be int or null")
    if isinstance(prompt_tokens_est, int) and prompt_tokens_est < 0:
        errors.append("prompt_tokens_est must be >= 0")
    discarded_evidence_count = trace.get("discarded_evidence_count")
    if discarded_evidence_count is not None and not isinstance(discarded_evidence_count, int):
        errors.append("discarded_evidence_count must be int or null")
    if isinstance(discarded_evidence_count, int) and discarded_evidence_count < 0:
        errors.append("discarded_evidence_count must be >= 0")
    context_overflow_fallback = trace.get("context_overflow_fallback")
    if context_overflow_fallback is not None and not isinstance(context_overflow_fallback, bool):
        errors.append("context_overflow_fallback must be bool or null")
    discarded_evidence = trace.get("discarded_evidence")
    if discarded_evidence is not None and not isinstance(discarded_evidence, list):
        errors.append("discarded_evidence must be list or null")
    if isinstance(discarded_evidence, list):
        for i, row in enumerate(discarded_evidence):
            if not isinstance(row, dict):
                errors.append(f"discarded_evidence[{i}] must be object")
                continue
            chunk_id = row.get("chunk_id")
            if chunk_id is not None and not isinstance(chunk_id, str):
                errors.append(f"discarded_evidence[{i}].chunk_id must be string or null")
            paper_id = row.get("paper_id")
            if paper_id is not None and not isinstance(paper_id, str):
                errors.append(f"discarded_evidence[{i}].paper_id must be string or null")
    coreference_resolved = trace.get("coreference_resolved")
    if coreference_resolved is not None and not isinstance(coreference_resolved, bool):
        errors.append("coreference_resolved must be bool or null")
    standalone_query = trace.get("standalone_query")
    if standalone_query is not None and not isinstance(standalone_query, str):
        errors.append("standalone_query must be string or null")
    for key in ("is_new_topic", "should_clear_pending_clarify", "planner_used", "planner_fallback", "truncated"):
        value = trace.get(key)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{key} must be bool or null")
    for key in ("relation_to_previous", "planner_source", "planner_fallback_reason", "primary_capability", "strictness"):
        value = trace.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{key} must be string or null")
    planner_confidence = trace.get("planner_confidence")
    if planner_confidence is not None and not isinstance(planner_confidence, (int, float)):
        errors.append("planner_confidence must be number or null")
    action_plan = trace.get("action_plan")
    if action_plan is not None and not isinstance(action_plan, list):
        errors.append("action_plan must be list or null")
    execution_trace = trace.get("execution_trace")
    if execution_trace is not None and not isinstance(execution_trace, list):
        errors.append("execution_trace must be list or null")
    short_circuit = trace.get("short_circuit")
    if short_circuit is not None and not isinstance(short_circuit, dict):
        errors.append("short_circuit must be object or null")
    intent_type = trace.get("intent_type")
    if intent_type is not None and not isinstance(intent_type, str):
        errors.append("intent_type must be string or null")
    if isinstance(intent_type, str) and intent_type not in {
        "retrieval_query",
        "style_control",
        "format_control",
        "continuation_control",
    }:
        errors.append("intent_type must be one of retrieval_query|style_control|format_control|continuation_control")
    intent_confidence = trace.get("intent_confidence")
    if intent_confidence is not None and not isinstance(intent_confidence, (int, float)):
        errors.append("intent_confidence must be number or null")
    if isinstance(intent_confidence, (int, float)) and not 0 <= float(intent_confidence) <= 1:
        errors.append("intent_confidence must satisfy 0 <= value <= 1")
    intent_fallback_reason = trace.get("intent_fallback_reason")
    if intent_fallback_reason is not None and not isinstance(intent_fallback_reason, str):
        errors.append("intent_fallback_reason must be string or null")
    intent_rule_matched = trace.get("intent_rule_matched")
    if intent_rule_matched is not None and not isinstance(intent_rule_matched, str):
        errors.append("intent_rule_matched must be string or null")
    anchor_query = trace.get("anchor_query")
    if anchor_query is not None and not isinstance(anchor_query, str):
        errors.append("anchor_query must be string or null")
    topic_query_source = trace.get("topic_query_source")
    if topic_query_source is not None and not isinstance(topic_query_source, str):
        errors.append("topic_query_source must be string or null")
    if isinstance(topic_query_source, str) and topic_query_source not in {"user_query", "anchor_query"}:
        errors.append("topic_query_source must be one of user_query|anchor_query")
    dense_backend = trace.get("dense_backend")
    if dense_backend is not None and not isinstance(dense_backend, str):
        errors.append("dense_backend must be string or null")

    mode = trace.get("mode")
    if mode is not None and not isinstance(mode, str):
        errors.append("mode must be string or null")

    final_evidence = trace.get("final_evidence")
    if final_evidence is not None and not isinstance(final_evidence, list):
        errors.append("final_evidence must be list or null")

    question = trace.get("question")
    if question is not None and not isinstance(question, str):
        errors.append("question must be string or null")

    scope_mode = trace.get("scope_mode")
    if scope_mode is not None and not isinstance(scope_mode, str):
        errors.append("scope_mode must be string or null")

    scope_reason = trace.get("scope_reason")
    if scope_reason is not None and not isinstance(scope_reason, dict):
        errors.append("scope_reason must be object or null")

    query_used = trace.get("query_used")
    if query_used is not None and not isinstance(query_used, str):
        errors.append("query_used must be string or null")

    papers_ranked = trace.get("papers_ranked")
    if papers_ranked is not None and not isinstance(papers_ranked, list):
        errors.append("papers_ranked must be list or null")

    evidence_grouped = trace.get("evidence_grouped")
    if evidence_grouped is not None and not isinstance(evidence_grouped, list):
        errors.append("evidence_grouped must be list or null")

    keywords_entities = trace.get("keywords_entities")
    if keywords_entities is not None and not isinstance(keywords_entities, dict):
        errors.append("keywords_entities must be object or null")

    strategy_hits = trace.get("strategy_hits")
    if strategy_hits is not None and not isinstance(strategy_hits, list):
        errors.append("strategy_hits must be list or null")

    rewrite_llm_used = trace.get("rewrite_llm_used")
    if rewrite_llm_used is not None and not isinstance(rewrite_llm_used, bool):
        errors.append("rewrite_llm_used must be bool or null")

    rewrite_llm_fallback = trace.get("rewrite_llm_fallback")
    if rewrite_llm_fallback is not None and not isinstance(rewrite_llm_fallback, bool):
        errors.append("rewrite_llm_fallback must be bool or null")
    rewrite_meta_detected = trace.get("rewrite_meta_detected")
    if rewrite_meta_detected is not None and not isinstance(rewrite_meta_detected, bool):
        errors.append("rewrite_meta_detected must be bool or null")

    rewrite_guard_applied = trace.get("rewrite_guard_applied")
    if rewrite_guard_applied is not None and not isinstance(rewrite_guard_applied, bool):
        errors.append("rewrite_guard_applied must be bool or null")

    rewrite_guard_strategy = trace.get("rewrite_guard_strategy")
    if rewrite_guard_strategy is not None and not isinstance(rewrite_guard_strategy, str):
        errors.append("rewrite_guard_strategy must be string or null")

    rewrite_notes = trace.get("rewrite_notes")
    if rewrite_notes is not None and not isinstance(rewrite_notes, str):
        errors.append("rewrite_notes must be string or null")

    answer_stream_enabled = trace.get("answer_stream_enabled")
    if answer_stream_enabled is not None and not isinstance(answer_stream_enabled, bool):
        errors.append("answer_stream_enabled must be bool or null")

    answer_stream_used = trace.get("answer_stream_used")
    if answer_stream_used is not None and not isinstance(answer_stream_used, bool):
        errors.append("answer_stream_used must be bool or null")

    answer_stream_first_token_ms = trace.get("answer_stream_first_token_ms")
    if answer_stream_first_token_ms is not None and not isinstance(answer_stream_first_token_ms, int):
        errors.append("answer_stream_first_token_ms must be int or null")
    if isinstance(answer_stream_first_token_ms, int) and answer_stream_first_token_ms < 0:
        errors.append("answer_stream_first_token_ms must be >= 0")

    answer_stream_fallback_reason = trace.get("answer_stream_fallback_reason")
    if answer_stream_fallback_reason is not None and not isinstance(answer_stream_fallback_reason, str):
        errors.append("answer_stream_fallback_reason must be string or null")

    answer_stream_events = trace.get("answer_stream_events")
    if answer_stream_events is not None and not isinstance(answer_stream_events, list):
        errors.append("answer_stream_events must be list or null")
    if isinstance(answer_stream_events, list):
        for i, event in enumerate(answer_stream_events):
            if not isinstance(event, dict):
                errors.append(f"answer_stream_events[{i}] must be object")
                continue
            for key in ("event_index", "t_ms", "delta_chars", "cumulative_chars"):
                value = event.get(key)
                if not isinstance(value, int):
                    errors.append(f"answer_stream_events[{i}].{key} must be int")
                elif value < 0:
                    errors.append(f"answer_stream_events[{i}].{key} must be >= 0")

    rewrite_rule_query = trace.get("rewrite_rule_query")
    if rewrite_rule_query is not None and not isinstance(rewrite_rule_query, str):
        errors.append("rewrite_rule_query must be string or null")

    rewrite_llm_query = trace.get("rewrite_llm_query")
    if rewrite_llm_query is not None and not isinstance(rewrite_llm_query, str):
        errors.append("rewrite_llm_query must be string or null")

    calibrated_query = trace.get("calibrated_query")
    if calibrated_query is not None and not isinstance(calibrated_query, str):
        errors.append("calibrated_query must be string or null")

    calibration_reason = trace.get("calibration_reason")
    if calibration_reason is not None and not isinstance(calibration_reason, dict):
        errors.append("calibration_reason must be object or null")

    query_retry_used = trace.get("query_retry_used")
    if query_retry_used is not None and not isinstance(query_retry_used, bool):
        errors.append("query_retry_used must be bool or null")

    query_retry_reason = trace.get("query_retry_reason")
    if query_retry_reason is not None and not isinstance(query_retry_reason, str):
        errors.append("query_retry_reason must be string or null")

    answer_citations = trace.get("answer_citations")
    if answer_citations is not None and not isinstance(answer_citations, list):
        errors.append("answer_citations must be list or null")
    if isinstance(answer_citations, list):
        for i, row in enumerate(answer_citations):
            if not isinstance(row, dict):
                errors.append(f"answer_citations[{i}] must be object")
                continue
            for required_key in ("chunk_id", "paper_id", "section_page"):
                if required_key not in row:
                    errors.append(f"answer_citations[{i}] missing key: {required_key}")
            chunk_id = row.get("chunk_id")
            if chunk_id is not None and not isinstance(chunk_id, str):
                errors.append(f"answer_citations[{i}].chunk_id must be string or null")
            if isinstance(chunk_id, str) and not chunk_id.strip():
                errors.append(f"answer_citations[{i}].chunk_id must not be empty")
            paper_id = row.get("paper_id")
            if paper_id is not None and not isinstance(paper_id, str):
                errors.append(f"answer_citations[{i}].paper_id must be string or null")
            section_page = row.get("section_page")
            if section_page is not None and not isinstance(section_page, str):
                errors.append(f"answer_citations[{i}].section_page must be string or null")
            if isinstance(section_page, str) and not section_page.strip():
                errors.append(f"answer_citations[{i}].section_page must not be empty")

    output_warnings = trace.get("output_warnings")
    if output_warnings is not None and not isinstance(output_warnings, list):
        errors.append("output_warnings must be list or null")
    warning_set = {
        str(w).strip()
        for w in output_warnings
        if isinstance(w, str) and str(w).strip()
    } if isinstance(output_warnings, list) else set()
    if context_overflow_fallback and "context_overflow_fallback" not in warning_set:
        errors.append("context_overflow_fallback must appear in output_warnings")
    if isinstance(answer_stream_fallback_reason, str) and answer_stream_fallback_reason and warning_set:
        if answer_stream_fallback_reason not in warning_set:
            errors.append("answer_stream_fallback_reason must appear in output_warnings")

    def _validate_llm_diagnostics(key: str, expected_stage: str) -> dict[str, Any] | None:
        value = trace.get(key)
        if value is None:
            return None
        if not isinstance(value, dict):
            errors.append(f"{key} must be object or null")
            return None
        for req in (
            "stage",
            "provider",
            "model",
            "reason",
            "status_code",
            "attempts_used",
            "max_retries",
            "elapsed_ms",
            "fallback_warning",
            "timestamp",
        ):
            if req not in value:
                errors.append(f"{key} missing key: {req}")
        stage = value.get("stage")
        if stage is not None and not isinstance(stage, str):
            errors.append(f"{key}.stage must be string or null")
        if isinstance(stage, str) and stage != expected_stage:
            errors.append(f"{key}.stage must be '{expected_stage}'")
        for str_key in ("provider", "model", "reason", "fallback_warning", "timestamp"):
            field = value.get(str_key)
            if field is not None and not isinstance(field, str):
                errors.append(f"{key}.{str_key} must be string or null")
        for opt_str_key in ("provider_used", "model_used", "fallback_reason", "error_category"):
            field = value.get(opt_str_key)
            if field is not None and not isinstance(field, str):
                errors.append(f"{key}.{opt_str_key} must be string or null")
        status_code = value.get("status_code")
        if status_code is not None and not isinstance(status_code, int):
            errors.append(f"{key}.status_code must be int or null")
        for int_key in ("attempts_used", "max_retries", "elapsed_ms"):
            field = value.get(int_key)
            if field is not None and not isinstance(field, int):
                errors.append(f"{key}.{int_key} must be int or null")
        fallback_warning = value.get("fallback_warning")
        if isinstance(fallback_warning, str) and fallback_warning and warning_set and fallback_warning not in warning_set:
            errors.append(f"{key}.fallback_warning must appear in output_warnings")
        for forbidden in ("api_key", "prompt", "system_prompt", "user_prompt", "response_body"):
            if forbidden in value:
                errors.append(f"{key} must not contain sensitive field: {forbidden}")
        return value

    rewrite_diag = _validate_llm_diagnostics("rewrite_llm_diagnostics", "rewrite")
    answer_diag = _validate_llm_diagnostics("answer_llm_diagnostics", "answer")

    rewrite_warnings = {
        "llm_missing_api_key_fallback_to_rules",
        "llm_rate_limit_fallback_to_rules",
        "llm_timeout_fallback_to_rules",
        "llm_empty_response_fallback_to_rules",
        "llm_term_loss_fallback_to_rules",
        "llm_intent_drift_fallback_to_rules",
        "llm_query_validation_failed_fallback_to_rules",
        "llm_error_fallback_to_rules",
    }
    answer_warnings = {
        "llm_fallback_disabled_skip_llm_answer",
        "llm_answer_missing_api_key_fallback_to_template",
        "llm_answer_timeout_fallback_to_template",
        "llm_answer_rate_limit_fallback_to_template",
        "llm_answer_empty_response_fallback_to_template",
        "llm_answer_error_fallback_to_template",
        "llm_answer_invalid_json_fallback_to_template",
        "llm_answer_invalid_payload_fallback_to_template",
        "llm_answer_first_token_timeout_fallback_to_template",
        "llm_answer_stream_interrupted_fallback_to_template",
        "llm_answer_stream_empty_response_fallback_to_template",
    }
    rewrite_warning_hit = next((w for w in warning_set if w in rewrite_warnings), None)
    answer_warning_hit = next((w for w in warning_set if w in answer_warnings), None)
    diagnostics_mode = ("rewrite_llm_diagnostics" in trace) or ("answer_llm_diagnostics" in trace)
    if diagnostics_mode and rewrite_warning_hit and not isinstance(rewrite_diag, dict):
        errors.append("rewrite_llm_diagnostics required when rewrite fallback warning exists")
    if diagnostics_mode and answer_warning_hit and not isinstance(answer_diag, dict):
        errors.append("answer_llm_diagnostics required when answer fallback warning exists")

    embedding_enabled = trace.get("embedding_enabled")
    if embedding_enabled is not None and not isinstance(embedding_enabled, bool):
        errors.append("embedding_enabled must be bool or null")

    for key in ("embedding_provider", "embedding_model", "dense_score_type"):
        value = trace.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{key} must be string or null")

    for key in (
        "embedding_dim",
        "embedding_batch_size",
        "embedding_cache_hits",
        "embedding_cache_miss",
        "embedding_api_calls",
        "embedding_query_time_ms",
        "embedding_build_time_ms",
        "embedding_failed_count",
        "rate_limited_count",
        "backoff_total_ms",
        "truncated_count",
        "skipped_over_limit_count",
        "skipped_empty",
        "expansion_budget",
    ):
        value = trace.get(key)
        if value is not None and not isinstance(value, int):
            errors.append(f"{key} must be int or null")

    for key in ("embedding_cache_enabled", "embedding_cache_hit"):
        value = trace.get(key)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{key} must be bool or null")

    for key in ("embedding_failed_chunk_ids", "embedding_batch_failures", "skipped_empty_chunk_ids"):
        value = trace.get(key)
        if value is not None and not isinstance(value, list):
            errors.append(f"{key} must be list or null")
    embedding_batch_failures = trace.get("embedding_batch_failures")
    if isinstance(embedding_batch_failures, list):
        for i, row in enumerate(embedding_batch_failures):
            if not isinstance(row, dict):
                errors.append(f"embedding_batch_failures[{i}] must be object")
                continue
            for required_key in ("count", "status_code", "trace_id"):
                if required_key not in row:
                    errors.append(f"embedding_batch_failures[{i}] missing key: {required_key}")
            count = row.get("count")
            if count is not None and not isinstance(count, int):
                errors.append(f"embedding_batch_failures[{i}].count must be int or null")
            status_code = row.get("status_code")
            if status_code is not None and not isinstance(status_code, int):
                errors.append(f"embedding_batch_failures[{i}].status_code must be int or null")
            trace_id = row.get("trace_id")
            if trace_id is not None and not isinstance(trace_id, str):
                errors.append(f"embedding_batch_failures[{i}].trace_id must be string or null")
            response_body = row.get("response_body")
            if response_body is not None and not isinstance(response_body, str):
                errors.append(f"embedding_batch_failures[{i}].response_body must be string or null")
            for int_key in ("batch_index", "batch_total"):
                value = row.get(int_key)
                if value is not None and not isinstance(value, int):
                    errors.append(f"embedding_batch_failures[{i}].{int_key} must be int or null")

    hybrid_fusion_weight = trace.get("hybrid_fusion_weight")
    if hybrid_fusion_weight is not None and not isinstance(hybrid_fusion_weight, (int, float)):
        errors.append("hybrid_fusion_weight must be number or null")
    graph_expand_alpha = trace.get("graph_expand_alpha")
    if graph_expand_alpha is not None and not isinstance(graph_expand_alpha, (int, float)):
        errors.append("graph_expand_alpha must be number or null")

    return len(errors) == 0, errors
