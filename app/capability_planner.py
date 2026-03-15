from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from app.library import load_papers

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")
STOPWORDS = {
    "列出",
    "列一下",
    "列",
    "有哪些",
    "哪些",
    "论文",
    "篇",
    "给我",
    "帮我",
    "一下",
    "一下子",
    "并",
    "然后",
    "再",
    "对比",
    "比较",
    "总结",
    "概括",
    "表格",
    "展示",
    "一下它们",
    "这些",
    "那几篇",
    "papers",
    "paper",
    "list",
    "show",
    "compare",
    "summary",
    "论文",
    "paper",
    "papers",
    "这篇",
    "那个",
    "这个",
}
CATALOG_TERMS = ("哪些论文", "列出", "列一下", "上传", "知识库", "库中", "导入")
SUMMARY_TERMS = ("总结", "概览", "差异", "对比", "比较", "归纳", "表格")
PAPER_ASSISTANT_TERMS = (
    "研究建议",
    "下一步",
    "创新点",
    "启发",
    "灵感",
    "研究方向",
    "未来工作",
    "局限",
)
STRICT_FACT_TERMS = (
    "准确率",
    "召回率",
    "f1",
    "precision",
    "recall",
    "具体数值",
    "多少",
    "作者",
    "年份",
    "会议",
    "benchmark",
    "数据集",
    "实验设置",
    "实验条件",
)
READY_STATUSES = {"ready", "completed", "active"}


@dataclass
class PlannerStep:
    action: str
    query: str
    produces: str | None = None
    depends_on: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerResult:
    planner_used: bool
    planner_source: str
    planner_fallback: bool
    planner_fallback_reason: str | None
    planner_confidence: float
    is_new_topic: bool
    should_clear_pending_clarify: bool
    relation_to_previous: str
    standalone_query: str
    primary_capability: str
    strictness: str
    action_plan: list[dict[str, Any]]


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split())


def _tokenize(text: str) -> set[str]:
    return {tok.lower() for tok in TOKEN_RE.findall(text or "") if tok.strip()}


def _topic_overlap(current: str, anchors: list[str]) -> bool:
    current_tokens = {tok for tok in _tokenize(current) if tok not in STOPWORDS}
    history_tokens = {str(item).strip().lower() for item in anchors if str(item).strip() and str(item).strip().lower() not in STOPWORDS}
    if not current_tokens or not history_tokens:
        return False
    if current_tokens.intersection(history_tokens):
        return True
    for cur in current_tokens:
        for hist in history_tokens:
            if len(cur) >= 4 and len(hist) >= 4 and (cur in hist or hist in cur):
                return True
    return False


def detect_new_topic(
    *,
    user_input: str,
    dialog_state: str,
    history_topic_anchors: list[str],
    pending_clarify: dict[str, Any] | None,
) -> tuple[bool, bool, str]:
    normalized = _normalize_spaces(user_input)
    has_pending = isinstance(pending_clarify, dict) and bool(
        _normalize_spaces(str(pending_clarify.get("original_question", ""))) or _normalize_spaces(str(pending_clarify.get("clarify_question", "")))
    )
    if (dialog_state not in {"need_clarify", "waiting_followup"} and not has_pending) or not normalized:
        return False, False, "same_topic_or_no_pending"
    if _topic_overlap(normalized, history_topic_anchors):
        return False, False, "followup_overlap"
    original_question = ""
    if isinstance(pending_clarify, dict):
        original_question = _normalize_spaces(str(pending_clarify.get("original_question", "")))
    if original_question and _topic_overlap(normalized, [original_question]):
        return False, False, "followup_pending_overlap"
    if any(term in normalized.lower() for term in ("库中", "知识库", "有哪些论文", "列出")):
        return True, True, "new_topic_catalog_request"
    return False, False, "pending_followup_default"


def _extract_limit(text: str, default: int) -> int:
    match = re.search(r"(\d+)\s*篇", text)
    if match:
        return max(1, int(match.group(1)))
    return max(1, default)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in terms)


def _strict_fact_signal(text: str) -> bool:
    return _contains_any(text, STRICT_FACT_TERMS)


