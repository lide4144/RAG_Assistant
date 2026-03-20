from __future__ import annotations

from dataclasses import asdict
import json
import os
from typing import Any, Callable, Literal, Protocol, TypedDict

from app.agent_tools import (
    ToolRegistryEntry,
    build_tool_call_envelope,
    build_tool_failure,
    build_tool_result_envelope,
    serialize_tool_registry_entry,
    validate_tool_call_envelope,
    validate_tool_registry_entry,
)
from app.capability_planner import (
    PlannerResult,
    build_planner_fallback,
    parse_planner_result,
    compose_catalog_answer,
    execute_catalog_lookup,
    normalize_planner_source,
    paper_assistant_clarification,
    serialize_planner_result,
    PLANNER_SOURCE_FALLBACK,
    PLANNER_SOURCE_LLM,
)
from app.config import load_and_validate_config
from app.llm_client import call_chat_completion
from app.paths import CONFIGS_DIR
from app.session_state import load_planner_conversation_state

try:  # pragma: no cover - exercised indirectly when langgraph is installed
    from langgraph.graph import END, StateGraph

    HAS_LANGGRAPH = True
except Exception:  # pragma: no cover - fallback path used in tests when dependency is absent
    END = "__end__"
    StateGraph = None
    HAS_LANGGRAPH = False


PlannerRuntimeRoute = Literal[
    "fact_qa",
    "catalog",
    "summary",
    "control",
    "research_assistant",
    "web_delegate",
    "clarify",
    "controlled_terminate",
]

RUNTIME_CONTRACT_VERSION = "agent-first-v1"
RUNTIME_STABLE_FIELDS = (
    "request",
    "planner",
    "tool_calls",
    "route",
    "fallback",
    "response",
    "selected_path",
    "execution_trace",
    "short_circuit",
    "truncated",
)
RUNTIME_ENVELOPE_FIELDS = (
    "tool_results",
    "runtime",
)
MAX_RUNTIME_TOOL_STEPS = 3
PLANNER_SOURCE_MODE_ENV = "PLANNER_SOURCE_MODE"
DEFAULT_PLANNER_SOURCE_MODE = "llm_primary"
PLANNER_SOURCE_MODES = {
    "llm_primary",
    "shadow_compare",
}
PLANNER_VALIDATION_STATUSES = {"accept", "accept_with_warnings", "reject"}
PLANNER_DECISION_ENUMS = {
    "decision_result": {"clarify", "local_execute", "delegate_web", "delegate_research_assistant", "controlled_terminate"},
    "strictness": {"strict_fact", "summary", "catalog"},
    "knowledge_route": {"local", "web"},
    "research_mode": {"none", "paper_assistant"},
}
SHADOW_DIFF_FIELDS = (
    "primary_capability",
    "strictness",
    "decision_result",
    "requires_clarification",
    "selected_tools_or_skills",
    "action_plan",
)
PLANNER_LLM_SYSTEM_PROMPT = (
    "You are a planner that routes a RAG assistant request. "
    "Return only a single JSON object that matches the required planner contract. "
    "Do not wrap JSON in markdown fences. "
    "Use only tools or skills present in capability_registry. "
    "Keep action_plan to at most policy_flags.max_steps steps."
)


class PlannerRuntimePayload(TypedDict, total=False):
    sessionId: str
    mode: str
    query: str
    traceId: str | None
    history: list[dict[str, str]]
    configPath: str | None


class PlannerRuntimeState(TypedDict, total=False):
    payload: Any
    request: PlannerRuntimePayload
    planner: dict[str, Any]
    planner_candidates: dict[str, Any]
    runtime: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    route: PlannerRuntimeRoute
    fallback: dict[str, Any]
    response: Any
    selected_path: str
    execution_trace: list[dict[str, Any]]
    short_circuit: dict[str, Any]
    truncated: bool
    controlled_termination: dict[str, Any]
    planner_runtime_backend: str
    planner_runtime_passthrough: bool

RUNTIME_TOOL_REGISTRY: dict[str, ToolRegistryEntry] = {
    "fact_qa": ToolRegistryEntry(
        tool_name="fact_qa",
        capability_family="qa",
        version="v1",
        planner_visible=True,
        kind="tool",
        route="fact_qa",
        passthrough=False,
        streaming_mode="text_stream",
        evidence_policy="citation_required",
        input_schema={"query": "string"},
        result_schema={"answer": "string", "sources": "citation[]"},
        failure_types=("invalid_input", "insufficient_evidence", "timeout", "execution_error"),
        capability_tags=("fact_qa", "strict_fact"),
    ),
    "catalog_lookup": ToolRegistryEntry(
        tool_name="catalog_lookup",
        capability_family="retrieval_meta",
        version="v1",
        planner_visible=True,
        kind="tool",
        route="catalog",
        passthrough=True,
        streaming_mode="final_only",
        evidence_policy="citation_forbidden",
        input_schema={"query": "string", "limit": "integer"},
        result_schema={"paper_set": "artifact", "sources": "metadata[]"},
        failure_types=("invalid_input", "empty_result", "execution_error"),
        capability_tags=("catalog", "local_retrieval"),
        produces=("paper_set",),
    ),
    "cross_doc_summary": ToolRegistryEntry(
        tool_name="cross_doc_summary",
        capability_family="summary",
        version="v1",
        planner_visible=True,
        kind="tool",
        route="summary",
        passthrough=True,
        streaming_mode="text_stream",
        evidence_policy="citation_optional",
        input_schema={"query": "string", "paper_set": "artifact?"},
        result_schema={"answer": "string", "sources": "citation[]"},
        failure_types=("invalid_input", "missing_dependencies", "timeout", "execution_error"),
        capability_tags=("summary", "comparison"),
        prerequisites=("paper_set_optional",),
    ),
    "control": ToolRegistryEntry(
        tool_name="control",
        capability_family="control",
        version="v1",
        planner_visible=True,
        kind="tool",
        route="control",
        passthrough=True,
        streaming_mode="final_only",
        evidence_policy="citation_forbidden",
        input_schema={"query": "string"},
        result_schema={"instruction": "string", "sources": "metadata[]"},
        failure_types=("invalid_input", "execution_error"),
        capability_tags=("control", "formatting"),
    ),
    "paper_assistant": ToolRegistryEntry(
        tool_name="paper_assistant",
        capability_family="research_assistant",
        version="v1",
        planner_visible=True,
        kind="skill",
        route="research_assistant",
        passthrough=True,
        streaming_mode="text_stream",
        evidence_policy="citation_optional",
        input_schema={"query": "string", "paper_set": "artifact?"},
        result_schema={"answer": "string", "sources": "citation|explanatory[]"},
        failure_types=("precondition_failed", "missing_dependencies", "timeout", "execution_error"),
        capability_tags=("research_assistant", "summary", "guidance"),
        supports_research_mode=True,
        prerequisites=("research_topic_or_paper_scope",),
    ),
    "title_term_localization": ToolRegistryEntry(
        tool_name="title_term_localization",
        capability_family="localization",
        version="v1",
        planner_visible=False,
        kind="tool",
        route="control",
        passthrough=True,
        streaming_mode="final_only",
        evidence_policy="citation_forbidden",
        input_schema={"text": "string"},
        result_schema={"localized_text": "string", "sources": "explanatory[]"},
        failure_types=("invalid_input", "execution_error"),
        capability_tags=("localization", "title_translation"),
    ),
}
RUNTIME_DELEGATE_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "name": "web_research",
        "kind": "skill",
        "capability_tags": ["web", "external_research"],
        "knowledge_scope": "web",
        "supports_research_mode": False,
        "prerequisites": ["network_allowed"],
    },
)


