from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolKind = Literal["tool", "skill"]
KnowledgeScope = Literal["local", "web", "hybrid"]
StreamingMode = Literal["none", "final_only", "text_stream"]
EvidencePolicy = Literal["citation_required", "citation_optional", "citation_forbidden"]
ToolFailureType = Literal[
    "invalid_input",
    "precondition_failed",
    "empty_result",
    "insufficient_evidence",
    "timeout",
    "execution_error",
    "unsupported_tool",
    "missing_dependencies",
]
ToolExecutionStatus = Literal[
    "planned",
    "validated",
    "dispatched",
    "succeeded",
    "failed",
    "blocked",
    "skipped",
    "clarify_required",
]
SourceProvenance = Literal["citation", "metadata", "explanatory"]

TOOL_FAILURE_TYPES: tuple[ToolFailureType, ...] = (
    "invalid_input",
    "precondition_failed",
    "empty_result",
    "insufficient_evidence",
    "timeout",
    "execution_error",
    "unsupported_tool",
    "missing_dependencies",
)
STREAMING_MODES: tuple[StreamingMode, ...] = ("none", "final_only", "text_stream")
EVIDENCE_POLICIES: tuple[EvidencePolicy, ...] = (
    "citation_required",
    "citation_optional",
    "citation_forbidden",
)


@dataclass(frozen=True)
class ToolRegistryEntry:
    tool_name: str
    capability_family: str
    version: str
    planner_visible: bool
    kind: ToolKind
    route: str
    passthrough: bool
    streaming_mode: StreamingMode
    evidence_policy: EvidencePolicy
    input_schema: dict[str, Any] = field(default_factory=dict)
    result_schema: dict[str, Any] = field(default_factory=dict)
    failure_types: tuple[ToolFailureType, ...] = field(default_factory=tuple)
    capability_tags: tuple[str, ...] = field(default_factory=tuple)
    knowledge_scope: KnowledgeScope = "local"
    supports_research_mode: bool = False
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    produces: tuple[str, ...] = field(default_factory=tuple)
    depends_on: tuple[str, ...] = field(default_factory=tuple)


def serialize_tool_registry_entry(entry: ToolRegistryEntry) -> dict[str, Any]:
    return {
        "name": entry.tool_name,
        "tool_name": entry.tool_name,
        "capability_family": entry.capability_family,
        "version": entry.version,
        "planner_visible": entry.planner_visible,
        "kind": entry.kind,
        "route": entry.route,
        "passthrough": entry.passthrough,
        "capability_tags": list(entry.capability_tags),
        "knowledge_scope": entry.knowledge_scope,
        "supports_research_mode": entry.supports_research_mode,
        "prerequisites": list(entry.prerequisites),
        "produces": list(entry.produces),
        "depends_on": list(entry.depends_on),
        "input_schema": dict(entry.input_schema),
        "result_schema": dict(entry.result_schema),
        "failure_types": list(entry.failure_types),
        "streaming_mode": entry.streaming_mode,
        "evidence_policy": entry.evidence_policy,
    }


def validate_tool_registry_entry(entry: ToolRegistryEntry) -> list[str]:
    errors: list[str] = []
    if not entry.tool_name.strip():
        errors.append("tool_name must not be empty")
    if not entry.capability_family.strip():
        errors.append(f"{entry.tool_name}: capability_family must not be empty")
    if entry.streaming_mode not in STREAMING_MODES:
        errors.append(f"{entry.tool_name}: invalid streaming_mode={entry.streaming_mode}")
    if entry.evidence_policy not in EVIDENCE_POLICIES:
        errors.append(f"{entry.tool_name}: invalid evidence_policy={entry.evidence_policy}")
    unknown_failure_types = [item for item in entry.failure_types if item not in TOOL_FAILURE_TYPES]
    if unknown_failure_types:
        errors.append(f"{entry.tool_name}: invalid failure_types={','.join(unknown_failure_types)}")
    return errors