def build_rule_based_plan(
    *,
    user_input: str,
    standalone_query: str,
    dialog_state: str,
    history_topic_anchors: list[str],
    pending_clarify: dict[str, Any] | None,
    max_steps: int = 3,
    catalog_limit: int = 20,
) -> PlannerResult:
    is_new_topic, should_clear, relation = detect_new_topic(
        user_input=user_input,
        dialog_state=dialog_state,
        history_topic_anchors=history_topic_anchors,
        pending_clarify=pending_clarify,
    )
    normalized_query = _normalize_spaces(standalone_query or user_input)
    wants_catalog = _contains_any(normalized_query, CATALOG_TERMS)
    wants_summary = _contains_any(normalized_query, SUMMARY_TERMS)
    wants_paper_assistant = _contains_any(normalized_query, PAPER_ASSISTANT_TERMS)
    strict_fact = _strict_fact_signal(normalized_query)
    limit = _extract_limit(normalized_query, catalog_limit)
    steps: list[PlannerStep] = []
    primary_capability = "fact_qa"
    strictness = "strict_fact"
    confidence = 0.7
    if wants_catalog:
        catalog_step = PlannerStep(
            action="catalog_lookup",
            query=normalized_query,
            produces="paper_set",
            params={"limit": limit},
        )
        steps.append(catalog_step)
        confidence = 0.82
        if wants_paper_assistant and not strict_fact:
            primary_capability = "paper_assistant"
            strictness = "summary"
            steps.append(
                PlannerStep(
                    action="paper_assistant",
                    query=normalized_query,
                    depends_on=["paper_set"],
                    params={"style": "research_assistant"},
                )
            )
            confidence = 0.91
        elif wants_summary and not strict_fact:
            primary_capability = "cross_doc_summary"
            strictness = "summary"
            steps.append(
                PlannerStep(
                    action="cross_doc_summary",
                    query=normalized_query,
                    depends_on=["paper_set"],
                    params={"format": ("table" if "表格" in normalized_query or "table" in normalized_query.lower() else "bullet")},
                )
            )
            confidence = 0.9
        elif strict_fact:
            primary_capability = "fact_qa"
            strictness = "strict_fact"
            steps.append(PlannerStep(action="fact_qa", query=normalized_query, depends_on=["paper_set"]))
            confidence = 0.9
        else:
            primary_capability = "catalog_lookup"
            strictness = "catalog"
    elif wants_paper_assistant and not strict_fact:
        primary_capability = "paper_assistant"
        strictness = "summary"
        steps.append(
            PlannerStep(
                action="paper_assistant",
                query=normalized_query,
                params={"style": "research_assistant"},
            )
        )
        confidence = 0.8
    elif wants_summary and not strict_fact:
        primary_capability = "cross_doc_summary"
        strictness = "summary"
        steps.append(PlannerStep(action="cross_doc_summary", query=normalized_query))
        confidence = 0.78
    elif _contains_any(normalized_query, ("表格", "markdown", "json", "继续")) and not wants_catalog:
        primary_capability = "control"
        strictness = "summary" if wants_summary else "strict_fact"
        steps.append(PlannerStep(action="control", query=normalized_query))
        confidence = 0.72
    else:
        steps.append(PlannerStep(action="fact_qa", query=normalized_query))

    if strict_fact and steps and steps[-1].action == "cross_doc_summary":
        steps[-1] = PlannerStep(action="fact_qa", query=normalized_query, depends_on=list(steps[-1].depends_on))
        primary_capability = "fact_qa"
        strictness = "strict_fact"
        confidence = max(confidence, 0.88)

    limited_steps = steps[: max(1, int(max_steps))]
    return PlannerResult(
        planner_used=True,
        planner_source="rule",
        planner_fallback=False,
        planner_fallback_reason=None,
        planner_confidence=round(confidence, 4),
        is_new_topic=is_new_topic,
        should_clear_pending_clarify=should_clear,
        relation_to_previous=relation,
        standalone_query=normalized_query,
        primary_capability=primary_capability,
        strictness=strictness,
        action_plan=[asdict(step) for step in limited_steps],
    )


def build_planner_fallback(*, user_input: str, standalone_query: str, reason: str) -> PlannerResult:
    query = _normalize_spaces(standalone_query or user_input)
    return PlannerResult(
        planner_used=False,
        planner_source="fallback",
        planner_fallback=True,
        planner_fallback_reason=reason,
        planner_confidence=0.0,
        is_new_topic=False,
        should_clear_pending_clarify=False,
        relation_to_previous="planner_fallback",
        standalone_query=query,
        primary_capability="fact_qa",
        strictness="strict_fact",
        action_plan=[asdict(PlannerStep(action="fact_qa", query=query))],
    )


