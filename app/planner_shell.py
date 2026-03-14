from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Literal, Protocol, TypedDict

from app.capability_planner import PlannerResult, build_planner_fallback, build_rule_based_plan

try:  # pragma: no cover - exercised indirectly when langgraph is installed
    from langgraph.graph import END, StateGraph

    HAS_LANGGRAPH = True
except Exception:  # pragma: no cover - fallback path used in tests when dependency is absent
    END = "__end__"
    StateGraph = None
    HAS_LANGGRAPH = False


PlannerRoute = Literal["fact_qa", "catalog", "summary", "control", "legacy_fallback"]


class PlannerShellPayload(TypedDict, total=False):
    sessionId: str
    mode: str
    query: str
    traceId: str | None
    history: list[dict[str, str]]


class PlannerShellState(TypedDict, total=False):
    payload: Any
    request: PlannerShellPayload
    planner: dict[str, Any]
    route: PlannerRoute
    response: Any
    selected_path: str
    execution_trace: list[dict[str, Any]]
    short_circuit: dict[str, Any]
    truncated: bool
    planner_shell_fallback: bool
    planner_shell_fallback_reason: str | None
    planner_shell_backend: str
    planner_shell_passthrough: bool


class RouteExecutor(Protocol):
    def __call__(
        self,
        payload: Any,
        *,
        selected_path: str,
        on_stream_delta: Callable[[str], None] | None = None,
        planner_shell_fallback: bool = False,
        planner_shell_fallback_reason: str | None = None,
        planner_result: PlannerResult | None = None,
    ) -> Any: ...


class PlannerShellRunResult(TypedDict):
    response: Any
    observation: dict[str, Any]


def _serialize_planner_result(result: PlannerResult) -> dict[str, Any]:
    return {
        "planner_used": result.planner_used,
        "planner_source": result.planner_source,
        "planner_fallback": result.planner_fallback,
        "planner_fallback_reason": result.planner_fallback_reason,
        "planner_confidence": result.planner_confidence,
        "is_new_topic": result.is_new_topic,
        "should_clear_pending_clarify": result.should_clear_pending_clarify,
        "relation_to_previous": result.relation_to_previous,
        "standalone_query": result.standalone_query,
        "primary_capability": result.primary_capability,
        "strictness": result.strictness,
        "action_plan": list(result.action_plan or []),
    }


def _load_request_context(state: PlannerShellState) -> PlannerShellState:
    next_state = dict(state)
    next_state.setdefault("execution_trace", [])
    next_state.setdefault("short_circuit", {"triggered": False, "reason": None, "step": None})
    next_state.setdefault("truncated", False)
    next_state.setdefault("planner_shell_fallback", False)
    next_state.setdefault("planner_shell_fallback_reason", None)
    next_state.setdefault("planner_shell_passthrough", False)
    return next_state


def _plan_chat_request(state: PlannerShellState) -> PlannerShellState:
    next_state = dict(state)
    request = dict(next_state.get("request") or {})
    query = str(request.get("query") or "").strip()
    planner_result = build_rule_based_plan(
        user_input=query,
        standalone_query=query,
        dialog_state="answering",
        history_topic_anchors=[],
        pending_clarify=None,
    )
    next_state["planner"] = _serialize_planner_result(planner_result)
    return next_state


def _build_route_state(state: PlannerShellState, route: PlannerRoute, *, passthrough: bool) -> PlannerShellState:
    next_state = dict(state)
    planner = dict(next_state.get("planner") or {})
    next_state["route"] = route
    next_state["selected_path"] = route if not passthrough else f"{route}_passthrough"
    next_state["planner_shell_passthrough"] = passthrough
    next_state["planner_shell_backend"] = "langgraph" if HAS_LANGGRAPH else "fallback"
    next_state["execution_trace"] = list(next_state.get("execution_trace") or [])
    next_state["execution_trace"].append(
        {
            "step": "planner_shell_route",
            "state": "selected",
            "selected_path": next_state["selected_path"],
            "primary_capability": planner.get("primary_capability"),
            "strictness": planner.get("strictness"),
            "passthrough": passthrough,
        }
    )
    return next_state


