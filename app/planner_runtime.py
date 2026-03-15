from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal, Protocol, TypedDict

from app.capability_planner import (
    PlannerResult,
    build_planner_fallback,
    build_rule_based_plan,
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


@dataclass(frozen=True)
class RuntimeToolSpec:
    name: str
    kind: Literal["tool", "skill"]
    route: PlannerRuntimeRoute
    passthrough: bool
    capability_tags: tuple[str, ...] = ()
    knowledge_scope: Literal["local", "web", "hybrid"] = "local"
    supports_research_mode: bool = False
    prerequisites: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()


RUNTIME_TOOL_REGISTRY: dict[str, RuntimeToolSpec] = {
    "fact_qa": RuntimeToolSpec(
        name="fact_qa",
        kind="tool",
        route="fact_qa",
        passthrough=False,
        capability_tags=("fact_qa", "strict_fact"),
    ),
    "catalog_lookup": RuntimeToolSpec(
        name="catalog_lookup",
        kind="tool",
        route="catalog",
        passthrough=True,
        capability_tags=("catalog", "local_retrieval"),
        produces=("paper_set",),
    ),
    "cross_doc_summary": RuntimeToolSpec(
        name="cross_doc_summary",
        kind="tool",
        route="summary",
        passthrough=True,
        capability_tags=("summary", "comparison"),
        prerequisites=("paper_set_optional",),
    ),
    "control": RuntimeToolSpec(
        name="control",
        kind="tool",
        route="control",
        passthrough=True,
        capability_tags=("control", "formatting"),
    ),
    "paper_assistant": RuntimeToolSpec(
        name="paper_assistant",
        kind="skill",
        route="research_assistant",
        passthrough=True,
        capability_tags=("research_assistant", "summary", "guidance"),
        supports_research_mode=True,
        prerequisites=("research_topic_or_paper_scope",),
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
    return {
        "version": RUNTIME_CONTRACT_VERSION,
        "stable_fields": list(RUNTIME_STABLE_FIELDS),
        "envelope_fields": list(RUNTIME_ENVELOPE_FIELDS),
        "tool_registry": sorted(RUNTIME_TOOL_REGISTRY),
        "capability_registry": _serialize_capability_registry(),
        "planner_input_segments": ["request", "conversation_context", "capability_registry", "policy_flags"],
    }


def _serialize_capability_registry() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in RUNTIME_TOOL_REGISTRY.values():
        rows.append(
            {
                "name": spec.name,
                "kind": spec.kind,
                "capability_tags": list(spec.capability_tags),
                "knowledge_scope": spec.knowledge_scope,
                "supports_research_mode": spec.supports_research_mode,
                "prerequisites": list(spec.prerequisites),
            }
        )
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


def _tool_error(code: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if details:
        error["details"] = dict(details)
    return error


def build_tool_result_envelope(
    tool_call: dict[str, Any],
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_call_id": tool_call.get("id"),
        "tool_name": tool_call.get("tool_name"),
        "status": status,
        "result": dict(result or {}),
        "error": dict(error or {}),
        "metadata": dict(metadata or {}),
        "produces": list(tool_call.get("produces") or []),
    }


def _response_metadata(response: Any) -> dict[str, Any]:
    sources = getattr(response, "sources", None)
    return {
        "trace_id": getattr(response, "traceId", None),
        "source_count": len(sources) if isinstance(sources, list) else None,
    }


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
    produces_raw = raw.get("produces")
    produces: list[str]
    if isinstance(produces_raw, list):
        produces = [str(item).strip() for item in produces_raw if str(item).strip()]
    elif produces_raw is None:
        produces = list(spec.produces)
    else:
        produces = [str(produces_raw).strip()] if str(produces_raw).strip() else list(spec.produces)
    depends_on = [str(item).strip() for item in list(raw.get("depends_on") or []) if str(item).strip()]
    return {
        "id": f"tool-{index}",
        "tool_name": spec.name,
        "query": str(raw.get("query") or "").strip(),
        "depends_on": depends_on,
        "produces": produces,
        "params": dict(raw.get("params") or {}),
        "route": spec.route,
        "passthrough": spec.passthrough,
        "status": "planned",
    }


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
                    error=_tool_error(
                        "unsupported_tool",
                        f"unsupported planner action: {fallback_tool['tool_name']}",
                    ),
                    metadata={"fallback_type": "planner"},
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
                    error=_tool_error(
                        "missing_dependencies",
                        f"missing tool dependencies: {','.join(missing_dep)}",
                        details={"missing_dependencies": missing_dep},
                    ),
                    metadata={"fallback_type": "tool"},
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
        }
    )
    return next_state


def _build_route_state(state: PlannerRuntimeState, route: PlannerRuntimeRoute, *, passthrough: bool) -> PlannerRuntimeState:
    next_state = dict(state)
    planner = dict(next_state.get("planner") or {})
    tool_calls = list(next_state.get("tool_calls") or [])
    selected_tool = tool_calls[0]["tool_name"] if tool_calls else None
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
                result={"clarify_questions": [clarify_question]},
                metadata={"missing_prerequisites": missing_prerequisites},
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
    if tool_calls:
        tool_calls[0]["status"] = "dispatched"
    planner_result = _hydrate_planner_result(planner_data, dict(request))
    next_state["tool_calls"] = tool_calls
    next_state["response"] = executor(
        payload,
        selected_path=str(next_state.get("selected_path") or "legacy_fallback"),
        on_stream_delta=on_stream_delta,
        runtime_fallback=bool(fallback.get("type")),
        runtime_fallback_reason=(str(fallback.get("reason")) if fallback.get("reason") is not None else None),
        planner_result=planner_result,
        tool_calls=tool_calls,
    )
    if tool_calls and not next_state.get("tool_results"):
        next_state["tool_results"] = [
            build_tool_result_envelope(
                tool_calls[0],
                status="succeeded",
                result={"selected_path": str(next_state.get("selected_path") or "legacy_fallback")},
                metadata=_response_metadata(next_state["response"]),
            )
        ]
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
                    error=_tool_error("planner_fallback", reason or "planner fallback"),
                    metadata={"fallback_type": "planner"},
                )
            ]
        elif tool_calls and fallback.get("type") == "tool":
            final_state["tool_results"] = [
                build_tool_result_envelope(
                    tool_calls[0],
                    status="failed",
                    error=_tool_error("tool_fallback", reason or "tool fallback"),
                    metadata={"fallback_type": "tool"},
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
