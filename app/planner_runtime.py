from __future__ import annotations

from dataclasses import asdict
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
    build_rule_based_plan,
    compose_catalog_answer,
    execute_catalog_lookup,
    normalize_planner_source,
    paper_assistant_clarification,
)
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
    "legacy_fallback",
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


class PlannerRuntimePayload(TypedDict, total=False):
    sessionId: str
    mode: str
    query: str
    traceId: str | None
    history: list[dict[str, str]]


class PlannerRuntimeState(TypedDict, total=False):
    payload: Any
    request: PlannerRuntimePayload
    planner: dict[str, Any]
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
    return {
        "decision_version": result.decision_version,
        "user_goal": result.user_goal,
        "planner_used": result.planner_used,
        "planner_source": normalize_planner_source(result.planner_source),
        "planner_fallback": result.planner_fallback,
        "planner_fallback_reason": result.planner_fallback_reason,
        "planner_confidence": result.planner_confidence,
        "is_new_topic": result.is_new_topic,
        "should_clear_pending_clarify": result.should_clear_pending_clarify,
        "relation_to_previous": result.relation_to_previous,
        "standalone_query": result.standalone_query,
        "primary_capability": result.primary_capability,
        "strictness": result.strictness,
        "decision_result": result.decision_result,
        "knowledge_route": result.knowledge_route,
        "research_mode": result.research_mode,
        "requires_clarification": result.requires_clarification,
        "selected_tools_or_skills": list(result.selected_tools_or_skills or []),
        "fallback": dict(result.fallback or {}),
        "clarify_question": result.clarify_question,
        "action_plan": list(result.action_plan or []),
    }


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
    }


def _serialize_capability_registry() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in RUNTIME_TOOL_REGISTRY.values():
        rows.append(serialize_tool_registry_entry(spec))
    rows.extend(dict(item) for item in RUNTIME_DELEGATE_CAPABILITIES)
    rows.sort(key=lambda row: str(row.get("name") or ""))
    return rows


def _planner_policy_flags() -> dict[str, Any]:
    return {
        "allow_web_delegation": True,
        "allow_research_assistant": True,
        "force_local_first": False,
        "max_steps": MAX_RUNTIME_TOOL_STEPS,
    }