def validate_tool_call_envelope(tool_call: dict[str, Any], registry: dict[str, ToolRegistryEntry]) -> list[str]:
    errors: list[str] = []
    tool_name = str(tool_call.get("tool_name") or "").strip()
    if not tool_name:
        return ["tool_name must not be empty"]
    entry = registry.get(tool_name)
    if entry is None:
        return [f"unregistered tool: {tool_name}"]
    arguments = tool_call.get("arguments")
    if not isinstance(arguments, dict):
        errors.append(f"{tool_name}: arguments must be an object")
    depends_on_artifacts = tool_call.get("depends_on_artifacts")
    if depends_on_artifacts is not None and not isinstance(depends_on_artifacts, list):
        errors.append(f"{tool_name}: depends_on_artifacts must be a list")
    execution_mode = str(tool_call.get("execution_mode") or "").strip()
    if execution_mode and execution_mode != entry.streaming_mode:
        errors.append(f"{tool_name}: execution_mode does not match registry streaming_mode")
    return errors


def build_tool_failure(
    failure_type: ToolFailureType,
    *,
    message: str,
    retryable: bool = False,
    user_safe_message: str | None = None,
    failed_dependency: str | None = None,
    stop_plan: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "failure_type": failure_type,
        "code": failure_type,
        "message": message,
        "retryable": retryable,
        "user_safe_message": user_safe_message or message,
        "failed_dependency": failed_dependency,
        "stop_plan": stop_plan,
        "details": dict(details or {}),
    }


def build_tool_call_envelope(
    entry: ToolRegistryEntry,
    *,
    call_id: str,
    query: str,
    arguments: dict[str, Any] | None = None,
    depends_on_artifacts: list[str] | None = None,
    trace_context: dict[str, Any] | None = None,
    execution_mode: StreamingMode | None = None,
    status: ToolExecutionStatus = "planned",
) -> dict[str, Any]:
    normalized_arguments = dict(arguments or {})
    if "query" not in normalized_arguments:
        normalized_arguments["query"] = query
    return {
        "id": call_id,
        "call_id": call_id,
        "tool_name": entry.tool_name,
        "query": query,
        "arguments": normalized_arguments,
        "depends_on_artifacts": list(depends_on_artifacts or []),
        "depends_on": list(depends_on_artifacts or []),
        "trace_context": dict(trace_context or {}),
        "execution_mode": execution_mode or entry.streaming_mode,
        "streaming_mode": entry.streaming_mode,
        "evidence_policy": entry.evidence_policy,
        "capability_family": entry.capability_family,
        "produces": list(entry.produces),
        "params": dict(normalized_arguments.get("params") or {}),
        "route": entry.route,
        "passthrough": entry.passthrough,
        "status": status,
        "tool_status": status,
    }


def build_tool_result_envelope(
    tool_call: dict[str, Any],
    *,
    status: ToolExecutionStatus,
    output: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    observability: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_output = dict(output or {})
    normalized_artifacts = [dict(item) for item in list(artifacts or []) if isinstance(item, dict)]
    normalized_sources = [dict(item) for item in list(sources or []) if isinstance(item, dict)]
    normalized_warnings = [str(item) for item in list(warnings or []) if str(item).strip()]
    normalized_observability = dict(observability or {})
    normalized_failure = dict(failure or {})
    return {
        "tool_call_id": tool_call.get("call_id") or tool_call.get("id"),
        "call_id": tool_call.get("call_id") or tool_call.get("id"),
        "tool_name": tool_call.get("tool_name"),
        "status": status,
        "tool_status": status,
        "output": normalized_output,
        "artifacts": normalized_artifacts,
        "sources": normalized_sources,
        "warnings": normalized_warnings,
        "observability": normalized_observability,
        "failure": normalized_failure,
        # Backward-compatible aliases.
        "result": normalized_output,
        "error": normalized_failure,
        "metadata": normalized_observability,
        "produces": list(tool_call.get("produces") or []),
    }