def _parse_imported_at(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_catalog_keywords(query: str) -> list[str]:
    values: list[str] = []
    for token in TOKEN_RE.findall(query or ""):
        normalized = token.strip().lower()
        if not normalized or normalized in STOPWORDS or normalized.isdigit():
            continue
        if len(normalized) <= 1:
            continue
        if normalized not in values:
            values.append(normalized)
    return values[:8]


def _filter_recent(papers: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    lowered = (query or "").lower()
    now = datetime.now(timezone.utc)
    if "昨天" in query or "yesterday" in lowered:
        start = (now - timedelta(days=1)).date()
        return [row for row in papers if (_parse_imported_at(str(row.get("imported_at", ""))) or now).date() == start]
    if "今天" in query or "today" in lowered:
        start = now.date()
        return [row for row in papers if (_parse_imported_at(str(row.get("imported_at", ""))) or now).date() == start]
    return papers


def execute_catalog_lookup(
    *,
    query: str,
    papers_path: str | None = None,
    max_papers: int = 20,
) -> dict[str, Any]:
    all_papers = load_papers() if papers_path is None else load_papers(path=papers_path)  # type: ignore[arg-type]
    filtered = _filter_recent(list(all_papers), query)
    keywords = _extract_catalog_keywords(query)
    if keywords:
        matched = []
        for row in filtered:
            haystack = " ".join(
                [
                    str(row.get("title", "")),
                    str(row.get("paper_id", "")),
                    str(row.get("source_type", "")),
                    str(row.get("status", "")),
                ]
            ).lower()
            if all(keyword in haystack for keyword in keywords):
                matched.append(row)
        if matched:
            filtered = matched
    filtered.sort(
        key=lambda row: (
            0 if str(row.get("status", "")).strip().lower() in READY_STATUSES else 1,
            str(row.get("imported_at", "")),
            str(row.get("title", "")).lower(),
        ),
        reverse=True,
    )
    matched_count = len(filtered)
    selected_count = min(matched_count, max(1, int(max_papers)))
    selected = filtered[:selected_count]
    paper_set = [
        {
            "paper_id": str(row.get("paper_id", "")).strip(),
            "title": str(row.get("title", "")).strip(),
            "source_type": str(row.get("source_type", "")).strip(),
            "imported_at": str(row.get("imported_at", "")).strip(),
            "status": str(row.get("status", "")).strip(),
        }
        for row in selected
        if str(row.get("paper_id", "")).strip()
    ]
    short_circuit = matched_count == 0
    short_circuit_reason = "catalog_lookup_empty" if short_circuit else None
    return {
        "state": "short_circuit" if short_circuit else "ready",
        "query": query,
        "keywords": keywords,
        "matched_count": matched_count,
        "selected_count": len(paper_set),
        "truncated": matched_count > len(paper_set),
        "paper_set": paper_set,
        "short_circuit": short_circuit,
        "short_circuit_reason": short_circuit_reason,
        "produces": {"paper_set": paper_set},
    }


def compose_catalog_answer(catalog_result: dict[str, Any]) -> str:
    paper_set = list(catalog_result.get("paper_set") or [])
    if not paper_set:
        return "未找到符合条件的论文，因此未继续执行后续步骤。"
    lines = ["基于目录元数据，匹配到这些论文："]
    for idx, row in enumerate(paper_set, start=1):
        title = str(row.get("title", "")).strip() or str(row.get("paper_id", "")).strip()
        imported_at = str(row.get("imported_at", "")).strip() or "未知导入时间"
        status = str(row.get("status", "")).strip() or "unknown"
        lines.append(f"{idx}. {title} | paper_id={row.get('paper_id', '')} | imported_at={imported_at} | status={status}")
    if bool(catalog_result.get("truncated")):
        lines.append(
            f"结果已截断：matched_count={catalog_result.get('matched_count', 0)}, "
            f"selected_count={catalog_result.get('selected_count', 0)}。"
        )
    return "\n".join(lines)