class RuntimeExecutor(Protocol):
    def __call__(
        self,
        payload: Any,
        *,
        selected_path: str,
        on_stream_delta: Callable[[str], None] | None = None,
        runtime_fallback: bool = False,
        runtime_fallback_reason: str | None = None,
        planner_result: PlannerResult | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> Any: ...


class PlannerRuntimeRunResult(TypedDict):
    response: Any
    observation: dict[str, Any]


def _serialize_planner_result(result: PlannerResult) -> dict[str, Any]:
    return serialize_planner_result(result)


def _default_runtime_contract() -> dict[str, Any]:
    registry_errors: list[str] = []
    for entry in RUNTIME_TOOL_REGISTRY.values():
        registry_errors.extend(validate_tool_registry_entry(entry))
    return {
        "version": RUNTIME_CONTRACT_VERSION,
        "stable_fields": list(RUNTIME_STABLE_FIELDS),
        "envelope_fields": list(RUNTIME_ENVELOPE_FIELDS),
        "tool_registry": sorted(RUNTIME_TOOL_REGISTRY),
        "capability_registry": _serialize_capability_registry(),
        "tool_registry_entries": [serialize_tool_registry_entry(entry) for entry in sorted(RUNTIME_TOOL_REGISTRY.values(), key=lambda row: row.tool_name)],
        "registry_validation_errors": registry_errors,
        "planner_input_segments": ["request", "conversation_context", "capability_registry", "policy_flags"],
        "planner_source_modes": sorted(PLANNER_SOURCE_MODES),
    }


def _serialize_capability_registry() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in RUNTIME_TOOL_REGISTRY.values():
        rows.append(serialize_tool_registry_entry(spec))
    rows.extend(dict(item) for item in RUNTIME_DELEGATE_CAPABILITIES)
    rows.sort(key=lambda row: str(row.get("name") or ""))
    return rows


def _planner_policy_flags(config: Any | None = None) -> dict[str, Any]:
    return {
        "allow_web_delegation": True,
        "allow_research_assistant": True,
        "force_local_first": False,
        "max_steps": max(1, int(getattr(config, "planner_max_steps", MAX_RUNTIME_TOOL_STEPS))),
        "catalog_limit": max(1, int(getattr(config, "planner_max_papers", 20))),
        "summary_min_papers": max(1, int(getattr(config, "planner_summary_min_papers", 2))),
    }


def _planner_source_mode() -> str:
    normalized = str(os.getenv(PLANNER_SOURCE_MODE_ENV, DEFAULT_PLANNER_SOURCE_MODE) or "").strip().lower()
    if normalized in PLANNER_SOURCE_MODES:
        return normalized
    return DEFAULT_PLANNER_SOURCE_MODE


def _build_planner_llm_prompt(*, planner_input_context: dict[str, Any]) -> str:
    payload = {
        "task": "Generate an independent planner decision for the request.",
        "output_contract": {
            "decision_version": "planner-policy-v1",
            "planner_source": "llm",
            "planner_used": True,
            "planner_confidence": "float 0..1",
            "user_goal": "string",
            "standalone_query": "string",
            "is_new_topic": "bool",
            "should_clear_pending_clarify": "bool",
            "relation_to_previous": "string",
            "primary_capability": "string",
            "strictness": "strict_fact|summary|catalog",
            "decision_result": "clarify|local_execute|delegate_web|delegate_research_assistant|controlled_terminate",
            "knowledge_route": "local|web",
            "research_mode": "none|paper_assistant",
            "requires_clarification": "bool",
            "clarify_question": "string|null",
            "selected_tools_or_skills": "string[]",
            "action_plan": "step[]",
            "fallback": {"type": "string|null", "reason": "string|null"},
        },
        "step_contract": {
            "action": "registered tool or skill name",
            "query": "string",
            "produces": "string|null",
            "depends_on": "string[]",
            "params": "object",
        },
        "planner_input": planner_input_context,
        "instruction": "Reason independently from planner_input and return the formal planner decision only.",
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_first_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    candidates = [text]
    if "```" in text:
        segments = [segment.strip() for segment in text.split("```") if segment.strip()]
        candidates.extend(segments)
        candidates.extend(segment.split("\n", 1)[1].strip() for segment in segments if "\n" in segment)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        probe = candidate.strip()
        if not probe:
            continue
        try:
            parsed = json.loads(probe)
        except json.JSONDecodeError:
            for idx, char in enumerate(probe):
                if char != "{":
                    continue
                try:
                    parsed, _ = decoder.raw_decode(probe[idx:])
                    break
                except json.JSONDecodeError:
                    parsed = None
            else:
                parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def _build_planner_llm_candidate(
    *,
    request: dict[str, Any],
    planner_input_context: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "attempted": False,
        "used_override": False,
        "status": "skipped",
        "reason": None,
        "provider": None,
        "model": None,
        "elapsed_ms": 0,
    }
    raw_override = os.getenv("PLANNER_LLM_DECISION_JSON", "").strip()
    if raw_override:
        diagnostics["attempted"] = True
        diagnostics["used_override"] = True
        diagnostics["status"] = "override"
        try:
            payload = json.loads(raw_override)
            if isinstance(payload, dict):
                return payload, diagnostics
            diagnostics["status"] = "invalid_override"
            diagnostics["reason"] = "override_not_object"
            return None, diagnostics
        except Exception:
            diagnostics["status"] = "invalid_override"
            diagnostics["reason"] = "override_parse_error"
            return None, diagnostics

    config_path = str(request.get("configPath") or "").strip()
    if not config_path:
        diagnostics["reason"] = "planner_config_missing"
        return None, diagnostics

    cfg, _ = load_and_validate_config(config_path)
    provider = str(getattr(cfg, "planner_provider", "")).strip()
    model = str(getattr(cfg, "planner_model", "")).strip()
    api_base = str(getattr(cfg, "planner_api_base", "")).strip()
    api_key_env = str(getattr(cfg, "planner_api_key_env", "")).strip()
    api_key = os.getenv(api_key_env, "").strip() if api_key_env else ""
    planner_enabled = bool(getattr(cfg, "planner_use_llm", False))
    diagnostics["provider"] = provider or None
    diagnostics["model"] = model or None
    if not planner_enabled:
        diagnostics["reason"] = "planner_llm_disabled"
        return None, diagnostics
    if not model:
        diagnostics["reason"] = "planner_model_missing"
        return None, diagnostics
    if not api_key:
        diagnostics["reason"] = "planner_api_key_missing"
        return None, diagnostics

    diagnostics["attempted"] = True
    timeout_ms = max(1000, int(getattr(cfg, "planner_timeout_ms", 6000)))
    result = call_chat_completion(
        provider=provider or "siliconflow",
        model=model,
        api_key=api_key,
        api_base=(api_base or None),
        system_prompt=PLANNER_LLM_SYSTEM_PROMPT,
        user_prompt=_build_planner_llm_prompt(planner_input_context=planner_input_context),
        timeout_ms=timeout_ms,
        max_retries=max(0, int(getattr(cfg, "llm_max_retries", 0))),
        temperature=0.0,
    )
    diagnostics["elapsed_ms"] = int(getattr(result, "elapsed_ms", 0) or 0)
    diagnostics["provider"] = getattr(result, "provider_used", None) or diagnostics["provider"]
    diagnostics["model"] = getattr(result, "model_used", None) or diagnostics["model"]
    if not result.ok:
        diagnostics["status"] = "error"
        diagnostics["reason"] = str(getattr(result, "reason", None) or "planner_llm_call_failed")
        diagnostics["status_code"] = getattr(result, "status_code", None)
        diagnostics["error_category"] = getattr(result, "error_category", None)
        return None, diagnostics

    payload = _extract_first_json_object(str(result.content or ""))
    if not isinstance(payload, dict):
        diagnostics["status"] = "invalid_payload"
        diagnostics["reason"] = "planner_llm_invalid_json"
        return None, diagnostics

    diagnostics["status"] = "ok"
    return payload, diagnostics


def _validation_layer(status: str, reason_codes: list[str], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status if status in PLANNER_VALIDATION_STATUSES else "reject",
        "reason_codes": list(reason_codes),
        "warnings": list(warnings or []),
    }


def _validate_structure(planner: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    warnings: list[str] = []
    bool_fields = (
        "planner_used",
        "is_new_topic",
        "should_clear_pending_clarify",
        "requires_clarification",
    )
    required_fields = (
        "decision_version",
        "planner_source",
        "planner_used",
        "planner_confidence",
        "user_goal",
        "standalone_query",
        "is_new_topic",
        "should_clear_pending_clarify",
        "relation_to_previous",
        "primary_capability",
        "strictness",
        "decision_result",
        "knowledge_route",
        "research_mode",
        "requires_clarification",
        "clarify_question",
        "selected_tools_or_skills",
        "action_plan",
        "fallback",
    )
    for field in required_fields:
        if field not in planner:
            reason_codes.append(f"missing_field:{field}")
    for field, allowed in PLANNER_DECISION_ENUMS.items():
        value = str(planner.get(field) or "").strip()
        if value and value not in allowed:
            reason_codes.append(f"invalid_enum:{field}")
    for field in bool_fields:
        if field in planner and not isinstance(planner.get(field), bool):
            reason_codes.append(f"invalid_type:{field}")
    confidence = planner.get("planner_confidence")
    if not isinstance(confidence, (int, float)):
        reason_codes.append("invalid_type:planner_confidence")
    elif float(confidence) < 0.0 or float(confidence) > 1.0:
        reason_codes.append("out_of_range:planner_confidence")
    if not isinstance(planner.get("selected_tools_or_skills"), list):
        reason_codes.append("invalid_type:selected_tools_or_skills")
    if not isinstance(planner.get("action_plan"), list):
        reason_codes.append("invalid_type:action_plan")
    if not isinstance(planner.get("fallback"), dict):
        reason_codes.append("invalid_type:fallback")
    if planner.get("clarify_question") is not None and not isinstance(planner.get("clarify_question"), str):
        reason_codes.append("invalid_type:clarify_question")
    return _validation_layer("reject" if reason_codes else ("accept_with_warnings" if warnings else "accept"), reason_codes, warnings)


def _validate_semantics(planner: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    warnings: list[str] = []
    decision_result = str(planner.get("decision_result") or "")
    requires_clarification = bool(planner.get("requires_clarification", False))
    clarify_question = str(planner.get("clarify_question") or "").strip()
    action_plan = list(planner.get("action_plan") or [])
    selected_tools = [str(item).strip() for item in list(planner.get("selected_tools_or_skills") or []) if str(item).strip()]

    if requires_clarification and not clarify_question:
        reason_codes.append("clarify_question_missing")
    if decision_result == "clarify":
        if not requires_clarification:
            reason_codes.append("clarify_result_missing_flag")
        if action_plan:
            reason_codes.append("clarify_result_with_action_plan")
    elif requires_clarification:
        warnings.append("clarify_flag_without_clarify_result")

    if decision_result == "local_execute" and not action_plan:
        reason_codes.append("local_execute_missing_action_plan")
    if decision_result == "delegate_web" and "web_research" not in selected_tools:
        reason_codes.append("delegate_web_missing_selected_capability")
    if decision_result == "delegate_research_assistant" and "paper_assistant" not in selected_tools:
        reason_codes.append("delegate_research_assistant_missing_selected_capability")
    if decision_result == "controlled_terminate":
        fallback = dict(planner.get("fallback") or {})
        if action_plan:
            reason_codes.append("controlled_terminate_with_action_plan")
        if not bool(fallback.get("reason")):
            reason_codes.append("controlled_terminate_missing_reason")
        if requires_clarification and not clarify_question:
            reason_codes.append("controlled_terminate_missing_clarify_question")

    action_names: list[str] = []
    for raw_step in action_plan:
        if isinstance(raw_step, dict):
            action = str(raw_step.get("action") or "").strip()
            if action:
                action_names.append(action)
    if action_names and selected_tools and action_names != [name for name in selected_tools if name in action_names]:
        warnings.append("selected_tools_mismatch_action_plan")

    status = "reject" if reason_codes else ("accept_with_warnings" if warnings else "accept")
    return _validation_layer(status, reason_codes, warnings)


def _validate_execution(planner: dict[str, Any], *, policy_flags: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    warnings: list[str] = []
    action_plan = list(planner.get("action_plan") or [])
    max_steps = max(1, int(policy_flags.get("max_steps") or MAX_RUNTIME_TOOL_STEPS))
    if len(action_plan) > max_steps:
        reason_codes.append("action_plan_step_limit_exceeded")

    produced: set[str] = set()
    for step in action_plan:
        if not isinstance(step, dict):
            reason_codes.append("invalid_type:action_plan_step")
            continue
        action = str(step.get("action") or "").strip()
        query = str(step.get("query") or "").strip()
        depends_on = [str(item).strip() for item in list(step.get("depends_on") or []) if str(item).strip()]
        params = step.get("params")
        if not action:
            reason_codes.append("missing_field:action")
            continue
        if action not in RUNTIME_TOOL_REGISTRY:
            reason_codes.append(f"unsupported_tool:{action}")
            continue
        if not query:
            reason_codes.append(f"missing_query:{action}")
        if params is not None and not isinstance(params, dict):
            reason_codes.append(f"invalid_params:{action}")
        missing_dep = [name for name in depends_on if name not in produced]
        if missing_dep:
            reason_codes.append(f"missing_dependencies:{','.join(missing_dep)}")
        produces_raw = step.get("produces")
        if isinstance(produces_raw, list):
            produced.update(str(item).strip() for item in produces_raw if str(item).strip())
        elif produces_raw is not None and str(produces_raw).strip():
            produced.add(str(produces_raw).strip())
        else:
            produced.update(RUNTIME_TOOL_REGISTRY[action].produces)
    status = "reject" if reason_codes else ("accept_with_warnings" if warnings else "accept")
    return _validation_layer(status, reason_codes, warnings)


def _validate_policy(planner: dict[str, Any], *, policy_flags: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    warnings: list[str] = []
    decision_result = str(planner.get("decision_result") or "")
    if decision_result == "delegate_web" and not bool(policy_flags.get("allow_web_delegation", False)):
        reason_codes.append("policy_blocked:web_delegation")
    if decision_result == "delegate_research_assistant" and not bool(policy_flags.get("allow_research_assistant", True)):
        reason_codes.append("policy_blocked:research_assistant")
    if bool(policy_flags.get("force_local_first", False)) and decision_result == "delegate_web":
        reason_codes.append("policy_blocked:force_local_first")
    status = "reject" if reason_codes else ("accept_with_warnings" if warnings else "accept")
    return _validation_layer(status, reason_codes, warnings)


def _validate_llm_planner_decision(planner: dict[str, Any], *, policy_flags: dict[str, Any]) -> dict[str, Any]:
    layers = {
        "structure": _validate_structure(planner),
        "semantic": _validate_semantics(planner),
        "execution": _validate_execution(planner, policy_flags=policy_flags),
        "policy": _validate_policy(planner, policy_flags=policy_flags),
    }
    all_reason_codes: list[str] = []
    all_warnings: list[str] = []
    rejected_layers: list[str] = []
    for layer_name, layer in layers.items():
        all_reason_codes.extend(str(code) for code in list(layer.get("reason_codes") or []))
        all_warnings.extend(str(code) for code in list(layer.get("warnings") or []))
        if layer.get("status") == "reject":
            rejected_layers.append(layer_name)
    verdict = "reject" if rejected_layers else ("accept_with_warnings" if all_warnings else "accept")
    return {
        "status": verdict,
        "reason_codes": all_reason_codes,
        "warnings": all_warnings,
        "rejected_layers": rejected_layers,
        "reason_code": all_reason_codes[0] if all_reason_codes else None,
        "layers": layers,
    }


def _load_runtime_planner_config(request: dict[str, Any]) -> Any:
    config_path = str(request.get("configPath") or "").strip()
    if not config_path:
        config_path = str(CONFIGS_DIR / "default.yaml")
    config, _ = load_and_validate_config(config_path)
    return config


def _build_planner_input_context(request: dict[str, Any], *, config: Any | None = None) -> dict[str, Any]:
    history = list(request.get("history") or [])
    session_context = load_planner_conversation_state(str(request.get("sessionId") or ""))
    return {
        "request": {
            "query": str(request.get("query") or ""),
            "mode": str(request.get("mode") or "local"),
            "trace_id": request.get("traceId"),
        },
        "conversation_context": {
            "history_size": len(history),
            "last_user_turn": (
                str(history[-1].get("content") or "")
                if history and isinstance(history[-1], dict) and str(history[-1].get("role") or "") == "user"
                else None
            ),
            "recent_topic_anchors": list(session_context.get("recent_topic_anchors") or []),
            "pending_clarify": session_context.get("pending_clarify"),
            "previous_planner": session_context.get("previous_planner"),
        },
        "capability_registry": _serialize_capability_registry(),
        "policy_flags": _planner_policy_flags(config),
    }


def _response_metadata(response: Any) -> dict[str, Any]:
    sources = getattr(response, "sources", None)
    return {
        "trace_id": getattr(response, "traceId", None),
        "source_count": len(sources) if isinstance(sources, list) else None,
    }


def _serialize_response_sources(response: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list(getattr(response, "sources", None) or []):
        rows.append(
            {
                "source_type": getattr(item, "source_type", "local"),
                "source_id": getattr(item, "source_id", ""),
                "title": getattr(item, "title", ""),
                "snippet": getattr(item, "snippet", ""),
                "locator": getattr(item, "locator", ""),
                "score": float(getattr(item, "score", 0.0) or 0.0),
                "provenance_type": getattr(item, "provenance_type", "citation"),
                "citation_indexable": bool(getattr(item, "provenance_type", "citation") == "citation"),
            }
        )
    return rows


def _tool_specific_sources(tool_name: str, response: Any) -> list[dict[str, Any]]:
    if tool_name == "paper_assistant":
        return [
            {
                "source_type": "local",
                "source_id": "paper_assistant_guidance",
                "title": "Research Assistant Guidance",
                "snippet": str(getattr(response, "answer", "") or "")[:120].strip(),
                "locator": "assistant",
                "score": 1.0,
                "provenance_type": "explanatory",
                "citation_indexable": False,
            }
        ]
    if tool_name == "catalog_lookup":
        return [
            {
                "source_type": "local",
                "source_id": "catalog_lookup",
                "title": "Paper Catalog",
                "snippet": "catalog metadata result",
                "locator": "catalog",
                "score": 1.0,
                "provenance_type": "metadata",
                "citation_indexable": False,
            }
        ]
    if tool_name == "control":
        return [
            {
                "source_type": "local",
                "source_id": "control_intent",
                "title": "Control Intent",
                "snippet": "structured control result",
                "locator": "runtime",
                "score": 1.0,
                "provenance_type": "metadata",
                "citation_indexable": False,
            }
        ]
    return []


def _selected_path_for_tool(tool_call: dict[str, Any]) -> str:
    route = str(tool_call.get("route") or "controlled_terminate")
    return route if not bool(tool_call.get("passthrough")) else f"{route}_passthrough"


def _catalog_lookup_response(tool_call: dict[str, Any], catalog_result: dict[str, Any]) -> Any:
    from app.kernel_api import KernelChatResponse

    call_id = str(tool_call.get("call_id") or tool_call.get("id") or "tool")
    answer = compose_catalog_answer(catalog_result)
    return KernelChatResponse(traceId=f"trace_{call_id}", answer=answer, sources=[])


def _catalog_lookup_result(tool_call: dict[str, Any]) -> tuple[dict[str, Any], Any, dict[str, Any], dict[str, Any]]:
    params = dict(((tool_call.get("arguments") or {}).get("params")) or {})
    limit_raw = params.get("limit")
    try:
        limit = max(1, int(limit_raw))
    except (TypeError, ValueError):
        limit = 20
    catalog_result = execute_catalog_lookup(
        query=str(tool_call.get("query") or ""),
        max_papers=limit,
    )
    response = _catalog_lookup_response(tool_call, catalog_result)
    selected_path = _selected_path_for_tool(tool_call)
    observability = {
        "selected_path": selected_path,
        "matched_count": int(catalog_result.get("matched_count", 0) or 0),
        "selected_count": int(catalog_result.get("selected_count", 0) or 0),
        "truncated": bool(catalog_result.get("truncated", False)),
    }
    sources = _tool_specific_sources("catalog_lookup", response)
    if bool(catalog_result.get("short_circuit")):
        result = build_tool_result_envelope(
            tool_call,
            status="failed",
            output={
                "matched_count": int(catalog_result.get("matched_count", 0) or 0),
                "selected_count": int(catalog_result.get("selected_count", 0) or 0),
            },
            artifacts=[{"artifact_name": "paper_set", "available": False}],
            sources=sources,
            observability=observability,
            failure=build_tool_failure(
                "empty_result",
                message="catalog lookup returned no papers",
                user_safe_message="未找到符合条件的论文，因此未继续执行后续步骤。",
                stop_plan=True,
            ),
        )
    else:
        result = build_tool_result_envelope(
            tool_call,
            status="succeeded",
            output={
                "selected_path": selected_path,
                "matched_count": int(catalog_result.get("matched_count", 0) or 0),
                "selected_count": int(catalog_result.get("selected_count", 0) or 0),
            },
            artifacts=[{"artifact_name": "paper_set", "available": True}],
            sources=sources,
            observability=observability,
        )
    trace_row = {
        "step": "planner_runtime_tool_execution",
        "action": "catalog_lookup",
        "call_id": tool_call.get("call_id") or tool_call.get("id"),
        "state": str(catalog_result.get("state", "ready")),
        "matched_count": int(catalog_result.get("matched_count", 0) or 0),
        "selected_count": int(catalog_result.get("selected_count", 0) or 0),
        "truncated": bool(catalog_result.get("truncated", False)),
        "tool_status": result["status"],
        "failure_type": result["failure"].get("failure_type"),
        "streaming_mode": tool_call.get("streaming_mode"),
        "evidence_policy": tool_call.get("evidence_policy"),
        "produced_artifacts": ["paper_set"] if not bool(catalog_result.get("short_circuit")) else [],
        "short_circuit_reason": catalog_result.get("short_circuit_reason"),
    }
    return result, response, {"paper_set": list(catalog_result.get("paper_set") or [])}, trace_row


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in terms)


def _build_runtime_clarify_response(payload: Any, question: str) -> Any:
    from app.kernel_api import KernelChatResponse

    trace_id = getattr(payload, "traceId", None) or f"trace_{getattr(payload, 'sessionId', 'runtime')}"
    answer = "为确保回答基于充分证据，请先澄清以下问题：\n1. " + question
    return KernelChatResponse(traceId=trace_id, answer=answer, sources=[])


def _build_controlled_termination(state: PlannerRuntimeState) -> dict[str, Any]:
    planner = dict(state.get("planner") or {})
    runtime = dict(state.get("runtime") or {})
    fallback = dict(state.get("fallback") or {})
    planner_fallback = dict(planner.get("fallback") or {})
    validation = dict(runtime.get("planner_validation") or {})
    rejection_layers = [str(item).strip() for item in list(validation.get("rejected_layers") or []) if str(item).strip()]
    rejection_layer = (
        str(planner_fallback.get("rejection_layer") or "").strip()
        or (rejection_layers[0] if rejection_layers else None)
    )
    reason = (
        str(fallback.get("reason") or "").strip()
        or str(planner_fallback.get("reason") or "").strip()
        or str(validation.get("reason_code") or "").strip()
        or "controlled_terminate"
    )
    clarify_question = str(planner.get("clarify_question") or "").strip() or None
    posture = str(planner_fallback.get("user_visible_posture") or "").strip()
    if posture not in {"clarify", "refuse"}:
        posture = "clarify" if clarify_question else "refuse"
    termination_type = "controlled_terminate"
    if str(validation.get("status") or "") == "reject":
        termination_type = "planner_reject"
    elif fallback.get("type") == "tool":
        termination_type = "tool_or_constraint_failure"
    elif reason in {"planner_runtime_exception", "route_fallback"}:
        termination_type = "runtime_exception"
    elif fallback.get("type") == "planner":
        termination_type = "planner_reject"
    message = "当前请求未通过执行安全检查，请换一种更明确的表述后重试。"
    if posture == "clarify" and clarify_question:
        message = "为继续处理该请求，请先澄清以下问题：\n1. " + clarify_question
    elif termination_type == "tool_or_constraint_failure":
        message = "当前无法继续执行所选能力，请补充更具体的范围或稍后重试。"
    elif termination_type == "runtime_exception":
        message = "当前系统暂时无法完成该请求，请稍后重试。"
    return {
        "type": termination_type,
        "reason": reason,
        "rejection_reason": str(validation.get("reason_code") or reason),
        "rejection_layer": rejection_layer,
        "source": str(fallback.get("type") or planner.get("planner_source") or "planner"),
        "user_visible_posture": posture,
        "clarify_question": clarify_question,
        "message": message,
    }


def _build_controlled_terminate_response(payload: Any, termination: dict[str, Any]) -> Any:
    from app.kernel_api import KernelChatResponse

    trace_id = getattr(payload, "traceId", None) or f"trace_{getattr(payload, 'sessionId', 'runtime')}"
    return KernelChatResponse(traceId=trace_id, answer=str(termination.get("message") or "").strip(), sources=[])


def _paper_assistant_missing_prerequisites(tool_call: dict[str, Any]) -> tuple[list[str], str | None]:
    if str(tool_call.get("tool_name") or "") != "paper_assistant":
        return [], None
    return paper_assistant_clarification(
        str(tool_call.get("query") or "").strip(),
        depends_on=[str(item).strip() for item in list(tool_call.get("depends_on") or []) if str(item).strip()],
    )


def _load_request_context(state: PlannerRuntimeState) -> PlannerRuntimeState:
    next_state = dict(state)
    next_state.setdefault("runtime", _default_runtime_contract())
    next_state.setdefault("planner_candidates", {})
    next_state.setdefault("tool_calls", [])
    next_state.setdefault("tool_results", [])
    next_state.setdefault("execution_trace", [])
    next_state.setdefault("short_circuit", {"triggered": False, "reason": None, "step": None})
    next_state.setdefault("truncated", False)
    next_state.setdefault("fallback", {"type": None, "reason": None, "failed_tool": None})
    next_state.setdefault("planner_runtime_passthrough", False)
    next_state.setdefault("planner_runtime_backend", "langgraph" if HAS_LANGGRAPH else "fallback")
    return next_state


def _plan_chat_request(state: PlannerRuntimeState) -> PlannerRuntimeState:
    next_state = dict(state)
    request = dict(next_state.get("request") or {})
    query = str(request.get("query") or "").strip()
    planner_config = _load_runtime_planner_config(request)
    planner_input_context = _build_planner_input_context(request, config=planner_config)
    runtime = dict(next_state.get("runtime") or {})
    runtime["planner_input_context"] = planner_input_context
    runtime["planner_source_mode"] = _planner_source_mode()
    next_state["runtime"] = runtime
    policy_flags = dict(planner_input_context.get("policy_flags") or {})
    planner_source_mode = str(runtime.get("planner_source_mode") or DEFAULT_PLANNER_SOURCE_MODE)
    llm_result: PlannerResult | None = None
    llm_candidate_payload: dict[str, Any] | None = None
    llm_diagnostics: dict[str, Any] = {"attempted": False, "status": "skipped", "reason": None}
    llm_validation: dict[str, Any] | None = None
    planner_execution_source = PLANNER_SOURCE_FALLBACK
    planner = _serialize_planner_result(
        build_planner_fallback(
            user_input=query,
            standalone_query=query,
            reason="planner_llm_unavailable",
            fallback_type="planner_reject",
            rejection_layer="llm_call",
        )
    )

    llm_candidate_payload, llm_diagnostics = _build_planner_llm_candidate(
        request=request,
        planner_input_context=planner_input_context,
    )
    if llm_candidate_payload is None:
        llm_validation = {
            "status": "reject",
            "reason_codes": [str(llm_diagnostics.get("reason") or "planner_llm_unavailable")],
            "warnings": [],
            "rejected_layers": ["llm_call"],
            "reason_code": str(llm_diagnostics.get("reason") or "planner_llm_unavailable"),
            "layers": {},
        }
    else:
        llm_validation = _validate_llm_planner_decision(llm_candidate_payload, policy_flags=policy_flags)
        if llm_validation["status"] != "reject":
            try:
                llm_result = parse_planner_result(llm_candidate_payload, default_query=query)
                llm_result = PlannerResult(**{**asdict(llm_result), "planner_source": PLANNER_SOURCE_LLM})
            except (TypeError, ValueError):
                llm_validation = {
                    "status": "reject",
                    "reason_codes": ["planner_llm_invalid_schema"],
                    "warnings": [],
                    "rejected_layers": ["parse"],
                    "reason_code": "planner_llm_invalid_schema",
                    "layers": {},
                }
        if llm_validation["status"] == "reject":
            planner = _serialize_planner_result(
                build_planner_fallback(
                    user_input=query,
                    standalone_query=query,
                    reason=str(llm_validation.get("reason_code") or "planner_llm_invalid_schema"),
                    fallback_type="planner_reject",
                    rejection_layer=(
                        [str(item).strip() for item in list(llm_validation.get("rejected_layers") or []) if str(item).strip()] or [None]
                    )[0],
                )
            )
        elif llm_result is not None:
            planner = _serialize_planner_result(llm_result)
            planner_execution_source = PLANNER_SOURCE_LLM
    shadow_record = None
    if llm_candidate_payload is not None:
        shadow_record = {
            "llm_decision": dict(llm_candidate_payload),
            "validation": dict(llm_validation or {}),
            "actual_execution_source": planner_execution_source,
            "review": {"label": None, "allowed_labels": ["accepted", "needs_followup", "incorrect", "blocked"]},
        }
    runtime["planner_validation"] = dict(llm_validation or {})
    runtime["planner_llm_diagnostics"] = dict(llm_diagnostics or {})
    runtime["shadow_compare"] = shadow_record
    runtime["planner_execution_source"] = planner_execution_source
    runtime["planner_candidates"] = {
        "llm": dict(llm_candidate_payload) if llm_candidate_payload is not None else None,
    }
    next_state["runtime"] = runtime
    next_state["planner_candidates"] = runtime["planner_candidates"]
    next_state["planner"] = planner
    next_state["execution_trace"] = list(next_state.get("execution_trace") or [])
    next_state["execution_trace"].append(
        {
            "step": "planner_runtime_decision",
            "state": "selected",
            "planner_source_mode": planner_source_mode,
            "planner_execution_source": planner_execution_source,
            "selected_decision_result": planner.get("decision_result"),
            "validation_status": (llm_validation or {}).get("status"),
            "validation_reason_codes": list((llm_validation or {}).get("reason_codes") or []),
            "shadow_diff_fields": [],
        }
    )
    return next_state


def _set_fallback(
    state: PlannerRuntimeState,
    *,
    fallback_type: Literal["planner", "tool"],
    reason: str,
    failed_tool: str | None = None,
) -> PlannerRuntimeState:
    next_state = dict(state)
    next_state["fallback"] = {"type": fallback_type, "reason": reason, "failed_tool": failed_tool}
    planner = dict(next_state.get("planner") or {})
    if fallback_type == "planner":
        planner["planner_fallback"] = True
        planner["planner_fallback_reason"] = reason
    next_state["planner"] = planner
    return next_state


def _normalize_tool_call(raw: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    action = str(raw.get("action") or "").strip()
    spec = RUNTIME_TOOL_REGISTRY.get(action)
    if spec is None:
        return None
    depends_on = [str(item).strip() for item in list(raw.get("depends_on") or []) if str(item).strip()]
    params = dict(raw.get("params") or {})
    if "produces" in raw:
        params["produces_override"] = raw.get("produces")
    tool_call = build_tool_call_envelope(
        spec,
        call_id=f"tool-{index}",
        query=str(raw.get("query") or "").strip(),
        arguments={"query": str(raw.get("query") or "").strip(), "params": params},
        depends_on_artifacts=depends_on,
        trace_context={"planner_step": index},
        execution_mode=spec.streaming_mode,
    )
    produces_raw = raw.get("produces")
    if isinstance(produces_raw, list):
        tool_call["produces"] = [str(item).strip() for item in produces_raw if str(item).strip()]
    elif produces_raw is not None:
        produce = str(produces_raw).strip()
        tool_call["produces"] = [produce] if produce else list(spec.produces)
    validation_errors = validate_tool_call_envelope(tool_call, RUNTIME_TOOL_REGISTRY)
    if validation_errors:
        tool_call["status"] = "failed"
        tool_call["tool_status"] = "failed"
        tool_call["validation_errors"] = validation_errors
    return tool_call


def _prepare_tool_calls(state: PlannerRuntimeState) -> PlannerRuntimeState:
    next_state = dict(state)
    planner = dict(next_state.get("planner") or {})
    decision_result = str(planner.get("decision_result") or "controlled_terminate")
    if decision_result not in {
        "clarify",
        "local_execute",
        "delegate_web",
        "delegate_research_assistant",
        "controlled_terminate",
    }:
        return _set_fallback(next_state, fallback_type="planner", reason=f"unsupported_decision_result:{decision_result}")
    raw_plan = list(planner.get("action_plan") or [])
    if decision_result in {"clarify", "delegate_web", "controlled_terminate"} and not raw_plan:
        next_state["tool_calls"] = []
        return next_state
    if not raw_plan:
        return _set_fallback(next_state, fallback_type="planner", reason="empty_action_plan")
    if len(raw_plan) > MAX_RUNTIME_TOOL_STEPS:
        return _set_fallback(next_state, fallback_type="planner", reason="action_plan_step_limit_exceeded")

    produced: set[str] = set()
    normalized_calls: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_plan, start=1):
        normalized = _normalize_tool_call(dict(raw), index=index)
        if normalized is None:
            fallback_tool = {
                "id": f"tool-{index}",
                "tool_name": str(raw.get("action") or "unknown").strip() or "unknown",
                "query": str(raw.get("query") or "").strip(),
                "depends_on": [str(item).strip() for item in list(raw.get("depends_on") or []) if str(item).strip()],
                "produces": [],
                "params": dict(raw.get("params") or {}),
                "route": "controlled_terminate",
                "passthrough": True,
                "status": "failed",
            }
            next_state["tool_calls"] = normalized_calls + [fallback_tool]
            next_state["tool_results"] = list(next_state.get("tool_results") or []) + [
                build_tool_result_envelope(
                    fallback_tool,
                    status="failed",
                    failure=build_tool_failure(
                        "unsupported_tool",
                        message=f"unsupported planner action: {fallback_tool['tool_name']}",
                        stop_plan=True,
                    ),
                    observability={"fallback_type": "planner"},
                )
            ]
            return _set_fallback(
                next_state,
                fallback_type="planner",
                reason=f"unsupported_tool:{str(raw.get('action') or 'unknown').strip() or 'unknown'}",
            )
        missing_dep = [dep for dep in normalized["depends_on"] if dep not in produced]
        if missing_dep:
            next_state["tool_calls"] = normalized_calls + [normalized]
            next_state["tool_results"] = list(next_state.get("tool_results") or []) + [
                build_tool_result_envelope(
                    normalized,
                    status="failed",
                    failure=build_tool_failure(
                        "missing_dependencies",
                        message=f"missing tool dependencies: {','.join(missing_dep)}",
                        failed_dependency=",".join(missing_dep),
                        stop_plan=True,
                        details={"missing_dependencies": missing_dep},
                    ),
                    observability={"fallback_type": "tool"},
                )
            ]
            return _set_fallback(
                next_state,
                fallback_type="tool",
                reason=f"missing_dependencies:{','.join(missing_dep)}",
                failed_tool=normalized["tool_name"],
            )
        normalized_calls.append(normalized)
        produced.update(normalized["produces"])

    next_state["tool_calls"] = normalized_calls
    next_state["execution_trace"] = list(next_state.get("execution_trace") or [])
    next_state["execution_trace"].append(
        {
            "step": "planner_runtime_prepare_tools",
            "state": "planned",
            "tool_names": [item["tool_name"] for item in normalized_calls],
            "tool_count": len(normalized_calls),
            "contract_version": RUNTIME_CONTRACT_VERSION,
            "call_ids": [item["call_id"] for item in normalized_calls],
        }
    )
    return next_state


def _build_route_state(state: PlannerRuntimeState, route: PlannerRuntimeRoute, *, passthrough: bool) -> PlannerRuntimeState:
    next_state = dict(state)
    planner = dict(next_state.get("planner") or {})
    tool_calls = list(next_state.get("tool_calls") or [])
    selected_tool = tool_calls[-1]["tool_name"] if tool_calls else None
    next_state["route"] = route
    next_state["selected_path"] = route if not passthrough else f"{route}_passthrough"
    next_state["planner_runtime_passthrough"] = passthrough
    next_state["planner_runtime_backend"] = "langgraph" if HAS_LANGGRAPH else "fallback"
    next_state["execution_trace"] = list(next_state.get("execution_trace") or [])
    next_state["execution_trace"].append(
        {
            "step": "planner_runtime_route",
            "state": "selected",
            "selected_path": next_state["selected_path"],
            "decision_result": planner.get("decision_result"),
            "primary_capability": planner.get("primary_capability"),
            "strictness": planner.get("strictness"),
            "knowledge_route": planner.get("knowledge_route"),
            "research_mode": planner.get("research_mode"),
            "tool_name": selected_tool,
            "passthrough": passthrough,
        }
    )
    return next_state


def _route_capability(state: PlannerRuntimeState) -> PlannerRuntimeState:
    planner = dict(state.get("planner") or {})
    decision_result = str(planner.get("decision_result") or "controlled_terminate")
    tool_calls = list(state.get("tool_calls") or [])
    fallback = dict(state.get("fallback") or {})
    if fallback.get("type") == "planner":
        fallback_state = dict(state)
        fallback_state.setdefault("tool_calls", [])
        return _build_route_state(fallback_state, "controlled_terminate", passthrough=False)
    if fallback.get("type") == "tool":
        fallback_state = dict(state)
        return _build_route_state(fallback_state, "controlled_terminate", passthrough=False)
    if decision_result == "controlled_terminate":
        return _build_route_state(dict(state), "controlled_terminate", passthrough=False)
    if decision_result == "delegate_web":
        return _build_route_state(dict(state), "web_delegate", passthrough=True)
    if decision_result == "clarify":
        clarify_state = dict(state)
        clarify_state["clarify_question"] = str(planner.get("clarify_question") or "请先说明你希望我聚焦的论文或研究主题。").strip()
        return _build_route_state(clarify_state, "clarify", passthrough=False)
    if not tool_calls:
        fallback_state = _set_fallback(dict(state), fallback_type="planner", reason="missing_tool_calls")
        return _build_route_state(fallback_state, "controlled_terminate", passthrough=False)
    paper_assistant_tool = next((tool for tool in tool_calls if str(tool.get("tool_name") or "") == "paper_assistant"), tool_calls[0])
    missing_prerequisites, clarify_question = _paper_assistant_missing_prerequisites(paper_assistant_tool)
    if missing_prerequisites and clarify_question:
        clarify_state = dict(state)
        clarify_state["tool_results"] = list(clarify_state.get("tool_results") or []) + [
            build_tool_result_envelope(
                paper_assistant_tool,
                status="clarify_required",
                output={"clarify_questions": [clarify_question]},
                warnings=["paper_assistant_missing_prerequisites"],
                observability={"missing_prerequisites": missing_prerequisites},
                failure=build_tool_failure(
                    "precondition_failed",
                    message="paper assistant missing prerequisites",
                    user_safe_message=clarify_question,
                    stop_plan=True,
                    details={"missing_prerequisites": missing_prerequisites},
                ),
            )
        ]
        clarify_state["short_circuit"] = {
            "triggered": True,
            "reason": "paper_assistant_missing_prerequisites",
            "step": paper_assistant_tool["tool_name"],
        }
        clarify_state["execution_trace"] = list(clarify_state.get("execution_trace") or [])
        clarify_state["execution_trace"].append(
            {
                "step": "planner_runtime_precondition_check",
                "state": "short_circuit",
                "action": paper_assistant_tool["tool_name"],
                "short_circuit_reason": "paper_assistant_missing_prerequisites",
                "missing_prerequisites": missing_prerequisites,
            }
        )
        clarify_state["clarify_question"] = clarify_question
        return _build_route_state(clarify_state, "clarify", passthrough=False)
    if decision_result == "delegate_research_assistant":
        return _build_route_state(dict(state), "research_assistant", passthrough=True)
    first_tool = tool_calls[0]
    return _build_route_state(dict(state), first_tool["route"], passthrough=bool(first_tool["passthrough"]))


def _hydrate_planner_result(planner_data: dict[str, Any], request: dict[str, Any]) -> PlannerResult:
    return parse_planner_result(planner_data, default_query=str(request.get("query") or ""))


def _run_route(
    state: PlannerRuntimeState,
    *,
    executor: RuntimeExecutor,
    on_stream_delta: Callable[[str], None] | None,
) -> PlannerRuntimeState:
    next_state = dict(state)
    request = next_state.get("request")
    payload = next_state.get("payload")
    if request is None or payload is None:
        raise RuntimeError("planner runtime request missing")
    planner_data = dict(next_state.get("planner") or {})
    fallback = dict(next_state.get("fallback") or {})
    tool_calls = [dict(item) for item in list(next_state.get("tool_calls") or [])]
    planner_result = _hydrate_planner_result(planner_data, dict(request))
    accumulated_results = [dict(item) for item in list(next_state.get("tool_results") or [])]
    executed_calls: list[dict[str, Any]] = []
    produced_artifacts: dict[str, Any] = {}
    latest_response = next_state.get("response")
    next_state["execution_trace"] = list(next_state.get("execution_trace") or [])
    if not tool_calls:
        next_state["tool_calls"] = []
        next_state["response"] = executor(
            payload,
            selected_path=str(next_state.get("selected_path") or "controlled_terminate"),
            on_stream_delta=on_stream_delta,
            runtime_fallback=bool(fallback.get("type")),
            runtime_fallback_reason=(str(fallback.get("reason")) if fallback.get("reason") is not None else None),
            planner_result=planner_result,
            tool_calls=[],
            prior_tool_results=[],
            available_artifacts={},
            record_runtime_observation=True,
        )
        return next_state
    for index, tool_call in enumerate(tool_calls):
        current_call = dict(tool_call)
        current_call["status"] = "dispatched"
        current_call["tool_status"] = "dispatched"
        depends_on = [str(item).strip() for item in list(current_call.get("depends_on_artifacts") or []) if str(item).strip()]
        current_call["resolved_artifacts"] = {name: produced_artifacts.get(name) for name in depends_on if name in produced_artifacts}
        executed_calls.append(current_call)
        if current_call["tool_name"] == "catalog_lookup":
            tool_result, latest_response, new_artifacts, trace_row = _catalog_lookup_result(current_call)
            accumulated_results.append(tool_result)
            current_call["status"] = tool_result["status"]
            current_call["tool_status"] = tool_result["status"]
            produced_artifacts.update(new_artifacts)
            next_state["execution_trace"].append(trace_row)
            if tool_result["status"] != "succeeded":
                next_state["tool_calls"] = executed_calls + [dict(item) for item in tool_calls[index + 1 :]]
                next_state["tool_results"] = accumulated_results
                next_state["response"] = latest_response
                next_state["short_circuit"] = {
                    "triggered": True,
                    "reason": tool_result["failure"].get("failure_type") or "catalog_lookup_empty",
                    "step": current_call["tool_name"],
                }
                next_state["fallback"] = {
                    "type": "tool",
                    "reason": str(tool_result["failure"].get("failure_type") or "empty_result"),
                    "failed_tool": current_call["tool_name"],
                }
                return next_state
            continue
        current_selected_path = _selected_path_for_tool(current_call)
        latest_response = executor(
            payload,
            selected_path=current_selected_path,
            on_stream_delta=on_stream_delta if index == len(tool_calls) - 1 else None,
            runtime_fallback=bool(fallback.get("type")),
            runtime_fallback_reason=(str(fallback.get("reason")) if fallback.get("reason") is not None else None),
            planner_result=planner_result,
            tool_calls=[dict(item) for item in executed_calls],
            active_tool_call=current_call,
            prior_tool_results=[dict(item) for item in accumulated_results],
            available_artifacts=dict(produced_artifacts),
            record_runtime_observation=index == len(tool_calls) - 1,
        )
        response_sources = _serialize_response_sources(latest_response)
        response_sources.extend(_tool_specific_sources(current_call["tool_name"], latest_response))
        artifacts_payload = [
            {"artifact_name": artifact_name, "available": True}
            for artifact_name in list(current_call.get("produces") or [])
        ]
        tool_result = build_tool_result_envelope(
            current_call,
            status="succeeded",
            output={"selected_path": current_selected_path},
            artifacts=artifacts_payload,
            sources=response_sources,
            observability=_response_metadata(latest_response),
        )
        accumulated_results.append(tool_result)
        current_call["status"] = "succeeded"
        current_call["tool_status"] = "succeeded"
        for artifact_name in list(current_call.get("produces") or []):
            produced_artifacts[artifact_name] = True
        next_state["execution_trace"].append(
            {
                "step": "planner_runtime_tool_execution",
                "action": current_call["tool_name"],
                "call_id": current_call.get("call_id") or current_call.get("id"),
                "state": "completed",
                "tool_status": "succeeded",
                "failure_type": None,
                "streaming_mode": current_call.get("streaming_mode"),
                "evidence_policy": current_call.get("evidence_policy"),
                "produced_artifacts": list(current_call.get("produces") or []),
                "depends_on_artifacts": depends_on,
            }
        )
    next_state["tool_calls"] = executed_calls
    next_state["tool_results"] = accumulated_results
    next_state["response"] = latest_response
    if tool_calls:
        next_state["selected_path"] = _selected_path_for_tool(executed_calls[-1])
    return next_state


def _route_next(state: PlannerRuntimeState) -> str:
    route = str(state.get("route") or "controlled_terminate")
    if route == "clarify":
        return "run_runtime_clarify"
    if route == "fact_qa":
        return "run_fact_qa_path"
    if route in {"catalog", "summary", "control", "research_assistant"}:
        return "run_compat_path"
    if route == "web_delegate":
        return "run_web_delegate_path"
    return "run_controlled_terminate"


def _build_graph(
    *,
    fact_qa_executor: RuntimeExecutor,
    compat_executor: RuntimeExecutor,
    legacy_executor: RuntimeExecutor,
    on_stream_delta: Callable[[str], None] | None,
):
    def _run_fact_qa(state: PlannerRuntimeState) -> PlannerRuntimeState:
        return _run_route(state, executor=fact_qa_executor, on_stream_delta=on_stream_delta)

    def _run_compat(state: PlannerRuntimeState) -> PlannerRuntimeState:
        return _run_route(state, executor=compat_executor, on_stream_delta=on_stream_delta)

    def _run_web_delegate(state: PlannerRuntimeState) -> PlannerRuntimeState:
        return _run_route(state, executor=legacy_executor, on_stream_delta=on_stream_delta)

    def _run_runtime_clarify(state: PlannerRuntimeState) -> PlannerRuntimeState:
        next_state = dict(state)
        question = str(next_state.get("clarify_question") or "请先说明你希望我聚焦的论文或研究主题。").strip()
        next_state["selected_path"] = "planner_runtime_clarify"
        next_state["response"] = _build_runtime_clarify_response(next_state.get("payload"), question)
        next_state["planner_runtime_passthrough"] = False
        return next_state

    def _run_controlled_terminate(state: PlannerRuntimeState) -> PlannerRuntimeState:
        next_state = dict(state)
        fallback = dict(next_state.get("fallback") or {})
        planner = dict(next_state.get("planner") or {})
        if fallback.get("type") is None and str(planner.get("decision_result") or "") != "controlled_terminate":
            next_state = _set_fallback(next_state, fallback_type="planner", reason="route_fallback")
        next_state["selected_path"] = "controlled_terminate"
        next_state["route"] = "controlled_terminate"
        next_state["planner_runtime_passthrough"] = False
        next_state["controlled_termination"] = _build_controlled_termination(next_state)
        next_state["response"] = _build_controlled_terminate_response(next_state.get("payload"), next_state["controlled_termination"])
        return next_state

    if not HAS_LANGGRAPH or StateGraph is None:
        return None, {
            "load_request_context": _load_request_context,
            "plan_chat_request": _plan_chat_request,
            "prepare_tool_calls": _prepare_tool_calls,
            "route_capability": _route_capability,
            "run_fact_qa_path": _run_fact_qa,
            "run_compat_path": _run_compat,
            "run_web_delegate_path": _run_web_delegate,
            "run_runtime_clarify": _run_runtime_clarify,
            "run_controlled_terminate": _run_controlled_terminate,
        }

    graph = StateGraph(PlannerRuntimeState)
    graph.add_node("load_request_context", _load_request_context)
    graph.add_node("plan_chat_request", _plan_chat_request)
    graph.add_node("prepare_tool_calls", _prepare_tool_calls)
    graph.add_node("route_capability", _route_capability)
    graph.add_node("run_fact_qa_path", _run_fact_qa)
    graph.add_node("run_compat_path", _run_compat)
    graph.add_node("run_web_delegate_path", _run_web_delegate)
    graph.add_node("run_runtime_clarify", _run_runtime_clarify)
    graph.add_node("run_controlled_terminate", _run_controlled_terminate)
    graph.set_entry_point("load_request_context")
    graph.add_edge("load_request_context", "plan_chat_request")
    graph.add_edge("plan_chat_request", "prepare_tool_calls")
    graph.add_edge("prepare_tool_calls", "route_capability")
    graph.add_conditional_edges(
        "route_capability",
        _route_next,
        {
            "run_fact_qa_path": "run_fact_qa_path",
            "run_compat_path": "run_compat_path",
            "run_web_delegate_path": "run_web_delegate_path",
            "run_runtime_clarify": "run_runtime_clarify",
            "run_controlled_terminate": "run_controlled_terminate",
        },
    )
    graph.add_edge("run_fact_qa_path", END)
    graph.add_edge("run_compat_path", END)
    graph.add_edge("run_web_delegate_path", END)
    graph.add_edge("run_runtime_clarify", END)
    graph.add_edge("run_controlled_terminate", END)
    return graph.compile(), None


def _run_without_langgraph(
    state: PlannerRuntimeState,
    nodes: dict[str, Callable[[PlannerRuntimeState], PlannerRuntimeState]],
) -> PlannerRuntimeState:
    current = nodes["load_request_context"](state)
    current = nodes["plan_chat_request"](current)
    current = nodes["prepare_tool_calls"](current)
    current = nodes["route_capability"](current)
    route_next = _route_next(current)
    return nodes[route_next](current)


def run_planner_runtime(
    payload: Any,
    *,
    fact_qa_executor: RuntimeExecutor,
    compat_executor: RuntimeExecutor,
    legacy_executor: RuntimeExecutor,
    on_stream_delta: Callable[[str], None] | None = None,
) -> PlannerRuntimeRunResult:
    initial_state: PlannerRuntimeState = {
        "payload": payload,
        "request": {
            "sessionId": str(getattr(payload, "sessionId")),
            "mode": str(getattr(payload, "mode")),
            "query": str(getattr(payload, "query")),
            "traceId": getattr(payload, "traceId", None),
            "history": [asdict(item) if hasattr(item, "__dataclass_fields__") else item.model_dump() for item in getattr(payload, "history", [])],
            "configPath": str(getattr(payload, "configPath", None) or (CONFIGS_DIR / "default.yaml")),
        },
    }
    compiled_graph, fallback_nodes = _build_graph(
        fact_qa_executor=fact_qa_executor,
        compat_executor=compat_executor,
        legacy_executor=legacy_executor,
        on_stream_delta=on_stream_delta,
    )
    try:
        if compiled_graph is not None:
            final_state = compiled_graph.invoke(initial_state)
        else:
            final_state = _run_without_langgraph(initial_state, fallback_nodes or {})
    except Exception as exc:
        planner_result = build_planner_fallback(
            user_input=str(getattr(payload, "query", "")),
            standalone_query=str(getattr(payload, "query", "")),
            reason="planner_runtime_exception",
        )
        planner_data = _serialize_planner_result(
            build_planner_fallback(
                user_input=str(getattr(payload, "query", "")),
                standalone_query=str(getattr(payload, "query", "")),
                reason="planner_runtime_exception",
                fallback_type="runtime_exception",
            )
        )
        controlled_termination = {
            "type": "runtime_exception",
            "reason": "planner_runtime_exception",
            "rejection_reason": "planner_runtime_exception",
            "rejection_layer": "runtime",
            "source": "planner",
            "user_visible_posture": "refuse",
            "clarify_question": None,
            "message": "当前系统暂时无法完成该请求，请稍后重试。",
        }
        response = _build_controlled_terminate_response(payload, controlled_termination)
        final_state = {
            "planner": planner_data,
            "runtime": _default_runtime_contract(),
            "tool_calls": [],
            "tool_results": [],
            "fallback": {"type": "planner", "reason": str(exc), "failed_tool": None},
            "response": response,
            "selected_path": "controlled_terminate",
            "execution_trace": [
                {
                    "step": "planner_runtime_route",
                    "state": "selected",
                    "selected_path": "controlled_terminate",
                    "primary_capability": planner_result.primary_capability,
                    "strictness": planner_result.strictness,
                    "tool_name": None,
                    "passthrough": False,
                }
            ],
            "short_circuit": {"triggered": False, "reason": None, "step": None},
            "truncated": False,
            "planner_runtime_backend": "langgraph" if HAS_LANGGRAPH else "fallback",
            "planner_runtime_passthrough": False,
            "controlled_termination": controlled_termination,
        }
    if not final_state.get("tool_results"):
        fallback = dict(final_state.get("fallback") or {})
        tool_calls = [dict(item) for item in list(final_state.get("tool_calls") or [])]
        reason = str(fallback.get("reason") or "").strip()
        if tool_calls and fallback.get("type") == "planner":
            final_state["tool_results"] = [
                build_tool_result_envelope(
                    tool_calls[0],
                    status="failed",
                    failure=build_tool_failure(
                        "execution_error",
                        message=reason or "planner fallback",
                        stop_plan=True,
                    ),
                    observability={"fallback_type": "planner"},
                )
            ]
        elif tool_calls and fallback.get("type") == "tool":
            final_state["tool_results"] = [
                build_tool_result_envelope(
                    tool_calls[0],
                    status="failed",
                    failure=build_tool_failure(
                        "execution_error",
                        message=reason or "tool fallback",
                        stop_plan=True,
                    ),
                    observability={"fallback_type": "tool"},
                )
            ]

    fallback = dict(final_state.get("fallback") or {})
    controlled_termination = (
        dict(final_state.get("controlled_termination") or {})
        if str(final_state.get("selected_path") or "") == "controlled_terminate"
        else None
    )
    planner_runtime_fallback = bool(fallback.get("type") == "planner")
    planner_runtime_fallback_reason = fallback.get("reason") if fallback.get("type") == "planner" else None
    if controlled_termination and not planner_runtime_fallback:
        planner_runtime_fallback = str(controlled_termination.get("type") or "") in {"planner_reject", "runtime_exception"}
        if planner_runtime_fallback:
            planner_runtime_fallback_reason = controlled_termination.get("reason")
    planner_data = dict(final_state.get("planner") or {})
    decision_result = str(planner_data.get("decision_result") or "").strip()
    interaction_decision_source = "planner:execute"
    final_interaction_authority = "planner"
    final_user_visible_posture = "execute"
    posture_override_forbidden = False
    if decision_result == "clarify":
        interaction_decision_source = "planner:clarify"
        final_user_visible_posture = "clarify"
    elif decision_result in {"delegate_web", "delegate_research_assistant"}:
        interaction_decision_source = f"planner:{decision_result}"
        final_user_visible_posture = "delegate"
    elif controlled_termination:
        interaction_decision_source = f"planner_policy:{controlled_termination.get('type') or 'controlled_terminate'}"
        final_interaction_authority = "planner_policy"
        final_user_visible_posture = str(controlled_termination.get("user_visible_posture") or "refuse")
    observation = {
        "planner_runtime_used": True,
        "planner_runtime_backend": final_state.get("planner_runtime_backend", "fallback"),
        "planner_runtime_fallback": planner_runtime_fallback,
        "planner_runtime_fallback_reason": planner_runtime_fallback_reason,
        "planner_runtime_passthrough": bool(final_state.get("planner_runtime_passthrough", False)),
        "planner_shell_used": True,
        "planner_shell_backend": final_state.get("planner_runtime_backend", "fallback"),
        "planner_shell_fallback": planner_runtime_fallback,
        "planner_shell_fallback_reason": planner_runtime_fallback_reason,
        "planner_shell_passthrough": bool(final_state.get("planner_runtime_passthrough", False)),
        "selected_path": str(final_state.get("selected_path") or "controlled_terminate"),
        "planner": planner_data,
        "runtime_contract_version": final_state.get("runtime", {}).get("version", RUNTIME_CONTRACT_VERSION),
        "runtime_stable_fields": list(final_state.get("runtime", {}).get("stable_fields", list(RUNTIME_STABLE_FIELDS))),
        "runtime_envelope_fields": list(final_state.get("runtime", {}).get("envelope_fields", list(RUNTIME_ENVELOPE_FIELDS))),
        "planner_input_context": dict(final_state.get("runtime", {}).get("planner_input_context", {})),
        "planner_source_mode": final_state.get("runtime", {}).get("planner_source_mode", DEFAULT_PLANNER_SOURCE_MODE),
        "planner_execution_source": final_state.get("runtime", {}).get("planner_execution_source", normalize_planner_source(dict(final_state.get("planner") or {}).get("planner_source"))),
        "planner_llm_diagnostics": dict(final_state.get("runtime", {}).get("planner_llm_diagnostics", {})),
        "planner_validation": dict(final_state.get("runtime", {}).get("planner_validation", {})),
        "shadow_compare": final_state.get("runtime", {}).get("shadow_compare"),
        "planner_candidates": final_state.get("runtime", {}).get("planner_candidates"),
        "capability_registry": list(final_state.get("runtime", {}).get("capability_registry", [])),
        "tool_registry_entries": list(final_state.get("runtime", {}).get("tool_registry_entries", [])),
        "tool_calls": [dict(item) for item in list(final_state.get("tool_calls") or [])],
        "tool_results": [dict(item) for item in list(final_state.get("tool_results") or [])],
        "tool_fallback": bool(fallback.get("type") == "tool"),
        "tool_fallback_reason": fallback.get("reason") if fallback.get("type") == "tool" else None,
        "failed_tool": fallback.get("failed_tool"),
        "execution_trace": list(final_state.get("execution_trace") or []),
        "short_circuit": dict(final_state.get("short_circuit") or {"triggered": False, "reason": None, "step": None}),
        "truncated": bool(final_state.get("truncated", False)),
        "controlled_termination": controlled_termination,
        "rejection_reason": (
            (controlled_termination or {}).get("rejection_reason")
            or dict(final_state.get("runtime", {}).get("planner_validation", {}) or {}).get("reason_code")
        ),
        "rejection_layer": (
            (controlled_termination or {}).get("rejection_layer")
            or (
                [str(item).strip() for item in list(dict(final_state.get("runtime", {}).get("planner_validation", {}) or {}).get("rejected_layers") or []) if str(item).strip()] or [None]
            )[0]
        ),
        "failure_settlement_source": (controlled_termination or {}).get("type"),
        "interaction_decision_source": interaction_decision_source,
        "final_interaction_authority": final_interaction_authority,
        "final_user_visible_posture": final_user_visible_posture,
        "posture_override_forbidden": posture_override_forbidden,
    }
    return {"response": final_state["response"], "observation": observation}


# Backward-compatible aliases while the codebase transitions away from "shell" wording.
PlannerRoute = PlannerRuntimeRoute
PlannerShellPayload = PlannerRuntimePayload
PlannerShellState = PlannerRuntimeState
RouteExecutor = RuntimeExecutor
PlannerShellRunResult = PlannerRuntimeRunResult
run_planner_shell = run_planner_runtime