def _build_planner_input_context(request: dict[str, Any]) -> dict[str, Any]:
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
        "policy_flags": _planner_policy_flags(),
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
    route = str(tool_call.get("route") or "legacy_fallback")
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
    planner_input_context = _build_planner_input_context(request)
    runtime = dict(next_state.get("runtime") or {})
    runtime["planner_input_context"] = planner_input_context
    next_state["runtime"] = runtime
    planner_result = build_rule_based_plan(
        user_input=query,
        standalone_query=query,
        dialog_state="answering",
        history_topic_anchors=list(planner_input_context.get("conversation_context", {}).get("recent_topic_anchors") or []),
        pending_clarify=planner_input_context.get("conversation_context", {}).get("pending_clarify"),
        capability_registry=list(planner_input_context.get("capability_registry") or []),
        policy_flags=dict(planner_input_context.get("policy_flags") or {}),
    )
    next_state["planner"] = _serialize_planner_result(planner_result)
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
    decision_result = str(planner.get("decision_result") or "legacy_fallback")
    if decision_result not in {
        "clarify",
        "local_execute",
        "delegate_web",
        "delegate_research_assistant",
        "legacy_fallback",
    }:
        return _set_fallback(next_state, fallback_type="planner", reason=f"unsupported_decision_result:{decision_result}")
    raw_plan = list(planner.get("action_plan") or [])
    if decision_result in {"clarify", "delegate_web", "legacy_fallback"} and not raw_plan:
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
                "route": "legacy_fallback",
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
    decision_result = str(planner.get("decision_result") or "legacy_fallback")
    tool_calls = list(state.get("tool_calls") or [])
    fallback = dict(state.get("fallback") or {})
    if fallback.get("type") == "planner":
        fallback_state = dict(state)
        fallback_state.setdefault("tool_calls", [])
        return _build_route_state(fallback_state, "legacy_fallback", passthrough=True)
    if fallback.get("type") == "tool":
        fallback_state = dict(state)
        return _build_route_state(fallback_state, "legacy_fallback", passthrough=True)
    if decision_result == "legacy_fallback":
        return _build_route_state(dict(state), "legacy_fallback", passthrough=True)
    if decision_result == "delegate_web":
        return _build_route_state(dict(state), "web_delegate", passthrough=True)
    if decision_result == "clarify":
        clarify_state = dict(state)
        clarify_state["clarify_question"] = str(planner.get("clarify_question") or "请先说明你希望我聚焦的论文或研究主题。").strip()
        return _build_route_state(clarify_state, "clarify", passthrough=False)
    if not tool_calls:
        fallback_state = _set_fallback(dict(state), fallback_type="planner", reason="missing_tool_calls")
        return _build_route_state(fallback_state, "legacy_fallback", passthrough=True)
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
    return PlannerResult(
        decision_version=str(planner_data.get("decision_version") or "planner-policy-v1"),
        user_goal=str(planner_data.get("user_goal") or request.get("query") or ""),
        planner_used=bool(planner_data.get("planner_used", False)),
        planner_source=normalize_planner_source(str(planner_data.get("planner_source") or "fallback")),
        planner_fallback=bool(planner_data.get("planner_fallback", False)),
        planner_fallback_reason=planner_data.get("planner_fallback_reason"),
        planner_confidence=float(planner_data.get("planner_confidence", 0.0)),
        is_new_topic=bool(planner_data.get("is_new_topic", False)),
        should_clear_pending_clarify=bool(planner_data.get("should_clear_pending_clarify", False)),
        relation_to_previous=str(planner_data.get("relation_to_previous") or "same_topic_or_no_pending"),
        standalone_query=str(planner_data.get("standalone_query") or request.get("query") or ""),
        primary_capability=str(planner_data.get("primary_capability") or "fact_qa"),
        strictness=str(planner_data.get("strictness") or "strict_fact"),
        decision_result=str(planner_data.get("decision_result") or "legacy_fallback"),
        knowledge_route=str(planner_data.get("knowledge_route") or "local"),
        research_mode=str(planner_data.get("research_mode") or "none"),
        requires_clarification=bool(planner_data.get("requires_clarification", False)),
        selected_tools_or_skills=[str(item).strip() for item in list(planner_data.get("selected_tools_or_skills") or []) if str(item).strip()],
        fallback=dict(planner_data.get("fallback") or {}),
        clarify_question=(
            str(planner_data.get("clarify_question")).strip()
            if planner_data.get("clarify_question") is not None
            else None
        ),
        action_plan=list(planner_data.get("action_plan") or []),
    )


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
            selected_path=str(next_state.get("selected_path") or "legacy_fallback"),
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
    route = str(state.get("route") or "legacy_fallback")
    if route == "clarify":
        return "run_runtime_clarify"
    if route == "fact_qa":
        return "run_fact_qa_path"
    if route in {"catalog", "summary", "control", "research_assistant"}:
        return "run_compat_path"
    if route == "web_delegate":
        return "run_web_delegate_path"
    return "fallback_to_legacy_qa"


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

    def _run_legacy(state: PlannerRuntimeState) -> PlannerRuntimeState:
        fallback_state = dict(state)
        fallback = dict(fallback_state.get("fallback") or {})
        if fallback.get("type") is None:
            fallback_state = _set_fallback(fallback_state, fallback_type="planner", reason="route_fallback")
        fallback_state["selected_path"] = "legacy_fallback"
        fallback_state["route"] = "legacy_fallback"
        fallback_state["planner_runtime_passthrough"] = True
        return _run_route(fallback_state, executor=legacy_executor, on_stream_delta=on_stream_delta)

    def _run_runtime_clarify(state: PlannerRuntimeState) -> PlannerRuntimeState:
        next_state = dict(state)
        question = str(next_state.get("clarify_question") or "请先说明你希望我聚焦的论文或研究主题。").strip()
        next_state["selected_path"] = "planner_runtime_clarify"
        next_state["response"] = _build_runtime_clarify_response(next_state.get("payload"), question)
        next_state["planner_runtime_passthrough"] = False
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
            "fallback_to_legacy_qa": _run_legacy,
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
    graph.add_node("fallback_to_legacy_qa", _run_legacy)
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
            "fallback_to_legacy_qa": "fallback_to_legacy_qa",
        },
    )
    graph.add_edge("run_fact_qa_path", END)
    graph.add_edge("run_compat_path", END)
    graph.add_edge("run_web_delegate_path", END)
    graph.add_edge("run_runtime_clarify", END)
    graph.add_edge("fallback_to_legacy_qa", END)
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
        response = legacy_executor(
            payload,
            selected_path="legacy_fallback",
            on_stream_delta=on_stream_delta,
            runtime_fallback=True,
            runtime_fallback_reason=str(exc),
            planner_result=planner_result,
            tool_calls=[],
        )
        final_state = {
            "planner": _serialize_planner_result(planner_result),
            "runtime": _default_runtime_contract(),
            "tool_calls": [],
            "tool_results": [],
            "fallback": {"type": "planner", "reason": str(exc), "failed_tool": None},
            "response": response,
            "selected_path": "legacy_fallback",
            "execution_trace": [
                {
                    "step": "planner_runtime_route",
                    "state": "selected",
                    "selected_path": "legacy_fallback",
                    "primary_capability": planner_result.primary_capability,
                    "strictness": planner_result.strictness,
                    "tool_name": None,
                    "passthrough": True,
                }
            ],
            "short_circuit": {"triggered": False, "reason": None, "step": None},
            "truncated": False,
            "planner_runtime_backend": "langgraph" if HAS_LANGGRAPH else "fallback",
            "planner_runtime_passthrough": True,
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
    observation = {
        "planner_runtime_used": True,
        "planner_runtime_backend": final_state.get("planner_runtime_backend", "fallback"),
        "planner_runtime_fallback": bool(fallback.get("type") == "planner"),
        "planner_runtime_fallback_reason": fallback.get("reason") if fallback.get("type") == "planner" else None,
        "planner_runtime_passthrough": bool(final_state.get("planner_runtime_passthrough", False)),
        "planner_shell_used": True,
        "planner_shell_backend": final_state.get("planner_runtime_backend", "fallback"),
        "planner_shell_fallback": bool(fallback.get("type") == "planner"),
        "planner_shell_fallback_reason": fallback.get("reason") if fallback.get("type") == "planner" else None,
        "planner_shell_passthrough": bool(final_state.get("planner_runtime_passthrough", False)),
        "selected_path": str(final_state.get("selected_path") or "legacy_fallback"),
        "planner": dict(final_state.get("planner") or {}),
        "runtime_contract_version": final_state.get("runtime", {}).get("version", RUNTIME_CONTRACT_VERSION),
        "runtime_stable_fields": list(final_state.get("runtime", {}).get("stable_fields", list(RUNTIME_STABLE_FIELDS))),
        "runtime_envelope_fields": list(final_state.get("runtime", {}).get("envelope_fields", list(RUNTIME_ENVELOPE_FIELDS))),
        "planner_input_context": dict(final_state.get("runtime", {}).get("planner_input_context", {})),
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
    }
    return {"response": final_state["response"], "observation": observation}


# Backward-compatible aliases while the codebase transitions away from "shell" wording.
PlannerRoute = PlannerRuntimeRoute
PlannerShellPayload = PlannerRuntimePayload
PlannerShellState = PlannerRuntimeState
RouteExecutor = RuntimeExecutor
PlannerShellRunResult = PlannerRuntimeRunResult
run_planner_shell = run_planner_runtime