def _route_capability(state: PlannerShellState) -> PlannerShellState:
    planner = dict(state.get("planner") or {})
    capability = str(planner.get("primary_capability") or "fact_qa").strip()
    if capability == "fact_qa":
        return _build_route_state(state, "fact_qa", passthrough=False)
    if capability == "catalog_lookup":
        return _build_route_state(state, "catalog", passthrough=True)
    if capability == "cross_doc_summary":
        return _build_route_state(state, "summary", passthrough=True)
    if capability == "control":
        return _build_route_state(state, "control", passthrough=True)
    fallback = dict(state)
    fallback["planner_shell_fallback"] = True
    fallback["planner_shell_fallback_reason"] = f"unsupported_capability:{capability or 'unknown'}"
    return _build_route_state(fallback, "legacy_fallback", passthrough=True)


def _run_route(
    state: PlannerShellState,
    *,
    executor: RouteExecutor,
    on_stream_delta: Callable[[str], None] | None,
) -> PlannerShellState:
    next_state = dict(state)
    request = next_state.get("request")
    payload = next_state.get("payload")
    if request is None or payload is None:
        raise RuntimeError("planner shell request missing")
    planner_data = dict(next_state.get("planner") or {})
    planner_result = PlannerResult(
        planner_used=bool(planner_data.get("planner_used", False)),
        planner_source=str(planner_data.get("planner_source") or "fallback"),
        planner_fallback=bool(planner_data.get("planner_fallback", False)),
        planner_fallback_reason=planner_data.get("planner_fallback_reason"),
        planner_confidence=float(planner_data.get("planner_confidence", 0.0)),
        is_new_topic=bool(planner_data.get("is_new_topic", False)),
        should_clear_pending_clarify=bool(planner_data.get("should_clear_pending_clarify", False)),
        relation_to_previous=str(planner_data.get("relation_to_previous") or "same_topic_or_no_pending"),
        standalone_query=str(planner_data.get("standalone_query") or request.get("query") or ""),
        primary_capability=str(planner_data.get("primary_capability") or "fact_qa"),
        strictness=str(planner_data.get("strictness") or "strict_fact"),
        action_plan=list(planner_data.get("action_plan") or []),
    )
    next_state["response"] = executor(
        payload,
        selected_path=str(next_state.get("selected_path") or "legacy_fallback"),
        on_stream_delta=on_stream_delta,
        planner_shell_fallback=bool(next_state.get("planner_shell_fallback", False)),
        planner_shell_fallback_reason=(
            str(next_state.get("planner_shell_fallback_reason"))
            if next_state.get("planner_shell_fallback_reason") is not None
            else None
        ),
        planner_result=planner_result,
    )
    return next_state


def _route_next(state: PlannerShellState) -> str:
    route = str(state.get("route") or "legacy_fallback")
    if route == "fact_qa":
        return "run_fact_qa_path"
    if route in {"catalog", "summary", "control"}:
        return "run_compat_path"
    return "fallback_to_legacy_qa"


def _build_graph(
    *,
    fact_qa_executor: RouteExecutor,
    compat_executor: RouteExecutor,
    legacy_executor: RouteExecutor,
    on_stream_delta: Callable[[str], None] | None,
):
    def _run_fact_qa(state: PlannerShellState) -> PlannerShellState:
        return _run_route(state, executor=fact_qa_executor, on_stream_delta=on_stream_delta)

    def _run_compat(state: PlannerShellState) -> PlannerShellState:
        return _run_route(state, executor=compat_executor, on_stream_delta=on_stream_delta)

    def _run_legacy(state: PlannerShellState) -> PlannerShellState:
        fallback_state = dict(state)
        fallback_state.setdefault("planner_shell_fallback", True)
        fallback_state.setdefault("planner_shell_fallback_reason", "route_fallback")
        fallback_state["selected_path"] = "legacy_fallback"
        fallback_state["route"] = "legacy_fallback"
        fallback_state["planner_shell_passthrough"] = True
        return _run_route(fallback_state, executor=legacy_executor, on_stream_delta=on_stream_delta)

    if not HAS_LANGGRAPH or StateGraph is None:
        return None, {
            "load_request_context": _load_request_context,
            "plan_chat_request": _plan_chat_request,
            "route_capability": _route_capability,
            "run_fact_qa_path": _run_fact_qa,
            "run_compat_path": _run_compat,
            "fallback_to_legacy_qa": _run_legacy,
        }

    graph = StateGraph(PlannerShellState)
    graph.add_node("load_request_context", _load_request_context)
    graph.add_node("plan_chat_request", _plan_chat_request)
    graph.add_node("route_capability", _route_capability)
    graph.add_node("run_fact_qa_path", _run_fact_qa)
    graph.add_node("run_compat_path", _run_compat)
    graph.add_node("fallback_to_legacy_qa", _run_legacy)
    graph.set_entry_point("load_request_context")
    graph.add_edge("load_request_context", "plan_chat_request")
    graph.add_edge("plan_chat_request", "route_capability")
    graph.add_conditional_edges(
        "route_capability",
        _route_next,
        {
            "run_fact_qa_path": "run_fact_qa_path",
            "run_compat_path": "run_compat_path",
            "fallback_to_legacy_qa": "fallback_to_legacy_qa",
        },
    )
    graph.add_edge("run_fact_qa_path", END)
    graph.add_edge("run_compat_path", END)
    graph.add_edge("fallback_to_legacy_qa", END)
    return graph.compile(), None


