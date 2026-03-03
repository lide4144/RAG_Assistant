from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Callable

try:
    import streamlit as st

    _STREAMLIT_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - fallback for test envs without streamlit
    _STREAMLIT_AVAILABLE = False

    class _StreamlitStub:
        def __getattr__(self, name: str) -> Any:
            raise RuntimeError("streamlit is required to run app/ui.py")

    st = _StreamlitStub()

# Ensure `streamlit run app/ui.py` can import the project package.
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.config import load_and_validate_config
from app.ideas import IDEA_STATUS_FLOW, create_draft, list_cards, save_card, update_card_status
from app.library import load_papers, load_topics, run_import_workflow, save_topics
from app.paths import CONFIGS_DIR, DATA_DIR, RUNS_DIR
from app.qa import run_qa
from app.session_state import clear_session

CITATION_PATTERN = re.compile(r"\[(\d+)\]")

DEFAULT_RUNS_DIR = RUNS_DIR
DEFAULT_CHUNKS = str(DATA_DIR / "processed" / "chunks_clean.jsonl")
DEFAULT_BM25 = str(DATA_DIR / "indexes" / "bm25_index.json")
DEFAULT_VEC = str(DATA_DIR / "indexes" / "vec_index.json")
DEFAULT_EMBED = str(DATA_DIR / "indexes" / "vec_index_embed.json")
DEFAULT_CONFIG = str(CONFIGS_DIR / "default.yaml")
DEFAULT_SESSION_STORE = str(DATA_DIR / "session_store.json")
DEFAULT_PAPER_SUMMARY = DATA_DIR / "processed" / "paper_summary.json"


def _na(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str) and not value.strip():
        return "N/A"
    return str(value)


def _pick(report: dict[str, Any], trace: dict[str, Any], key: str) -> Any:
    if key in report:
        return report.get(key)
    return trace.get(key)


def _assistant_mode_inspector_lines(report: dict[str, Any], trace: dict[str, Any]) -> list[str]:
    return [
        f"- assistant_mode_used: `{_na(report.get('assistant_mode_used') or trace.get('assistant_mode_used'))}`",
        f"- clarify_count: `{_na(_pick(report, trace, 'clarify_count'))}`",
        f"- clarify_limit_hit: `{_na(_pick(report, trace, 'clarify_limit_hit'))}`",
        f"- forced_partial_answer: `{_na(_pick(report, trace, 'forced_partial_answer'))}`",
        f"- gate_trigger_reason: `{_na(report.get('gate_trigger_reason') or trace.get('gate_trigger_reason'))}`",
    ]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_paper_summary_lookup(path: Path = DEFAULT_PAPER_SUMMARY) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        if not paper_id:
            continue
        out[paper_id] = row
    return out


def _build_paper_navigation(report: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = _load_paper_summary_lookup()
    evidence_grouped = report.get("evidence_grouped") or []
    if not isinstance(evidence_grouped, list):
        return []
    nav_rows: list[dict[str, Any]] = []
    for group in evidence_grouped[:4]:
        if not isinstance(group, dict):
            continue
        paper_id = str(group.get("paper_id", "")).strip()
        if not paper_id:
            continue
        summary_row = summaries.get(paper_id, {})
        title = str(group.get("paper_title") or summary_row.get("title") or paper_id).strip()
        one_paragraph = str(summary_row.get("one_paragraph_summary", "")).strip()
        key_points = [str(x).strip() for x in (summary_row.get("key_points") or []) if str(x).strip()][:3]
        nav_rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "one_paragraph_summary": one_paragraph,
                "key_points": key_points,
            }
        )
    return nav_rows


def _extract_citation_numbers(answer: str) -> list[int]:
    seen: set[int] = set()
    numbers: list[int] = []
    for match in CITATION_PATTERN.findall(answer or ""):
        idx = int(match)
        if idx not in seen:
            seen.add(idx)
            numbers.append(idx)
    return numbers