def _run_without_langgraph(
    state: PlannerShellState,
    nodes: dict[str, Callable[[PlannerShellState], PlannerShellState]],
) -> PlannerShellState:
    current = nodes["load_request_context"](state)
    current = nodes["plan_chat_request"](current)
    current = nodes["route_capability"](current)
    route_next = _route_next(current)
    return nodes[route_next](current)


def run_planner_shell(
    payload: Any,
    *,
    fact_qa_executor: RouteExecutor,
    compat_executor: RouteExecutor,
    legacy_executor: RouteExecutor,
    on_stream_delta: Callable[[str], None] | None = None,
) -> PlannerShellRunResult:
    initial_state: PlannerShellState = {
        "payload": payload,
        "request": {
            "sessionId": str(getattr(payload, "sessionId")),
            "mode": str(getattr(payload, "mode")),
            "query": str(getattr(payload, "query")),
            "traceId": getattr(payload, "traceId", None),
            "history": [asdict(item) if hasattr(item, "__dataclass_fields__") else item.model_dump() for item in getattr(payload, "history", [])],
        }
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
            reason="planner_shell_exception",
        )
        response = legacy_executor(
            payload,
            selected_path="legacy_fallback",
            on_stream_delta=on_stream_delta,
            planner_shell_fallback=True,
            planner_shell_fallback_reason=str(exc),
            planner_result=planner_result,
        )
        final_state = {
            "planner": _serialize_planner_result(planner_result),
            "response": response,
            "selected_path": "legacy_fallback",
            "execution_trace": [
                {
                    "step": "planner_shell_route",
                    "state": "selected",
                    "selected_path": "legacy_fallback",
                    "primary_capability": planner_result.primary_capability,
                    "strictness": planner_result.strictness,
                    "passthrough": True,
                }
            ],
            "short_circuit": {"triggered": False, "reason": None, "step": None},
            "truncated": False,
            "planner_shell_fallback": True,
            "planner_shell_fallback_reason": str(exc),
            "planner_shell_backend": "langgraph" if HAS_LANGGRAPH else "fallback",
            "planner_shell_passthrough": True,
        }

    observation = {
        "planner_shell_used": True,
        "planner_shell_backend": final_state.get("planner_shell_backend", "fallback"),
        "planner_shell_fallback": bool(final_state.get("planner_shell_fallback", False)),
        "planner_shell_fallback_reason": final_state.get("planner_shell_fallback_reason"),
        "planner_shell_passthrough": bool(final_state.get("planner_shell_passthrough", False)),
        "selected_path": str(final_state.get("selected_path") or "legacy_fallback"),
        "planner": dict(final_state.get("planner") or {}),
        "execution_trace": list(final_state.get("execution_trace") or []),
        "short_circuit": dict(final_state.get("short_circuit") or {"triggered": False, "reason": None, "step": None}),
        "truncated": bool(final_state.get("truncated", False)),
    }
    return {"response": final_state["response"], "observation": observation}