def _build_citation_slots(answer: str, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citation_numbers = _extract_citation_numbers(answer)
    if not citation_numbers and citations:
        citation_numbers = list(range(1, len(citations) + 1))
    total = len(citations)
    return [
        {
            "citation_idx": num,
            "valid": 1 <= num <= total,
        }
        for num in citation_numbers
    ]


def _source_badge_html(source: str) -> str:
    if source == "graph_expand":
        return "<span style='background:#f97316;color:white;padding:1px 6px;border-radius:10px;'>graph_expand</span>"
    return f"<span style='background:#334155;color:white;padding:1px 6px;border-radius:10px;'>{source}</span>"


def _decision_alert_kind(decision: str) -> str | None:
    if decision == "refuse":
        return "error"
    if decision == "clarify":
        return "warning"
    return None


def _apply_session_reset_history_guard(
    report: dict[str, Any],
    *,
    expect_zero_history_turn: bool,
) -> tuple[dict[str, Any], str | None]:
    if not expect_zero_history_turn:
        return report, None
    hist_turns = int(report.get("history_used_turns") or 0)
    if hist_turns <= 0:
        return report, None
    warn = (
        "会话清空后首次提问的 history_used_turns 非 0，"
        f"当前值={hist_turns}，请检查会话隔离。"
    )
    output_warnings = list(report.get("output_warnings") or [])
    output_warnings.append("session_reset_history_leak_suspected")
    report["output_warnings"] = output_warnings
    return report, warn


def _build_args(
    question: str,
    session_id: str,
    *,
    topic_paper_ids: list[str] | None = None,
    topic_name: str = "",
    run_id: str = "",
    run_dir: str = "",
    on_stream_delta: Callable[[str], None] | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        q=question,
        mode="hybrid",
        chunks=DEFAULT_CHUNKS,
        bm25_index=DEFAULT_BM25,
        vec_index=DEFAULT_VEC,
        embed_index=DEFAULT_EMBED,
        config=DEFAULT_CONFIG,
        top_k=None,
        top_evidence=5,
        session_id=session_id,
        session_store=DEFAULT_SESSION_STORE,
        clear_session=False,
        topic_paper_ids=",".join(topic_paper_ids or []),
        topic_name=topic_name,
        run_id=run_id,
        run_dir=run_dir,
        on_stream_delta=on_stream_delta,
    )


def _run_turn(
    question: str,
    session_id: str,
    *,
    topic_paper_ids: list[str] | None = None,
    topic_name: str = "",
    on_stream_delta: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str, Path]:
    run_id = f"ui_{session_id}_{uuid.uuid4().hex[:10]}"
    run_dir = DEFAULT_RUNS_DIR / run_id
    args = _build_args(
        question,
        session_id,
        topic_paper_ids=topic_paper_ids,
        topic_name=topic_name,
        run_id=run_id,
        run_dir=str(run_dir),
        on_stream_delta=on_stream_delta,
    )

    out_buf = StringIO()
    err_buf = StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = run_qa(args)

    if rc != 0:
        raise RuntimeError(f"run_qa returned non-zero code: {rc}")

    report = _read_json(run_dir / "qa_report.json")
    trace = _read_json(run_dir / "run_trace.json")
    if not report:
        raise RuntimeError(f"QA report missing at {run_dir / 'qa_report.json'}")
    logs = (out_buf.getvalue() + "\n" + err_buf.getvalue()).strip()
    return report, trace, logs, run_dir


def _compact_turn_report(report: dict[str, Any]) -> dict[str, Any]:
    keep_keys = {
        "question",
        "standalone_query",
        "answer",
        "answer_citations",
        "evidence_grouped",
        "output_warnings",
        "decision",
        "decision_reason",
        "assistant_mode_used",
        "clarify_count",
        "clarify_limit_hit",
        "forced_partial_answer",
        "gate_trigger_reason",
        "topic_name",
        "history_used_turns",
        "paper_navigation",
    }
    return {k: report.get(k) for k in keep_keys if k in report}


def _compact_turn_trace(trace: dict[str, Any]) -> dict[str, Any]:
    keep_keys = {
        "rewrite_query",
        "calibrated_query",
        "intent_router_enabled",
        "intent_type",
        "anchor_query",
        "topic_query_source",
        "output_warnings",
        "session_reset",
        "ui_logs",
    }
    return {k: trace.get(k) for k in keep_keys if k in trace}


def _load_turn_data(turn: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    report = dict(turn.get("report") or {})
    trace = dict(turn.get("trace") or {})
    report_path = str(turn.get("report_path") or "").strip()
    trace_path = str(turn.get("trace_path") or "").strip()
    if report_path and ("evidence_grouped" not in report or "answer_citations" not in report):
        report.update(_read_json(Path(report_path)))
    if trace_path and "rewrite_query" not in trace:
        trace.update(_read_json(Path(trace_path)))
    return report, trace


def _find_evidence_by_chunk_id(evidence_grouped: list[dict[str, Any]], chunk_id: str) -> dict[str, Any] | None:
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            if str(item.get("chunk_id")) == str(chunk_id):
                payload = dict(item)
                payload["paper_title"] = group.get("paper_title")
                payload["paper_id"] = group.get("paper_id")
                return payload
    return None


def _reset_chat_state() -> None:
    st.session_state.chat_messages = []
    st.session_state.turn_traces = []
    st.session_state.selected_citation = None
    st.session_state.expect_zero_history_turn = True
    st.session_state.session_reset_pending = True


def _init_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "turn_traces" not in st.session_state:
        st.session_state.turn_traces = []
    if "selected_citation" not in st.session_state:
        st.session_state.selected_citation = None
    if "expect_zero_history_turn" not in st.session_state:
        st.session_state.expect_zero_history_turn = False
    if "session_reset_pending" not in st.session_state:
        st.session_state.session_reset_pending = False
    if "workspace" not in st.session_state:
        st.session_state.workspace = "Chat"
    if "show_dev_panel" not in st.session_state:
        st.session_state.show_dev_panel = False
    if "idea_draft" not in st.session_state:
        st.session_state.idea_draft = None
    if "active_topic" not in st.session_state:
        st.session_state.active_topic = "全部论文"


def _render_citation_buttons(turn_idx: int, answer: str, citations: list[dict[str, Any]]) -> None:
    citation_slots = _build_citation_slots(answer, citations)
    if not citation_slots:
        return

    st.caption("证据来源（点击查看）")
    cols = st.columns(min(6, len(citation_slots)))
    for idx, slot in enumerate(citation_slots):
        num = int(slot.get("citation_idx", 0))
        is_valid = bool(slot.get("valid"))
        col = cols[idx % len(cols)]
        with col:
            if is_valid and st.button(f"[{num}]", key=f"cite_{turn_idx}_{num}"):
                st.session_state.selected_citation = {"turn_idx": turn_idx, "citation_idx": num}
            if not is_valid:
                st.button(
                    f"[{num}]",
                    key=f"cite_disabled_{turn_idx}_{idx}_{num}",
                    disabled=True,
                    help="该引用未映射到 answer_citations",
                )
                st.markdown(
                    "<span style='color:#ca8a04;font-size:0.85rem;'>无映射</span>",
                    unsafe_allow_html=True,
                )


def _build_idea_draft_from_trace(turn_idx: int) -> dict[str, Any] | None:
    if not (0 <= turn_idx < len(st.session_state.turn_traces)):
        return None
    turn = st.session_state.turn_traces[turn_idx]
    report, _ = _load_turn_data(turn)
    answer = str(report.get("answer", "")).strip()
    if not answer:
        return None

    research_question = str(report.get("question") or report.get("standalone_query") or "").strip()
    method_outline = "\n".join(answer.splitlines()[:4]).strip()
    suggestions = list(report.get("assistant_summary_suggestions") or [])
    next_experiments = [str(x).strip() for x in suggestions if str(x).strip()][:3]

    evidence: list[dict[str, str]] = []
    for citation in report.get("answer_citations", []) or []:
        chunk_id = str(citation.get("chunk_id", "")).strip()
        if not chunk_id:
            continue
        matched = _find_evidence_by_chunk_id(report.get("evidence_grouped") or [], chunk_id) or {}
        evidence.append(
            {
                "chunk_id": chunk_id,
                "paper_id": str(citation.get("paper_id", "")).strip(),
                "section_page": str(citation.get("section_page", "")).strip(),
                "quote": str(matched.get("quote", "")).strip(),
            }
        )
    title = (answer.splitlines()[0] if answer else "").strip()[:60] or "新的研究灵感"

    return create_draft(
        title=title,
        research_question=research_question,
        method_outline=method_outline,
        next_experiments=next_experiments,
        evidence=evidence,
        source_session_id=str(st.session_state.session_id),
        source_turn_idx=turn_idx,
        topic=str(report.get("topic_name") or st.session_state.active_topic or ""),
    )


def _render_chat_messages() -> None:
    assistant_turn_idx = 0
    for message in st.session_state.chat_messages:
        role = message.get("role", "assistant")
        content = str(message.get("content", ""))
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(content)
            if role == "assistant":
                citations = message.get("answer_citations") or []
                navigation = message.get("paper_navigation") or []
                if navigation:
                    with st.expander("本轮命中文章导航（摘要层）", expanded=False):
                        for row in navigation:
                            title = str(row.get("title") or row.get("paper_id") or "未命名论文")
                            summary = str(row.get("one_paragraph_summary") or "").strip()
                            key_points = [str(x).strip() for x in (row.get("key_points") or []) if str(x).strip()]
                            st.markdown(f"**{title}**")
                            if summary:
                                st.caption(summary)
                            for idx, point in enumerate(key_points, start=1):
                                st.markdown(f"{idx}. {point}")
                turn_idx = int(message.get("trace_idx", assistant_turn_idx))
                _render_citation_buttons(turn_idx, content, citations)
                if st.button("生成灵感卡片", key=f"gen_idea_{turn_idx}"):
                    draft = _build_idea_draft_from_trace(turn_idx)
                    if draft is not None:
                        st.session_state.idea_draft = draft
                        st.session_state.workspace = "Ideas"
                        st.success("已生成灵感卡片草稿，请在 Ideas 中确认并保存。")
                        st.rerun()
                assistant_turn_idx += 1


def _render_selected_citation_detail() -> None:
    selected = st.session_state.selected_citation
    if not selected:
        return
    turn_idx = int(selected.get("turn_idx", -1))
    citation_idx = int(selected.get("citation_idx", 0))
    if not (0 <= turn_idx < len(st.session_state.turn_traces)):
        return

    target = st.session_state.turn_traces[turn_idx]
    report, _ = _load_turn_data(target)
    citations = report.get("answer_citations") or []
    if not (1 <= citation_idx <= len(citations)):
        return

    citation = citations[citation_idx - 1]
    chunk_id = str(citation.get("chunk_id") or "")
    matched = _find_evidence_by_chunk_id(report.get("evidence_grouped") or [], chunk_id)

    with st.expander(f"引用 [{citation_idx}] 的证据来源", expanded=True):
        if matched:
            st.markdown(f"**论文**: {matched.get('paper_title', matched.get('paper_id', 'N/A'))}")
            st.markdown(f"**位置**: {matched.get('section_page', citation.get('section_page', 'N/A'))}")
            st.markdown(f"**片段**: {matched.get('quote', '')}")
        else:
            st.json(citation)


def _render_inspector() -> None:
    st.sidebar.header("高级设置 / 开发者审查")

    if not st.session_state.turn_traces:
        st.sidebar.info("暂无会话。提交一个问题后将在这里显示 Trace。")
        return

    current = st.session_state.turn_traces[-1]
    report, trace = _load_turn_data(current)

    st.sidebar.subheader("Query 演变")
    st.sidebar.markdown(
        "\n".join(
            [
                f"- 原始输入: `{_na(report.get('question'))}`",
                f"- Rewrite 结果: `{_na(report.get('rewrite_rule_query') or trace.get('rewrite_query'))}`",
                f"- Calibrated Query: `{_na(report.get('calibrated_query') or trace.get('calibrated_query'))}`",
                f"- Intent Router: `{_na(report.get('intent_router_enabled', trace.get('intent_router_enabled')) )}`",
                f"- intent_type: `{_na(report.get('intent_type') or trace.get('intent_type'))}`",
                f"- anchor_query: `{_na(report.get('anchor_query') or trace.get('anchor_query'))}`",
                f"- topic_query_source: `{_na(report.get('topic_query_source') or trace.get('topic_query_source'))}`",
                f"- history_constraint_dropped: `{_na(_pick(report, trace, 'history_constraint_dropped'))}`",
                f"- dropped_constraints: `{_na(_pick(report, trace, 'dropped_constraints'))}`",
            ]
        )
    )
    st.sidebar.subheader("助理模式与门控")
    st.sidebar.markdown("\n".join(_assistant_mode_inspector_lines(report, trace)))

    st.sidebar.subheader("检索溯源（evidence_grouped）")
    evidence_grouped = report.get("evidence_grouped") or []
    if not evidence_grouped:
        st.sidebar.warning("本轮无 evidence_grouped 数据。")
    else:
        for g_idx, group in enumerate(evidence_grouped, start=1):
            title = f"{g_idx}. {group.get('paper_title', group.get('paper_id', 'unknown'))}"
            with st.sidebar.expander(title, expanded=(g_idx == 1)):
                for ev in group.get("evidence", []):
                    source = str(ev.get("source") or "N/A")
                    source_style = _source_badge_html(source)
                    st.markdown(
                        (
                            f"**{_na(ev.get('chunk_id'))}**  "
                            f"score_retrieval=`{_na(ev.get('score_retrieval'))}`  "
                            f"score_rerank=`{_na(ev.get('score_rerank'))}`  "
                            f"source={source_style}"
                        ),
                        unsafe_allow_html=True,
                    )
                    st.caption(_na(ev.get("quote")))

    decision = str(report.get("decision") or trace.get("decision") or "")
    reason = report.get("decision_reason") or trace.get("decision_reason") or trace.get("reason")
    warnings = report.get("output_warnings") or trace.get("output_warnings") or []
    alert_kind = _decision_alert_kind(decision)
    if alert_kind:
        block = f"decision={decision}\nreason={_na(reason)}\noutput_warnings={warnings or 'N/A'}"
        if alert_kind == "error":
            st.sidebar.error(block)
        elif alert_kind == "warning":
            st.sidebar.warning(block)

    with st.sidebar.expander("Raw Trace JSON"):
        st.json(trace if trace else {"warning": "trace missing"})


def _resolve_legacy_layout_switch() -> bool:
    env_value = os.getenv("UI_LEGACY_LAYOUT", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False
    config, _ = load_and_validate_config(DEFAULT_CONFIG)
    return bool(getattr(config, "ui_legacy_layout_default", False))


def _render_library_workspace() -> None:
    st.subheader("Library: 导入论文并组织专题")
    topics = load_topics()
    papers = load_papers()

    with st.expander("新建专题", expanded=False):
        new_topic = st.text_input("专题名称", value="", key="new_topic_name")
        if st.button("创建专题"):
            topic_name = new_topic.strip()
            if not topic_name:
                st.warning("请输入专题名称。")
            elif topic_name in topics:
                st.info("该专题已存在。")
            else:
                topics[topic_name] = []
                save_topics(topics)
                st.success(f"已创建专题：{topic_name}")
                st.rerun()

    topic_options = ["(不绑定专题)"] + sorted(topics.keys())
    selected_topic = st.selectbox("导入到专题", topic_options, index=0)
    uploaded = st.file_uploader(
        "导入论文（支持多选 PDF）",
        type=["pdf"],
        accept_multiple_files=True,
        help="导入后系统会自动准备知识库，然后可直接进入 Chat 提问。",
    )
    if st.button("开始导入论文", type="primary"):
        if not uploaded:
            st.warning("请先选择至少一篇 PDF。")
        else:
            staging_dir = DATA_DIR / "raw" / "_ui_upload_staging" / st.session_state.session_id
            staging_dir.mkdir(parents=True, exist_ok=True)
            file_paths: list[Path] = []
            for file in uploaded:
                dst = staging_dir / file.name
                dst.write_bytes(file.getvalue())
                file_paths.append(dst)
            progress_box = st.empty()
            progress_bar = st.progress(0, text="准备导入...")

            def _import_progress(step: int, total: int, message: str) -> None:
                ratio = 0.0 if total <= 0 else min(1.0, max(0.0, step / total))
                progress_bar.progress(int(ratio * 100), text=message)
                progress_box.caption(f"步骤 {step}/{total}: {message}")

            with st.spinner("正在导入并准备知识库..."):
                summary = run_import_workflow(
                    uploaded_files=file_paths,
                    topic=("" if selected_topic == "(不绑定专题)" else selected_topic),
                    config_path=DEFAULT_CONFIG,
                    progress_callback=_import_progress,
                )
            progress_bar.empty()
            progress_box.empty()
            if summary.get("ok"):
                st.success(f"导入完成：成功 {summary.get('success_count', 0)} 篇，失败 {summary.get('failed_count', 0)} 篇。")
                import_summary = summary.get("import_summary") or {}
                if import_summary:
                    added = int(import_summary.get("added", 0))
                    skipped = int(import_summary.get("skipped", 0))
                    conflicts = int(import_summary.get("conflicts", 0))
                    failed = int(import_summary.get("failed", 0))
                    st.caption("导入结果分类")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("新增", added)
                    c2.metric("已存在跳过", skipped)
                    c3.metric("冲突", conflicts)
                    c4.metric("失败", failed)
                index_stage = summary.get("index_stage") or {}
                if index_stage:
                    stage_map = {
                        "success": "已完成",
                        "failed": "失败",
                        "conflict": "冲突",
                    }
                    stage_text = stage_map.get(str(index_stage.get("status", "")).strip(), str(index_stage.get("status", "unknown")))
                    st.caption(
                        f"知识库准备阶段：{stage_text}，耗时约 {index_stage.get('duration_sec', 'N/A')} 秒。"
                    )
                next_steps = [str(x).strip() for x in (summary.get("next_steps") or []) if str(x).strip()]
                if next_steps:
                    st.caption("下一步建议：")
                    for idx, step in enumerate(next_steps, start=1):
                        st.markdown(f"{idx}. {step}")
                failure_reasons = [str(x).strip() for x in (summary.get("failure_reasons") or []) if str(x).strip()]
                if failure_reasons:
                    st.warning("部分文件未成功导入。")
                    with st.expander("查看失败原因", expanded=False):
                        for reason in failure_reasons:
                            st.markdown(f"- {reason}")
            else:
                st.error(f"导入失败：成功 {summary.get('success_count', 0)} 篇，失败 {summary.get('failed_count', 0)} 篇。")
                failure_reasons = [str(x).strip() for x in (summary.get("failure_reasons") or []) if str(x).strip()]
                next_steps = [str(x).strip() for x in (summary.get("next_steps") or []) if str(x).strip()]
                if failure_reasons:
                    for reason in failure_reasons:
                        st.markdown(f"- {reason}")
                elif summary.get("message"):
                    st.markdown(f"- {summary.get('message')}")
                if next_steps:
                    st.caption("建议下一步：")
                    for idx, step in enumerate(next_steps, start=1):
                        st.markdown(f"{idx}. {step}")

    st.markdown("---")
    st.markdown("**已收录论文**")
    if not papers:
        st.info("当前还没有论文，先导入 1-5 篇即可开始提问。")
        return

    paper_summary_lookup = _load_paper_summary_lookup()
    topics_by_paper: dict[str, list[str]] = {}
    for topic_name, paper_ids in topics.items():
        for pid in paper_ids:
            topics_by_paper.setdefault(pid, []).append(topic_name)

    search_text = st.text_input("搜索论文（标题/来源）", value="", key="catalog_search_text").strip().lower()
    source_filter = st.selectbox("来源筛选", ["全部", "pdf", "url"], index=0)
    status_values = sorted({str(row.get("status", "active")).strip() or "active" for row in papers})
    status_filter = st.selectbox("状态筛选", ["全部"] + status_values, index=0)
    topic_filter_options = ["全部专题"] + sorted(topics.keys())
    topic_filter = st.selectbox("专题筛选", topic_filter_options, index=0)
    sort_mode = st.selectbox("排序", ["导入时间(新->旧)", "标题(A-Z)", "来源类型"], index=0)

    filtered: list[dict[str, Any]] = []
    for row in papers:
        title = str(row.get("title", "")).strip()
        source_uri = str(row.get("source_uri", "")).strip()
        source_type = str(row.get("source_type", "pdf")).strip() or "pdf"
        status = str(row.get("status", "active")).strip() or "active"
        pid = str(row.get("paper_id", "")).strip()
        if search_text and search_text not in title.lower() and search_text not in source_uri.lower():
            continue
        if source_filter != "全部" and source_type != source_filter:
            continue
        if status_filter != "全部" and status != status_filter:
            continue
        if topic_filter != "全部专题" and topic_filter not in topics_by_paper.get(pid, []):
            continue
        enriched = dict(row)
        enriched["topics"] = topics_by_paper.get(pid, [])
        filtered.append(enriched)

    if sort_mode == "导入时间(新->旧)":
        filtered.sort(key=lambda x: str(x.get("imported_at", "")), reverse=True)
    elif sort_mode == "标题(A-Z)":
        filtered.sort(key=lambda x: str(x.get("title", "")).lower())
    else:
        filtered.sort(key=lambda x: (str(x.get("source_type", "")), str(x.get("title", "")).lower()))

    catalog_rows = []
    for row in filtered:
        pid = str(row.get("paper_id", ""))
        catalog_rows.append(
            {
                "paper_id": pid,
                "title": row.get("title"),
                "source_type": row.get("source_type"),
                "status": row.get("status"),
                "imported_at": row.get("imported_at"),
                "topics": ", ".join(row.get("topics", [])),
                "source_uri": row.get("source_uri"),
            }
        )

    st.caption(f"目录命中 {len(catalog_rows)} / {len(papers)} 篇")
    st.dataframe(catalog_rows, width="stretch", hide_index=True)

    if filtered:
        paper_options = [str(row.get("paper_id", "")) for row in filtered if str(row.get("paper_id", "")).strip()]
        selected_pid = st.selectbox(
            "论文详情",
            paper_options,
            format_func=lambda pid: next(
                (
                    f"{str(row.get('title') or pid)} ({pid})"
                    for row in filtered
                    if str(row.get("paper_id", "")) == pid
                ),
                pid,
            ),
        )
        selected_row = next((row for row in filtered if str(row.get("paper_id", "")) == selected_pid), {})
        summary = paper_summary_lookup.get(selected_pid, {})
        with st.expander("查看详情", expanded=False):
            st.markdown(f"**标题**: {selected_row.get('title', '')}")
            st.markdown(f"**paper_id**: `{selected_pid}`")
            st.markdown(f"**来源**: {selected_row.get('source_type', '')}")
            st.markdown(f"**source_uri**: {selected_row.get('source_uri', '')}")
            st.markdown(f"**导入时间**: {selected_row.get('imported_at', '')}")
            st.markdown(f"**状态**: {selected_row.get('status', '')}")
            st.markdown(f"**专题归属**: {', '.join(selected_row.get('topics', [])) or '无'}")
            st.markdown(f"**摘要**: {summary.get('one_paragraph_summary', '')}")
            key_points = summary.get("key_points") or []
            if key_points:
                st.markdown("**关键点**")
                for idx, point in enumerate(key_points[:5], start=1):
                    st.markdown(f"{idx}. {point}")

    st.markdown("### 专题批量管理")
    if topics:
        all_filtered_ids = [str(row.get("paper_id", "")) for row in filtered if str(row.get("paper_id", "")).strip()]
        selected_batch = st.multiselect(
            "选择论文（可多选）",
            options=all_filtered_ids,
            format_func=lambda pid: next(
                (
                    str(row.get("title", "")).strip() or pid
                    for row in filtered
                    if str(row.get("paper_id", "")) == pid
                ),
                pid,
            ),
        )
        target_topic = st.selectbox("目标专题", sorted(topics.keys()), index=0)
        batch_action = st.radio("操作", ["加入专题", "移出专题"], horizontal=True)
        if st.button("应用批量变更"):
            changed = 0
            topic_members = list(topics.get(target_topic, []))
            if batch_action == "加入专题":
                for pid in selected_batch:
                    if pid not in topic_members:
                        topic_members.append(pid)
                        changed += 1
            else:
                before = len(topic_members)
                topic_members = [pid for pid in topic_members if pid not in set(selected_batch)]
                changed = before - len(topic_members)
            topics[target_topic] = topic_members
            save_topics(topics)
            st.success(f"专题“{target_topic}”已更新，变更 {changed} 篇。")
            st.rerun()


def _topic_scope() -> tuple[str, list[str]]:
    topics = load_topics()
    options = ["全部论文"] + sorted(topics.keys())
    if st.session_state.active_topic not in options:
        st.session_state.active_topic = "全部论文"
    selected = st.selectbox("当前专题范围", options, index=options.index(st.session_state.active_topic))
    st.session_state.active_topic = selected
    if selected == "全部论文":
        return selected, []
    return selected, list(topics.get(selected, []))


def _run_prompt(prompt: str, topic_name: str, topic_paper_ids: list[str]) -> None:
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    live_placeholder = st.empty()
    live_chunks: list[str] = []

    def _stream_delta(piece: str) -> None:
        if not piece:
            return
        live_chunks.append(piece)
        live_placeholder.markdown("".join(live_chunks))

    try:
        with st.spinner("正在基于论文证据生成回答..."):
            run_result = _run_turn(
                prompt,
                st.session_state.session_id,
                topic_paper_ids=topic_paper_ids,
                topic_name=("" if topic_name == "全部论文" else topic_name),
                on_stream_delta=_stream_delta,
            )
            if len(run_result) == 4:
                report, trace, logs, run_dir = run_result
            else:  # backward-compatible for tests that patch _run_turn
                report, trace, logs = run_result  # type: ignore[misc]
                run_dir = DEFAULT_RUNS_DIR
    except Exception as exc:
        live_placeholder.empty()
        st.error(f"抱歉，推理过程中出现错误：{exc}")
        return
    live_placeholder.empty()

    reset_pending = bool(st.session_state.session_reset_pending)
    report, reset_guard_warning = _apply_session_reset_history_guard(
        report,
        expect_zero_history_turn=bool(st.session_state.expect_zero_history_turn),
    )
    if reset_guard_warning:
        st.warning(reset_guard_warning)
    if st.session_state.expect_zero_history_turn:
        st.session_state.expect_zero_history_turn = False
    st.session_state.session_reset_pending = False

    answer = str(report.get("answer") or "")
    citations = report.get("answer_citations") or []
    if not answer:
        answer = "N/A"

    st.session_state.chat_messages.append(
        {
            "role": "assistant",
            "content": answer,
            "answer_citations": citations,
            "paper_navigation": _build_paper_navigation(report),
            "trace_idx": len(st.session_state.turn_traces),
        }
    )

    trace = dict(trace or {})
    if trace.get("session_reset") is None:
        trace["session_reset"] = reset_pending
    if bool(st.session_state.get("show_dev_panel")):
        trace["ui_logs"] = logs

    st.session_state.turn_traces.append(
        {
            "report": _compact_turn_report(report),
            "trace": _compact_turn_trace(trace),
            "report_path": str(run_dir / "qa_report.json"),
            "trace_path": str(run_dir / "run_trace.json"),
        }
    )
    st.rerun()


def _render_chat_workspace() -> None:
    st.subheader("Chat: 面向科研任务的问答")
    topic_name, topic_paper_ids = _topic_scope()
    if topic_name == "全部论文":
        st.caption("当前在全部论文范围内回答。")
    else:
        st.caption(f"当前专题：{topic_name}（{len(topic_paper_ids)} 篇论文）")

    _render_chat_messages()
    _render_selected_citation_detail()

    prompt = st.chat_input("输入你的科研问题，例如：这个方向还能设计哪些可验证实验？")
    if prompt:
        _run_prompt(prompt, topic_name, topic_paper_ids)


def _render_idea_draft_editor() -> None:
    draft = st.session_state.idea_draft
    if not draft:
        return

    st.markdown("### 待保存草稿")
    title = st.text_input("卡片标题", value=str(draft.get("title", "")), key="draft_title")
    rq = st.text_area("研究问题", value=str(draft.get("research_question", "")), key="draft_rq")
    method_outline = st.text_area("方法思路", value=str(draft.get("method_outline", "")), key="draft_method")
    next_exp = st.text_area(
        "下一步实验（每行一条）",
        value="\n".join(draft.get("next_experiments", [])),
        key="draft_next_exp",
    )
    evidence = draft.get("evidence", [])
    st.caption(f"证据条目: {len(evidence)}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("保存灵感卡片", type="primary"):
            card = dict(draft)
            card["title"] = title
            card["research_question"] = rq
            card["method_outline"] = method_outline
            card["next_experiments"] = [line.strip() for line in next_exp.splitlines() if line.strip()]
            saved = save_card(card)
            st.session_state.idea_draft = None
            st.success(f"已保存卡片：{saved.get('title', '')}")
            st.rerun()
    with col2:
        if st.button("放弃草稿"):
            st.session_state.idea_draft = None
            st.info("已清空草稿。")
            st.rerun()


def _render_ideas_workspace() -> None:
    st.subheader("Ideas: 管理灵感卡片")
    _render_idea_draft_editor()

    cards = list_cards()
    if not cards:
        st.info("还没有卡片。先在 Chat 中点击“生成灵感卡片”。")
        return

    st.caption(f"当前卡片总数：{len(cards)}")
    for card in cards:
        title = str(card.get("title") or card.get("card_id", "未命名卡片"))
        status = str(card.get("status", "draft"))
        updated_at = str(card.get("updated_at", ""))
        with st.expander(f"[{status}] {title} · 更新时间 {updated_at}", expanded=False):
            st.markdown(f"**研究问题**: {card.get('research_question', '')}")
            st.markdown(f"**方法思路**: {card.get('method_outline', '')}")
            next_exp = card.get("next_experiments", [])
            if next_exp:
                st.markdown("**下一步实验**")
                for idx, item in enumerate(next_exp, start=1):
                    st.markdown(f"{idx}. {item}")
            evidence = card.get("evidence", [])
            st.caption(f"证据条目：{len(evidence)}")

            status_options = list(IDEA_STATUS_FLOW)
            status_idx = status_options.index(status) if status in status_options else 0
            target = st.selectbox(
                "更新状态",
                status_options,
                index=status_idx,
                key=f"status_target_{card.get('card_id')}",
            )
            if st.button("应用状态变更", key=f"status_apply_{card.get('card_id')}"):
                ok, err = update_card_status(str(card.get("card_id")), target)
                if ok:
                    st.success(f"状态已更新为 {target}")
                    st.rerun()
                else:
                    st.error(err)


def _render_legacy_layout() -> None:
    st.title("RAG Visual Inspector")
    st.caption("已启用旧布局（可设置 UI_LEGACY_LAYOUT=0 切回新布局）")

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.write(f"当前 session_id: `{st.session_state.session_id}`")
    with top_col2:
        if st.button("开启新对话 / 清空上下文", type="primary"):
            old_session_id = st.session_state.session_id
            cleared = clear_session(old_session_id, DEFAULT_SESSION_STORE)
            st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"
            _reset_chat_state()
            st.success(
                f"已触发 clear_session('{old_session_id}') -> {cleared}，新会话: {st.session_state.session_id}"
            )

    _render_chat_messages()
    _render_inspector()

    prompt = st.chat_input("请输入问题")
    if prompt:
        _run_prompt(prompt, "全部论文", [])


def main() -> None:
    if not _STREAMLIT_AVAILABLE:
        raise RuntimeError("streamlit is not installed. Install streamlit to run the UI.")

    st.set_page_config(page_title="Research Paper Assistant", layout="wide")
    _init_state()

    if _resolve_legacy_layout_switch():
        _render_legacy_layout()
        return

    st.title("科研助手工作台")
    st.caption("正在使用变更：research-assistant-user-friendly-workflow（可通过 /opsx:apply <other> 覆盖）")

    top_col1, top_col2 = st.columns([3, 1])
    with top_col1:
        st.write(f"当前 session_id: `{st.session_state.session_id}`")
    with top_col2:
        if st.button("开启新对话", type="primary"):
            old_session_id = st.session_state.session_id
            cleared = clear_session(old_session_id, DEFAULT_SESSION_STORE)
            st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"
            _reset_chat_state()
            st.success(f"已清空旧会话并创建新会话（clear={cleared}）。")

    workspace_options = ["Library", "Chat", "Ideas"]
    st.session_state.workspace = st.radio(
        "工作区",
        workspace_options,
        index=workspace_options.index(st.session_state.workspace)
        if st.session_state.workspace in workspace_options
        else 1,
        horizontal=True,
    )

    st.sidebar.checkbox("显示开发者审查面板", key="show_dev_panel")
    if st.session_state.show_dev_panel:
        _render_inspector()

    if st.session_state.workspace == "Library":
        _render_library_workspace()
    elif st.session_state.workspace == "Ideas":
        _render_ideas_workspace()
    else:
        _render_chat_workspace()


if __name__ == "__main__":
    main()
