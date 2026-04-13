from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import yaml

from app.capability_planner import (
    build_planner_fallback,
    compose_catalog_answer,
    detect_new_topic,
    execute_catalog_lookup,
    parse_planner_result,
)
from app.context_budget import ContextAssemblyResult, assemble_prompt_with_budget
from app.config import load_and_validate_config
from app.document_structure import (
    STRUCTURE_READY,
    is_structure_question,
    load_structure_index,
    retrieve_sections,
    summarize_structure_status,
)
from app.generate import build_answer
from app.intent_calibration import CalibrationResult, calibrate_query_intent, strip_summary_cues
from app.llm_diagnostics import build_llm_diagnostics
from app.llm_client import call_chat_completion, call_chat_completion_stream
from app.llm_routing import build_stage_policy, classify_error_category
from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index, load_vec_index
from app.rewrite import RewriteGuardResult, RewriteResult, apply_state_aware_rewrite_guard, rewrite_query
from app.rerank import rerank_candidates
from app.retrieve import (
    RetrievalCandidate,
    expand_candidates_with_graph,
    load_paper_summaries,
    recall_papers_by_summary,
    load_indexes_and_config,
    retrieve_candidates,
)
from app.runlog import create_run_dir, save_json, validate_trace_schema
from app.paths import CONFIGS_DIR, DATA_DIR, RUNS_DIR
from app.planner_policy import (
    apply_assistant_mode_decision_policy,
    build_constraint_envelope,
    prefer_assistant_mode_clarify,
    resolve_final_interaction_decision,
)
from app.planner_runtime import (
    _build_planner_llm_candidate,
    _planner_policy_flags,
    _serialize_capability_registry,
    _validate_llm_planner_decision,
)
from app.session_state import (
    append_turn_record,
    build_control_intent_anchor_query,
    build_history_brief,
    clear_session,
    derive_rewrite_context,
    load_dialog_state,
    load_history_window,
    load_pending_clarify,
    merge_with_pending_clarify,
    rewrite_with_history_context,
)
from app.sufficiency import run_sufficiency_gate as run_sufficiency_gate_impl
from app.vector_backend import resolve_vector_backend

AMBIGUOUS_SCOPE_TERMS = (
    "this work",
    "this paper",
    "the authors",
    "our method",
    "in this study",
    "本文",
    "这篇论文",
    "作者",
)

SCOPE_CLARIFY_HINT_TERMS = (
    "author",
    "authors",
    "affiliation",
    "institute",
    "institution",
    "email",
    "corresponding",
    "作者",
    "单位",
    "机构",
    "邮箱",
    "通讯作者",
)

SUMMARY_SHELL_PATTERNS = (
    r"\bin summary\b",
    r"\bsummary of\b",
    r"\breporting summary\b",
    r"\bthis paper:\s*•\s*introduces\b",
    r"\bin this survey paper\b",
)

NOISY_CONTENT_TYPES = {"front_matter", "reference"}
MAX_EVIDENCE_PER_PAPER = 2
MAX_PAPERS_DISPLAY = 6
TOP_PAPERS_REQUIRE_EVIDENCE = 5
CLAIM_EXPERIMENT_TERMS = (
    "experiment",
    "experiments",
    "evaluation",
    "result",
    "results",
    "accuracy",
    "f1",
    "precision",
    "recall",
    "ablation",
    "实验",
    "评估",
    "结果",
    "准确率",
    "召回率",
    "消融",
)
CLAIM_DEFINITION_TERMS = (
    "is defined as",
    "defined as",
    "refers to",
    "means",
    "定义为",
    "是指",
    "指的是",
)
CLAIM_CONCLUSION_TERMS = (
    "therefore",
    "thus",
    "we conclude",
    "demonstrates",
    "shows that",
    "表明",
    "说明",
    "证明",
    "因此",
)
FORMAT_NUMBER_PATTERNS = (
    re.compile(r"^\s*\d+[\.\)]\s*"),
    re.compile(r"^\s*第\s*\d+(?:\.\d+)?\s*[章节节]\s*"),
)
FORMAT_LOCATOR_RE = re.compile(r"\bp\.\s*\d+\b", flags=re.IGNORECASE)
FORMAT_LOCATOR_SENTENCE_RE = re.compile(r"(第\s*\d+(?:\.\d+)?\s*[章节节])|(\bp\.\s*\d+\b)|(^\s*\d+[\.\)])", flags=re.IGNORECASE)
CLAIM_UNCERTAINTY_TERMS = (
    "insufficient evidence",
    "not enough evidence",
    "lack of evidence",
    "cannot determine",
    "can't determine",
    "uncertain",
    "unknown",
    "信息不足",
    "证据不足",
    "无法判断",
    "无法确定",
    "不确定",
    "没有明确说明",
    "未明确说明",
)
CLAIM_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "what",
    "which",
    "问题",
    "论文",
    "研究",
    "我们",
    "可以",
    "一个",
}
OPEN_SUMMARY_TERMS = (
    "总结",
    "概览",
    "方向",
    "重点",
    "下一步",
    "后续提问",
    "值得关注",
    "overview",
    "summarize",
    "summary",
    "key directions",
    "next question",
    "what should i ask next",
)
STYLE_CONTROL_PATTERNS = (
    r"^(请)?(用|以)?中文(来)?(回答|说|写)",
    r"^(请)?(用|以)?英文(来)?(回答|说|写)",
    r"^(请)?(换成|切换到).*(中文|英文)",
    r"^(请)?(简短|详细|更详细|更简短)(一点|些)?",
)
FORMAT_CONTROL_PATTERNS = (
    r"^(请)?(用|按).*(列表|表格|markdown|json|要点|bullet|项目符号)",
    r"^(请)?(分点|分条|给出要点|列出来)",
)
CONTINUATION_CONTROL_PATTERNS = (
    r"^(继续|接着|再说|往下|继续回答|继续说)",
    r"^(然后呢|后面呢|继续讲)",
)


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split())


def _semantic_route_score(text: str, exemplar: str) -> float:
    tset = _tokenize_for_matching(text)
    eset = _tokenize_for_matching(exemplar)
    if not tset or not eset:
        return 0.0
    inter = len(tset.intersection(eset))
    denom = max(1, min(len(tset), len(eset)))
    return inter / denom


def _extract_intent_params(text: str, intent_type: str) -> dict[str, Any]:
    lowered = _normalize_spaces(text).lower()
    params: dict[str, Any] = {}
    if intent_type == "style_control":
        if "中文" in lowered or "chinese" in lowered:
            params["language"] = "zh"
        elif "英文" in lowered or "english" in lowered:
            params["language"] = "en"
        if any(k in lowered for k in ("简短", "简洁", "brief")):
            params["verbosity"] = "brief"
        elif any(k in lowered for k in ("详细", "detail")):
            params["verbosity"] = "detailed"
    elif intent_type == "format_control":
        if any(k in lowered for k in ("表格", "table")):
            params["format"] = "table"
        elif "json" in lowered:
            params["format"] = "json"
        elif any(k in lowered for k in ("markdown", "md")):
            params["format"] = "markdown"
        elif any(k in lowered for k in ("要点", "列表", "bullet", "项目符号", "分点", "分条")):
            params["format"] = "bullet"
    elif intent_type == "continuation_control":
        params["continuation"] = True
    return params


def semantic_route_intent(user_text: str) -> tuple[str, float, str, dict[str, Any]]:
    normalized = _normalize_spaces(user_text).lower()
    if not normalized:
        return "retrieval_query", 1.0, "semantic_model", {}
    if ("继续" in normalized or "接着" in normalized) and (
        "刚才" in normalized or "上一个" in normalized or "上轮" in normalized or "之前" in normalized
    ):
        return "continuation_control", 0.88, "semantic_model", {"continuation": True}

    exemplars: dict[str, tuple[str, ...]] = {
        "continuation_control": (
            "继续刚才的问题",
            "接着上一个回答往下说",
            "continue previous answer",
            "go on with last topic",
        ),
        "format_control": (
            "换成表格展示",
            "用要点列表回答",
            "format as markdown table",
            "answer in bullet points",
        ),
        "style_control": (
            "请用中文回答",
            "改成英文更简短",
            "respond in chinese",
            "answer in english briefly",
        ),
    }
    best_intent = "retrieval_query"
    best_score = 0.0
    for intent, items in exemplars.items():
        score = max((_semantic_route_score(normalized, ex) for ex in items), default=0.0)
        if score > best_score:
            best_score = score
            best_intent = intent
    params = _extract_intent_params(normalized, best_intent if best_intent != "retrieval_query" else "retrieval_query")
    if params and best_intent != "retrieval_query":
        best_score = max(best_score, 0.78)
        # Mixed "control + factual content" should be lower-confidence and allow fallback.
        control_terms = {
            "中文",
            "英文",
            "style",
            "format",
            "表格",
            "列表",
            "要点",
            "markdown",
            "json",
            "继续",
            "接着",
            "回答",
        }
        tokens = _tokenize_for_matching(normalized)
        if tokens:
            control_hits = sum(1 for t in tokens if any(c in t for c in control_terms))
            control_ratio = control_hits / max(1, len(tokens))
            if control_ratio < 0.6:
                best_score = min(best_score, 0.82)
    if best_intent == "retrieval_query":
        best_score = 1.0
    return best_intent, round(best_score, 4), "semantic_model", params


def classify_intent_type_with_confidence(user_text: str) -> tuple[str, float, str | None]:
    normalized = _normalize_spaces(user_text).lower()
    if not normalized:
        return "retrieval_query", 1.0, None

    def _match_intent(patterns: tuple[str, ...], intent: str) -> tuple[str, float, str] | None:
        for pattern in patterns:
            matched = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not matched:
                continue
            coverage = len(_normalize_spaces(matched.group(0))) / max(1, len(normalized))
            confidence = 0.55 + 0.45 * max(0.0, min(1.0, coverage))
            return intent, round(confidence, 4), pattern
        return None

    for patterns, intent in (
        (CONTINUATION_CONTROL_PATTERNS, "continuation_control"),
        (FORMAT_CONTROL_PATTERNS, "format_control"),
        (STYLE_CONTROL_PATTERNS, "style_control"),
    ):
        matched_intent = _match_intent(patterns, intent)
        if matched_intent is not None:
            return matched_intent
    return "retrieval_query", 1.0, None


def ensure_indexes(
    *,
    chunks_path: str,
    bm25_index_path: str,
    vec_index_path: str,
    embed_index_path: str,
    config_path: str,
    mode: str,
) -> dict[str, Any]:
    build_metrics: dict[str, Any] = {
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
    }
    if not Path(bm25_index_path).exists():
        build_bm25_index(chunks_path, bm25_index_path)
    if not Path(vec_index_path).exists():
        build_vec_index(chunks_path, vec_index_path)
    config, _ = load_and_validate_config(config_path)
    needs_embedding = config.embedding.enabled and (
        config.dense_backend == "embedding" and mode in {"dense", "hybrid"}
    )
    if needs_embedding:
        embed_path = Path(embed_index_path)
        rebuild_embed = not embed_path.exists()
        rebuild_reason = "missing_index"
        if not rebuild_embed:
            try:
                embed_idx = load_vec_index(embed_path)
                # Defensive self-healing for stale/broken embedding indexes
                # (e.g., built during API outage with placeholder dim=1 vectors).
                if (
                    embed_idx.index_type != "embedding"
                    or embed_idx.embedding_dim <= 1
                    or not embed_idx.docs
                    or not embed_idx.embeddings
                ):
                    rebuild_embed = True
                    rebuild_reason = "invalid_or_stale_index"
            except Exception:
                rebuild_embed = True
                rebuild_reason = "load_failed"

        if rebuild_embed:
            print(
                f"[info] rebuilding embedding index ({rebuild_reason}): {embed_index_path}",
                file=sys.stderr,
            )
            backend = resolve_vector_backend("file")
            t0 = perf_counter()
            last_reported = {"step": -1}

            def _progress(step: int, total: int) -> None:
                total = max(1, int(total))
                step = min(max(0, int(step)), total)
                interval = max(1, total // 100)
                if (
                    last_reported["step"] != -1
                    and step != total
                    and step - last_reported["step"] < interval
                ):
                    return
                last_reported["step"] = step
                print(
                    f"\r[info] embedding rebuild progress: {step}/{total}",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

            def _status(msg: str) -> None:
                print(f"\n[info] {msg}", file=sys.stderr, flush=True)

            embed_idx, embed_stats = backend.rebuild(
                chunks_path=chunks_path,
                output_path=embed_index_path,
                embedding_cfg=config.embedding,
                progress_callback=_progress,
                status_callback=_status,
            )
            elapsed_ms = int((perf_counter() - t0) * 1000)
            print(file=sys.stderr)
            print(
                "[info] embedding index rebuilt: "
                f"docs={len(embed_idx.docs)} dim={embed_idx.embedding_dim} "
                f"hits={embed_stats.cache_hits} miss={embed_stats.cache_miss} "
                f"api_calls={embed_stats.api_calls} failed={embed_stats.failed_items} "
                f"elapsed_ms={elapsed_ms}",
                file=sys.stderr,
            )
            build_metrics = {
                "embedding_build_time_ms": int(embed_stats.build_time_ms or elapsed_ms),
                "embedding_failed_count": int(embed_stats.failed_items),
                "embedding_failed_chunk_ids": list(embed_stats.embedding_failed_chunk_ids),
                "embedding_batch_failures": list(embed_stats.embedding_batch_failures),
                "rate_limited_count": int(embed_stats.rate_limited_count),
                "backoff_total_ms": int(embed_stats.backoff_total_ms),
                "truncated_count": int(embed_stats.truncated_count),
                "skipped_over_limit_count": int(embed_stats.skipped_over_limit_count),
                "skipped_empty": int(embed_stats.skipped_empty),
                "skipped_empty_chunk_ids": list(embed_stats.skipped_empty_chunk_ids),
            }
    return build_metrics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal QA CLI for M2 baseline")
    parser.add_argument("--q", required=True, help="Question text")
    parser.add_argument("--mode", default="hybrid", choices=["dense", "bm25", "hybrid"], help="Retrieval mode")
    parser.add_argument("--chunks", default=str(DATA_DIR / "processed" / "chunks_clean.jsonl"), help="Input chunks_clean.jsonl")
    parser.add_argument("--bm25-index", default=str(DATA_DIR / "indexes" / "bm25_index.json"), help="BM25 index path")
    parser.add_argument("--vec-index", default=str(DATA_DIR / "indexes" / "vec_index.json"), help="Vector index path")
    parser.add_argument("--embed-index", default=str(DATA_DIR / "indexes" / "vec_index_embed.json"), help="Embedding index path")
    parser.add_argument("--config", default=str(CONFIGS_DIR / "default.yaml"), help="Config path")
    parser.add_argument("--top-k", type=int, default=None, help="Override retrieval top-k")
    parser.add_argument("--top-evidence", type=int, default=5, help="Number of evidence items to output")
    parser.add_argument("--session-id", default="default", help="Session id for multi-turn memory")
    parser.add_argument(
        "--session-store",
        default=str(DATA_DIR / "session_store.json"),
        help="Session store path (dehydrated history only)",
    )
    parser.add_argument("--clear-session", action="store_true", help="Clear this session before answering")
    parser.add_argument(
        "--topic-paper-ids",
        default="",
        help="Optional comma-separated paper_id scope for topic-bound QA",
    )
    parser.add_argument(
        "--topic-name",
        default="",
        help="Optional topic name for scoped QA",
    )
    parser.add_argument("--run-id", default="", help="Optional run id used as run directory name")
    parser.add_argument("--run-dir", default="", help="Optional explicit run directory path")
    return parser.parse_args(argv)


def _has_paper_clue(question: str) -> bool:
    q = question.lower()
    if re.search(r"\b(19|20)\d{2}\b", q):
        return True
    if re.search(r"\b[0-9a-f]{12}\b", q):
        return True
    if "\"" in question or "《" in question or "》" in question:
        return True
    if any(term in q for term in ("title", "paper id", "doi", "arxiv", "论文标题", "题目")):
        return True
    return False


def resolve_scope_policy(question: str) -> tuple[str, str, dict[str, Any]]:
    q = question.lower()
    matched_ambiguous = [term for term in AMBIGUOUS_SCOPE_TERMS if term in q]
    has_ambiguous_scope = bool(matched_ambiguous)
    has_paper_clue = _has_paper_clue(question)
    matched_clarify = [term for term in SCOPE_CLARIFY_HINT_TERMS if term in q]
    should_clarify = bool(matched_clarify)

    reason = {
        "matched_ambiguous_terms": matched_ambiguous,
        "matched_clarify_terms": matched_clarify,
        "has_paper_clue": has_paper_clue,
    }

    if not has_ambiguous_scope or has_paper_clue:
        reason["rule"] = "open_by_default_or_has_paper_clue"
        return "open", question, reason

    if should_clarify:
        reason["rule"] = "clarify_by_author_or_affiliation_intent"
        return "clarify_scope", question, reason

    reason["rule"] = "rewrite_for_cross_paper_mode"
    return "rewrite_scope", question, reason


def is_summary_shell(text: str) -> bool:
    raw = " ".join((text or "").split())
    if not raw:
        return False
    for pattern in SUMMARY_SHELL_PATTERNS:
        if re.search(pattern, raw, flags=re.IGNORECASE):
            return True
    lowered = raw.lower()
    if len(raw) <= 120 and (lowered.startswith("summary") or lowered.startswith("abstract")):
        return True
    return False


def summary_shell_ratio(candidates: list[RetrievalCandidate], *, top_n: int = 5) -> float:
    top = candidates[:top_n]
    if not top:
        return 0.0
    shell_count = sum(1 for c in top if is_summary_shell(c.text))
    return shell_count / len(top)


def _load_paper_title_map(chunks_path: str) -> dict[str, str]:
    papers_path = Path(chunks_path).parent / "papers.json"
    if not papers_path.exists():
        return {}

    data = json.loads(papers_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return {}

    mapping: dict[str, str] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        title = str(row.get("title", "")).strip()
        if paper_id:
            mapping[paper_id] = title or paper_id
    return mapping


def _build_candidate_lookup(*, bm25_index: Any, vec_index: Any) -> dict[str, RetrievalCandidate]:
    lookup: dict[str, RetrievalCandidate] = {}
    for doc in getattr(bm25_index, "docs", []) or []:
        lookup[str(doc.chunk_id)] = RetrievalCandidate(
            chunk_id=str(doc.chunk_id),
            score=0.0,
            content_type=str(getattr(doc, "content_type", "body") or "body"),
            paper_id=str(getattr(doc, "paper_id", "") or ""),
            page_start=int(getattr(doc, "page_start", 0) or 0),
            section=(str(getattr(doc, "section", "")).strip() or None),
            text=str(getattr(doc, "text", "") or ""),
            clean_text=str(getattr(doc, "clean_text", "") or ""),
        )
    for doc in getattr(vec_index, "docs", []) or []:
        lookup.setdefault(
            str(doc.chunk_id),
            RetrievalCandidate(
                chunk_id=str(doc.chunk_id),
                score=0.0,
                content_type=str(getattr(doc, "content_type", "body") or "body"),
                paper_id=str(getattr(doc, "paper_id", "") or ""),
                page_start=int(getattr(doc, "page_start", 0) or 0),
                section=(str(getattr(doc, "section", "")).strip() or None),
                text=str(getattr(doc, "text", "") or ""),
                clean_text=str(getattr(doc, "clean_text", "") or ""),
            ),
        )
    return lookup


def _candidate_from_section_match(
    *,
    match: Any,
    chunk_id: str,
    base: RetrievalCandidate,
    rank: int,
) -> RetrievalCandidate:
    payload = dict(base.payload or {})
    payload["source"] = "section"
    payload["retrieval_source"] = "section"
    payload["section_id"] = str(match.section_id)
    payload["section_title"] = str(match.section_title)
    payload["heading_path"] = list(match.heading_path)
    payload["score_retrieval"] = round(float(match.score) - (rank * 0.001), 6)
    payload["structure_coverage"] = str(match.coverage)
    return RetrievalCandidate(
        chunk_id=chunk_id,
        score=float(payload["score_retrieval"]),
        content_type=base.content_type,
        payload=payload,
        paper_id=base.paper_id,
        page_start=base.page_start,
        section=base.section or str(match.section_title),
        text=base.text,
        clean_text=base.clean_text,
        block_type=base.block_type,
        markdown_source=base.markdown_source,
        structure_provenance=dict(base.structure_provenance or {}) or None,
    )


def _section_or_page(candidate: RetrievalCandidate) -> str:
    return candidate.section if candidate.section else f"p.{candidate.page_start}"


def _build_quote(text: str, min_len: int = 50, max_len: int = 120) -> str | None:
    raw = " ".join((text or "").split())
    if not raw:
        return None
    if len(raw) <= min_len:
        return raw
    if len(raw) <= max_len:
        return raw

    clipped = raw[:max_len].rstrip()
    return clipped


def _build_papers_ranked(
    candidates: list[RetrievalCandidate],
    paper_titles: dict[str, str],
    *,
    top_supporting: int = 10,
) -> list[dict[str, Any]]:
    grouped_scores: dict[str, list[float]] = defaultdict(list)
    grouped_chunks: dict[str, list[str]] = defaultdict(list)

    for c in candidates:
        pid = c.paper_id or "unknown-paper"
        grouped_scores[pid].append(float(c.score))
        grouped_chunks[pid].append(c.chunk_id)

    rows: list[dict[str, Any]] = []
    for pid, scores in grouped_scores.items():
        max_score = max(scores) if scores else 0.0
        mean_score = sum(scores) / len(scores) if scores else 0.0
        rows.append(
            {
                "paper_id": pid,
                "paper_title": paper_titles.get(pid, pid),
                "score_paper": max_score,
                "_score_mean": mean_score,
                "supporting_chunks": grouped_chunks[pid][:top_supporting],
            }
        )

    rows.sort(key=lambda x: (x["score_paper"], x["_score_mean"]), reverse=True)
    for row in rows:
        row.pop("_score_mean", None)
    return rows


def _candidate_to_evidence_item(candidate: RetrievalCandidate) -> dict[str, Any]:
    quote = _build_quote(candidate.text)
    if quote is None:
        quote = (candidate.text or "").strip()
    payload = dict(candidate.payload or {})
    return {
        "chunk_id": candidate.chunk_id,
        "section_page": _section_or_page(candidate),
        "section_id": str(payload.get("section_id", "")),
        "section_title": str(payload.get("section_title", candidate.section or "")),
        "quote": quote,
        "paper_id": candidate.paper_id or "unknown-paper",
        "content_type": candidate.content_type or "body",
        "source": str(payload.get("source", "")),
        "score_retrieval": float(payload.get("score_retrieval", candidate.score)),
        "score_rerank": float(payload.get("score_rerank", candidate.score)),
        "structure_coverage": str(payload.get("structure_coverage", "")),
        "block_type": str(candidate.block_type or ""),
        "markdown_source": str(candidate.markdown_source or ""),
        "structure_provenance": dict(candidate.structure_provenance or {}) or None,
    }


def _build_evidence_grouped(
    candidates: list[RetrievalCandidate],
    papers_ranked: list[dict[str, Any]],
    paper_titles: dict[str, str],
    *,
    max_per_paper: int = MAX_EVIDENCE_PER_PAPER,
    max_papers_display: int = MAX_PAPERS_DISPLAY,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    grouped_candidates: dict[str, list[RetrievalCandidate]] = defaultdict(list)
    for c in candidates:
        grouped_candidates[c.paper_id or "unknown-paper"].append(c)

    target_papers = [row["paper_id"] for row in papers_ranked[:max_papers_display]]
    evidence_grouped: list[dict[str, Any]] = []

    for pid in target_papers:
        bucket = grouped_candidates.get(pid, [])
        evidence_items = [_candidate_to_evidence_item(c) for c in bucket[:max_per_paper]]
        evidence_grouped.append(
            {
                "paper_id": pid,
                "paper_title": paper_titles.get(pid, pid),
                "evidence": evidence_items,
            }
        )

    if evidence_grouped:
        top_group = evidence_grouped[0]
        if not top_group.get("evidence"):
            top_pid = top_group.get("paper_id", "")
            top_candidates = grouped_candidates.get(top_pid, [])
            if top_candidates:
                top_group["evidence"] = [_candidate_to_evidence_item(top_candidates[0])]
                warnings.append("top_paper_has_no_evidence_fixed")

    for row in papers_ranked[:TOP_PAPERS_REQUIRE_EVIDENCE]:
        pid = row["paper_id"]
        group = next((g for g in evidence_grouped if g.get("paper_id") == pid), None)
        if group is None and len(evidence_grouped) < max_papers_display:
            fallback_candidates = grouped_candidates.get(pid, [])
            if fallback_candidates:
                evidence_grouped.append(
                    {
                        "paper_id": pid,
                        "paper_title": paper_titles.get(pid, pid),
                        "evidence": [_candidate_to_evidence_item(fallback_candidates[0])],
                    }
                )
        elif group is not None and not group.get("evidence"):
            fallback_candidates = grouped_candidates.get(pid, [])
            if fallback_candidates:
                group["evidence"] = [_candidate_to_evidence_item(fallback_candidates[0])]
                if pid == papers_ranked[0]["paper_id"] and "top_paper_has_no_evidence_fixed" not in warnings:
                    warnings.append("top_paper_has_no_evidence_fixed")

    return evidence_grouped[:max_papers_display], warnings


def _flatten_evidence(evidence_grouped: list[dict[str, Any]]) -> list[dict[str, str]]:
    flat: list[dict[str, str]] = []
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            merged = dict(item)
            merged["paper_id"] = group.get("paper_id", merged.get("paper_id", "unknown-paper"))
            flat.append(merged)
    return flat


def _filter_candidates_by_topic(
    candidates: list[RetrievalCandidate],
    allowed_paper_ids: set[str],
) -> tuple[list[RetrievalCandidate], int]:
    if not allowed_paper_ids:
        return list(candidates), 0
    kept: list[RetrievalCandidate] = []
    dropped = 0
    for row in candidates:
        pid = str(row.paper_id or "").strip()
        if pid in allowed_paper_ids:
            kept.append(row)
        else:
            dropped += 1
    return kept, dropped


def _build_answer_citations(evidence_grouped: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for group in evidence_grouped:
        pid = group.get("paper_id", "unknown-paper")
        for item in group.get("evidence", []):
            citations.append(
                {
                    "chunk_id": item.get("chunk_id", ""),
                    "paper_id": pid,
                    "section_page": item.get("section_page", ""),
                    "block_type": item.get("block_type", ""),
                    "structure_provenance": item.get("structure_provenance"),
                }
            )
    return [c for c in citations if c["chunk_id"]]


def _build_structure_coverage_notice(
    *,
    retrieval_route: str,
    structure_parse_status: str,
    evidence_grouped: list[dict[str, Any]],
) -> str | None:
    if retrieval_route != "section":
        return None
    if structure_parse_status != STRUCTURE_READY:
        return "当前仅基于局部章节证据，文档结构解析未达到完整可用状态。"
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            if str(item.get("structure_coverage", "")).strip() == "partial":
                return "当前仅基于局部章节证据。"
    return None


def _prepend_notice(answer: str, notice: str | None) -> str:
    text = str(answer or "").strip()
    note = str(notice or "").strip()
    if not note:
        return text
    if text.startswith(note):
        return text
    if not text:
        return note
    return f"{note}\n\n{text}"


def _build_claim_plan(evidence_grouped: list[dict[str, Any]], *, max_claims: int = 5) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            quote = _normalize_spaces(str(item.get("quote", "")))
            if not quote:
                continue
            snippet = quote[:120] + ("..." if len(quote) > 120 else "")
            plan.append(
                {
                    "claim": snippet,
                    "chunk_id": str(item.get("chunk_id", "")).strip(),
                    "paper_id": str(group.get("paper_id", "unknown-paper")).strip(),
                    "section_page": str(item.get("section_page", "")).strip(),
                    "section_id": str(item.get("section_id", "")).strip(),
                }
            )
            if len(plan) >= max_claims:
                return plan
    return plan


def _render_claim_bound_answer(claim_plan: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    if not claim_plan:
        return "当前证据不足，无法生成可追溯的结论。", []

    citations: list[dict[str, str]] = []
    lines: list[str] = []
    for idx, row in enumerate(claim_plan, start=1):
        lines.append(f"{idx}. {row['claim']} [{idx}]")
        citations.append(
            {
                "chunk_id": row.get("chunk_id", ""),
                "paper_id": row.get("paper_id", "unknown-paper"),
                "section_page": row.get("section_page", ""),
            }
        )
    answer = (
        "基于可追溯证据的结论（claim -> citation）：\n"
        + "\n".join(lines)
        + "\n\n如需更完整答案，我可以按你指定的子问题继续展开。"
    )
    return answer, citations


def _bind_claim_plan_to_citations(
    *,
    claim_plan: list[dict[str, str]],
    answer: str,
    answer_citations: list[dict[str, Any]],
    evidence_grouped: list[dict[str, Any]],
    min_bind_ratio: float = 0.6,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    report: dict[str, Any] = {
        "enabled": bool(claim_plan),
        "claim_count": len(claim_plan),
        "bound_claim_count": 0,
        "binding_ratio": 0.0,
        "missing_claim_chunk_ids": [],
        "claim_binding_mode": "chunk",
        "fallback_to_staged": False,
        "fallback_reason": None,
    }
    if not claim_plan:
        return answer, answer_citations, report

    evidence_lookup = _build_evidence_lookup(evidence_grouped)
    normalized_citations = _normalize_citations(answer_citations, evidence_lookup)
    citation_chunk_ids = {str(row.get("chunk_id", "")).strip() for row in normalized_citations}
    claim_chunk_ids = [str(row.get("chunk_id", "")).strip() for row in claim_plan if str(row.get("chunk_id", "")).strip()]

    bound_claim_count = sum(1 for cid in claim_chunk_ids if cid in citation_chunk_ids)
    missing_claims = [cid for cid in claim_chunk_ids if cid not in citation_chunk_ids]
    claim_count = len(claim_chunk_ids)
    binding_ratio = (bound_claim_count / claim_count) if claim_count > 0 else 1.0

    report["bound_claim_count"] = int(bound_claim_count)
    report["binding_ratio"] = round(float(binding_ratio), 4)
    report["missing_claim_chunk_ids"] = missing_claims
    if any(str(row.get("section_id", "")).strip() for row in claim_plan):
        report["claim_binding_mode"] = "claim_with_section"

    if not normalized_citations or binding_ratio < float(min_bind_ratio):
        staged_answer, staged_citations = _render_claim_bound_answer(claim_plan)
        report["fallback_to_staged"] = True
        report["fallback_reason"] = "claim_binding_insufficient"
        return staged_answer, staged_citations, report

    return answer, normalized_citations, report


def _rewrite_candidate_metrics(
    *,
    query: str,
    mode: str,
    top_k: int,
    bm25_index: dict[str, Any],
    vec_index: Any,
    embed_index: Any,
    embed_index_path: str | None,
    config: Any,
) -> dict[str, Any]:
    runtime_metrics: dict[str, Any] = {}
    candidates = retrieve_candidates(
        query,
        mode=mode,
        top_k=top_k,
        bm25_index=bm25_index,
        vec_index=vec_index,
        embed_index=embed_index,
        embed_index_path=embed_index_path,
        config=config,
        runtime_metrics=runtime_metrics,
    )
    if not candidates:
        return {
            "query": query,
            "candidate_count": 0,
            "retrieval_quality": 0.0,
            "rerank_margin": 0.0,
            "citation_coverage": 0.0,
            "final_score": 0.0,
        }

    if bool(getattr(config.rerank, "enabled", True)):
        rerank_outcome = rerank_candidates(query=query, candidates=candidates, config=config)
        ranked = rerank_outcome.candidates
    else:
        ranked = list(candidates)

    retrieval_scores = [float((row.payload or {}).get("score_retrieval", row.score)) for row in ranked[:5]]
    retrieval_quality = sum(retrieval_scores) / max(1, len(retrieval_scores))
    retrieval_quality = max(0.0, min(1.0, retrieval_quality))

    rerank_scores = [float((row.payload or {}).get("score_rerank", row.score)) for row in ranked[:5]]
    rerank_margin = (
        max(0.0, rerank_scores[0] - rerank_scores[1]) if len(rerank_scores) >= 2 else (rerank_scores[0] if rerank_scores else 0.0)
    )
    rerank_margin = max(0.0, min(1.0, rerank_margin))

    valid_citations = [row for row in ranked[:5] if str(row.chunk_id or "").strip()]
    citation_coverage = len(valid_citations) / max(1, min(5, len(ranked)))
    citation_coverage = max(0.0, min(1.0, citation_coverage))

    final_score = 0.45 * retrieval_quality + 0.35 * rerank_margin + 0.20 * citation_coverage
    return {
        "query": query,
        "candidate_count": len(candidates),
        "retrieval_quality": round(retrieval_quality, 4),
        "rerank_margin": round(rerank_margin, 4),
        "citation_coverage": round(citation_coverage, 4),
        "final_score": round(final_score, 4),
    }


def _split_sentences(text: str) -> list[str]:
    raw = " ".join((text or "").split())
    if not raw:
        return []
    parts = re.split(r"(?:[。！？!?]+|\.(?:\s+|$)|\n+)", raw)
    return [p.strip() for p in parts if p.strip()]


def _extract_numbers(text: str) -> set[str]:
    cleaned = _strip_format_markers(text)
    cleaned = re.sub(r"\b[a-zA-Z0-9]+:\d+\b", " ", cleaned or "")
    cleaned = re.sub(r"\bp\d+\b", " ", cleaned, flags=re.IGNORECASE)
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", cleaned))


def _strip_format_markers(text: str) -> str:
    cleaned = str(text or "")
    for pattern in FORMAT_NUMBER_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = FORMAT_LOCATOR_RE.sub(" ", cleaned)
    return cleaned


def _tokenize_for_matching(text: str) -> set[str]:
    lowered = (text or "").lower()
    chunks = re.findall(r"[a-z0-9\u4e00-\u9fff]+", lowered)
    tokens: set[str] = set()
    for chunk in chunks:
        # Split token boundaries across latin letters / digits / CJK blocks.
        parts = re.findall(r"[a-z]+|[0-9]+|[\u4e00-\u9fff]+", chunk)
        for part in parts:
            if len(part) <= 1 or part in CLAIM_STOPWORDS:
                continue
            tokens.add(part)
    return tokens


def _claim_types(sentence: str) -> set[str]:
    normalized_sentence = _strip_format_markers(sentence)
    lowered = normalized_sentence.lower()
    tags: set[str] = set()
    if any(term in lowered for term in CLAIM_UNCERTAINTY_TERMS):
        return tags
    if _extract_numbers(normalized_sentence):
        tags.add("numeric")
    if any(term in lowered for term in CLAIM_EXPERIMENT_TERMS):
        tags.add("experiment")
    if any(term in lowered for term in CLAIM_DEFINITION_TERMS):
        tags.add("definition")
    if any(term in lowered for term in CLAIM_CONCLUSION_TERMS):
        tags.add("conclusion")
    return tags


def _is_format_locator_sentence(sentence: str) -> bool:
    raw = str(sentence or "").strip()
    if not raw:
        return True
    if not FORMAT_LOCATOR_SENTENCE_RE.search(raw):
        return False
    normalized = _strip_format_markers(raw)
    normalized = FORMAT_LOCATOR_RE.sub(" ", normalized)
    normalized = " ".join(normalized.split()).strip(" ,.;:()[]")
    if not normalized:
        return True
    if normalized.isdigit():
        return True
    if normalized in {"overview only", "详见", "介绍实验设置，详见", "介绍实验设置"}:
        return True
    return False


def _extract_key_claims(answer: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for sentence in _split_sentences(answer):
        if _is_format_locator_sentence(sentence):
            continue
        normalized = _strip_format_markers(sentence).strip()
        if not normalized or normalized.isdigit():
            continue
        tags = _claim_types(normalized)
        if not tags:
            continue
        claims.append({"text": normalized, "types": sorted(tags)})
    return claims


def _build_evidence_lookup(evidence_grouped: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for group in evidence_grouped:
        paper_id = group.get("paper_id", "unknown-paper")
        for item in group.get("evidence", []):
            chunk_id = str(item.get("chunk_id", "")).strip()
            if not chunk_id:
                continue
            lookup[chunk_id] = {
                "chunk_id": chunk_id,
                "paper_id": str(item.get("paper_id", paper_id) or paper_id),
                "section_page": str(item.get("section_page", "")),
                "section_id": str(item.get("section_id", "")),
                "quote": str(item.get("quote", "")),
                "block_type": str(item.get("block_type", "")),
                "structure_provenance": item.get("structure_provenance"),
            }
    return lookup


def _normalize_citations(
    answer_citations: list[dict[str, Any]],
    evidence_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for citation in answer_citations:
        if not isinstance(citation, dict):
            continue
        chunk_id = str(citation.get("chunk_id", "")).strip()
        if not chunk_id:
            continue
        evidence_item = evidence_lookup.get(chunk_id, {})
        paper_id = str(citation.get("paper_id", "")).strip() or str(evidence_item.get("paper_id", "unknown-paper"))
        section_page = str(citation.get("section_page", "")).strip() or str(evidence_item.get("section_page", ""))
        row = {"chunk_id": chunk_id, "paper_id": paper_id, "section_page": section_page}
        block_type = str(citation.get("block_type", "")).strip() or str(evidence_item.get("block_type", "")).strip()
        if block_type:
            row["block_type"] = block_type
        structure_provenance = citation.get("structure_provenance")
        if not isinstance(structure_provenance, dict):
            structure_provenance = evidence_item.get("structure_provenance")
        if isinstance(structure_provenance, dict) and structure_provenance:
            row["structure_provenance"] = structure_provenance
        key = (row["chunk_id"], row["paper_id"], row["section_page"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(row)
    return normalized


def _is_claim_supported_by_evidence(claim_text: str, evidence_text: str) -> bool:
    if not evidence_text.strip():
        return False
    claim_numbers = _extract_numbers(claim_text)
    evidence_numbers = _extract_numbers(evidence_text)
    if claim_numbers and not claim_numbers.intersection(evidence_numbers):
        return False

    claim_tokens = _tokenize_for_matching(claim_text)
    evidence_tokens = _tokenize_for_matching(evidence_text)
    overlap = claim_tokens.intersection(evidence_tokens)
    min_overlap = 1 if len(claim_tokens) < 4 else 2
    return len(overlap) >= min_overlap


def _m8_weak_answer(question: str, source: str = "sufficiency_gate") -> str:
    source_label = "Sufficiency Gate"
    if source == "evidence_policy_gate":
        source_label = "Evidence Policy Gate"
    return (
        f"当前回答中的关键结论缺少可追溯证据，已触发 {source_label}。"
        f"请补充更具体线索后重试：{question}"
    )


def _apply_evidence_policy_gate(
    *,
    question: str,
    answer: str,
    answer_citations: list[dict[str, Any]],
    evidence_grouped: list[dict[str, Any]],
    output_warnings: list[str],
    policy_enforced: bool,
    claim_binding_report: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    evidence_lookup = _build_evidence_lookup(evidence_grouped)
    normalized_citations = _normalize_citations(answer_citations, evidence_lookup)
    claims = _extract_key_claims(answer)
    gate_report: dict[str, Any] = {
        "enabled": bool(policy_enforced),
        "claim_count": len(claims),
        "failed_claims": [],
        "claim_binding_mode": str((claim_binding_report or {}).get("claim_binding_mode", "text_fallback")),
        "constraints_envelope": None,
    }
    if not policy_enforced or not claims:
        return answer, normalized_citations, gate_report
    if (
        claim_binding_report
        and int(claim_binding_report.get("claim_count", 0) or 0) > 0
        and int(claim_binding_report.get("bound_claim_count", 0) or 0) >= int(claim_binding_report.get("claim_count", 0) or 0)
    ):
        gate_report["triggered"] = False
        gate_report["checked_via"] = "claim_binding"
        return answer, normalized_citations, gate_report

    for claim in claims:
        supported = False
        for citation in normalized_citations:
            evidence = evidence_lookup.get(citation.get("chunk_id", ""))
            if evidence is None:
                continue
            if _is_claim_supported_by_evidence(claim["text"], evidence.get("quote", "")):
                supported = True
                break
        if not supported:
            gate_report["failed_claims"].append(claim)

    if gate_report["failed_claims"]:
        if "insufficient_evidence_for_answer" not in output_warnings:
            output_warnings.append("insufficient_evidence_for_answer")
        gate_report["triggered"] = True
        gate_report["constraints_envelope"] = build_constraint_envelope(
            constraint_type="citation_legality",
            reason_code="evidence_policy_gate_claim_not_supported",
            severity="high",
            retryable=True,
            blocking_scope="final_answer",
            user_safe_summary="关键结论缺少可追溯证据，当前回答不能直接向用户输出。",
            evidence_snapshot={"failed_claim_count": len(gate_report["failed_claims"])},
            citation_status="claim_not_supported",
            suggested_next_actions=["补充更具体的问题线索，或缩小到已有证据支持的结论。"],
            guardrail_blocked=True,
        )
        return answer, [], gate_report

    gate_report["triggered"] = False
    gate_report["checked_via"] = "text_fallback"
    return answer, normalized_citations, gate_report


def _is_insufficient_evidence(
    evidence_grouped: list[dict[str, Any]],
    *,
    min_evidence: int = 2,
) -> bool:
    flat = _flatten_evidence(evidence_grouped)
    if len(flat) < min_evidence:
        return True
    noisy_only = all((item.get("content_type", "body") or "body").lower() in NOISY_CONTENT_TYPES for item in flat)
    return noisy_only


def _collect_evidence_text(evidence_grouped: list[dict[str, Any]]) -> str:
    segments: list[str] = []
    for group in evidence_grouped:
        title = str(group.get("paper_title", "")).strip()
        if title:
            segments.append(title)
        for item in group.get("evidence", []):
            quote = str(item.get("quote", "")).strip()
            if quote:
                segments.append(quote)
    return " ".join(segments)


def is_open_summary_intent(question: str) -> bool:
    lowered = (question or "").lower()
    if not lowered.strip():
        return False
    return any(term in lowered for term in OPEN_SUMMARY_TERMS)


def _derive_topic_anchors(query: str, *, max_terms: int = 8) -> list[str]:
    anchors: list[str] = []
    for tok in sorted(_tokenize_for_matching(query), key=len, reverse=True):
        val = str(tok).strip()
        if not val:
            continue
        if val not in anchors:
            anchors.append(val)
        if re.search(r"[\u4e00-\u9fff]", val) and len(val) >= 4:
            for n in (4, 3, 2):
                for i in range(0, max(0, len(val) - n + 1)):
                    gram = val[i : i + n]
                    if gram not in anchors:
                        anchors.append(gram)
                    if len(anchors) >= max_terms:
                        break
                if len(anchors) >= max_terms:
                    break
        if len(anchors) >= max_terms:
            break
    return anchors


def _is_clarify_like_turn(decision: str) -> bool:
    normalized = str(decision or "").strip()
    return normalized in {"clarify", "need_scope_clarification"}


def _topic_overlap(current_anchors: list[str], turn_anchors: list[str]) -> bool:
    if not current_anchors or not turn_anchors:
        return False
    current_set = {x.lower() for x in current_anchors if str(x).strip()}
    turn_set = {x.lower() for x in turn_anchors if str(x).strip()}
    if not current_set or not turn_set:
        return False
    if current_set.intersection(turn_set):
        return True
    for cur in current_set:
        for prev in turn_set:
            if len(cur) >= 4 and len(prev) >= 4 and (cur in prev or prev in cur):
                return True
    return False


def _compute_same_topic_clarify_streak(
    history_turns: list[dict[str, Any]],
    current_topic_anchors: list[str],
) -> tuple[int, bool]:
    if not history_turns:
        return 0, False
    streak = 0
    topic_switched = False
    for idx, turn in enumerate(reversed(history_turns)):
        if not isinstance(turn, dict):
            continue
        if str(turn.get("turn_type", "")).strip() in {"summary_memory", "semantic_recall_memory"}:
            continue
        turn_anchors_raw = turn.get("topic_anchors", [])
        turn_anchors = [str(x).strip() for x in turn_anchors_raw if str(x).strip()] if isinstance(turn_anchors_raw, list) else []
        if not turn_anchors:
            turn_anchors = _derive_topic_anchors(str(turn.get("standalone_query", "")))
        if current_topic_anchors and turn_anchors and not _topic_overlap(current_topic_anchors, turn_anchors):
            if idx == 0:
                topic_switched = True
            break
        if _is_clarify_like_turn(str(turn.get("decision", ""))):
            streak += 1
            continue
        break
    return streak, topic_switched


def _build_assistant_summary_answer(
    *,
    question: str,
    evidence_grouped: list[dict[str, Any]],
    min_topics: int = 3,
    low_confidence_note: bool = False,
) -> tuple[str, list[dict[str, Any]], list[str], bool]:
    citations: list[dict[str, Any]] = []
    topic_lines: list[str] = []
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            chunk_id = str(item.get("chunk_id", "")).strip()
            if not chunk_id:
                continue
            citation_idx = len(citations) + 1
            quote = _normalize_spaces(str(item.get("quote", "")))
            quote = quote[:120] + ("..." if len(quote) > 120 else "")
            paper_id = str(group.get("paper_id", ""))
            section_page = str(item.get("section_page", "N/A"))
            citations.append(
                {
                    "chunk_id": chunk_id,
                    "paper_id": paper_id,
                    "section_page": section_page,
                    "block_type": str(item.get("block_type", "")),
                    "structure_provenance": item.get("structure_provenance"),
                }
            )
            paper_title = str(group.get("paper_title") or paper_id or "unknown")
            topic_lines.append(f"{citation_idx}. {paper_title}：{quote} [{citation_idx}]")
            if len(citations) >= 5:
                break
        if len(citations) >= 5:
            break

    min_topics = max(1, int(min_topics))
    if len(topic_lines) < min_topics:
        return (
            "",
            [],
            [],
            False,
        )

    suggestions = [
        "这些方向中哪个与你当前任务最相关？我可以展开细节。",
        "要先对比不同论文的方法差异，还是先看证据最强的实验结论？",
        f"如果你愿意，我可以基于“{question[:24]}”继续细化成可执行检索问题。",
    ][:3]
    prefix = "基于当前可追溯证据，优先可关注这些主题："
    if low_confidence_note:
        prefix = "以下为低置信度主题草图（基于当前有限证据，建议继续验证）："
    answer = prefix + "\n" + "\n".join(topic_lines[:5]) + "\n\n建议下一步追问：\n" + "\n".join(
        f"{idx+1}. {q}" for idx, q in enumerate(suggestions)
    )
    return answer, citations, suggestions, True


def run_sufficiency_gate(
    *,
    question: str,
    query_used: str | None = None,
    topic_query_source: str = "user_query",
    topic_query_text: str | None = None,
    open_summary_intent: bool = False,
    scope_mode: str,
    evidence_grouped: list[dict[str, Any]],
    config: Any,
    clarify_count_for_topic: int = 0,
    clarify_limit: int = 2,
    force_partial_answer_on_limit: bool = True,
) -> dict[str, Any]:
    return run_sufficiency_gate_impl(
        question=question,
        query_used=query_used,
        topic_query_source=topic_query_source,
        topic_query_text=topic_query_text,
        open_summary_intent=open_summary_intent,
        scope_mode=scope_mode,
        evidence_grouped=evidence_grouped,
        config=config,
        clarify_count_for_topic=clarify_count_for_topic,
        clarify_limit=clarify_limit,
        force_partial_answer_on_limit=force_partial_answer_on_limit,
    )


def _strip_json_code_fence(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return raw


def _extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"```([a-zA-Z0-9_-]*)\s*\n(.*?)```", re.DOTALL)
    blocks: list[tuple[str, str]] = []
    for match in pattern.finditer(text or ""):
        lang = str(match.group(1) or "").strip().lower()
        body = str(match.group(2) or "").strip()
        if body:
            blocks.append((lang, body))
    return blocks


def _parse_answer_dict(payload: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    answer = str(payload.get("answer", "")).strip()
    if not answer:
        # Allow alternative structured formats.
        conclusion = str(payload.get("conclusion", "")).strip()
        evidence = str(payload.get("evidence", "")).strip()
        uncertainty = str(payload.get("uncertainty", "")).strip()
        parts = []
        if conclusion:
            parts.append(f"Conclusion:\n{conclusion}")
        if evidence:
            parts.append(f"Evidence:\n{evidence}")
        if uncertainty:
            parts.append(f"Uncertainty:\n{uncertainty}")
        answer = "\n\n".join(parts).strip()

    citations_raw = payload.get("answer_citations", [])
    if citations_raw is None:
        citations_raw = []
    normalized: list[dict[str, Any]] = []
    if isinstance(citations_raw, list):
        for row in citations_raw:
            if not isinstance(row, dict):
                continue
            normalized_row: dict[str, Any] = {
                "chunk_id": str(row.get("chunk_id", "")).strip(),
                "paper_id": str(row.get("paper_id", "")).strip(),
                "section_page": str(row.get("section_page", "")).strip(),
            }
            block_type = str(row.get("block_type", "")).strip()
            if block_type:
                normalized_row["block_type"] = block_type
            structure_provenance = row.get("structure_provenance")
            if isinstance(structure_provenance, dict) and structure_provenance:
                normalized_row["structure_provenance"] = structure_provenance
            normalized.append(normalized_row)
    return (answer or None), normalized


def _try_parse_structured_payload(raw: str) -> tuple[str | None, list[dict[str, Any]] | None]:
    candidates: list[str] = []
    base = raw.strip()
    if base:
        candidates.append(base)
    stripped = _strip_json_code_fence(base)
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    for _, body in _extract_fenced_blocks(base):
        if body not in candidates:
            candidates.append(body)

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            answer, citations = _parse_answer_dict(payload)
            if answer:
                return answer, citations

        try:
            yaml_payload = yaml.safe_load(candidate)
        except Exception:
            yaml_payload = None
        if isinstance(yaml_payload, dict):
            answer, citations = _parse_answer_dict(yaml_payload)
            if answer:
                return answer, citations

    return None, None


def _normalize_unstructured_answer(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    # Prefer fenced markdown/html/yaml body over fence wrapper.
    blocks = _extract_fenced_blocks(text)
    if blocks:
        # Use first non-empty block body.
        text = blocks[0][1].strip()

    # HTML to text.
    if "<" in text and ">" in text:
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)

    text = text.strip()
    return text or None


def _build_llm_answer_prompt(
    *,
    question: str,
    scope_mode: str,
    output_warnings: list[str],
    history_brief: str,
    claim_plan: list[dict[str, str]],
) -> str:
    payload = {
        "question": question,
        "scope_mode": scope_mode,
        "output_warnings": output_warnings,
        "history_brief_style_only": history_brief,
        "claim_plan": claim_plan,
    }
    return (
        "Use ONLY the evidence provided in ContextPayload to answer the question. "
        "First align with claim_plan, then render readable answer with conclusion/evidence/uncertainty boundary. "
        "Do not add any fact outside the provided evidence and chat history context. "
        "Return strict JSON with keys: answer, answer_citations. "
        "answer_citations must be a list of objects with chunk_id, paper_id, section_page.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _answer_warning_from_reason(reason: str | None) -> str:
    mapping = {
        "timeout": "llm_answer_timeout_fallback_to_template",
        "rate_limit": "llm_answer_rate_limit_fallback_to_template",
        "empty_response": "llm_answer_empty_response_fallback_to_template",
        "missing_api_key": "llm_answer_missing_api_key_fallback_to_template",
        "stream_first_token_timeout": "llm_answer_first_token_timeout_fallback_to_template",
        "stream_interrupted": "llm_answer_stream_interrupted_fallback_to_template",
        "stream_empty": "llm_answer_stream_empty_response_fallback_to_template",
    }
    return mapping.get(reason or "", "llm_answer_error_fallback_to_template")


def _build_answer_llm_diag(
    *,
    config: Any,
    reason: str,
    warning: str,
    status_code: int | None = None,
    attempts_used: int = 0,
    max_retries: int = 0,
    elapsed_ms: int = 0,
    timestamp: str | None = None,
    provider_used: str | None = None,
    model_used: str | None = None,
    fallback_reason: str | None = None,
    error_category: str | None = None,
) -> dict[str, Any]:
    return build_llm_diagnostics(
        stage="answer",
        provider=config.answer_llm_provider,
        model=config.answer_llm_model,
        reason=reason,
        fallback_warning=warning,
        status_code=status_code,
        attempts_used=attempts_used,
        max_retries=max_retries,
        elapsed_ms=elapsed_ms,
        timestamp=timestamp,
        provider_used=provider_used,
        model_used=model_used,
        fallback_reason=fallback_reason,
        error_category=error_category,
    )


def _parse_answer_payload(
    *,
    content: str,
) -> tuple[str | None, list[dict[str, Any]] | None, str | None]:
    raw = (content or "").strip()
    answer, citations = _try_parse_structured_payload(raw)
    if answer is not None and citations is not None:
        return answer, citations, None

    fallback_text = _normalize_unstructured_answer(raw)
    if fallback_text:
        return fallback_text, [], None
    return None, None, "llm_answer_invalid_payload_fallback_to_template"


def _try_llm_answer_with_evidence(
    *,
    question: str,
    scope_mode: str,
    evidence_grouped: list[dict[str, Any]],
    output_warnings: list[str],
    config: Any,
    history_turns: list[dict[str, Any]],
    on_stream_delta: Callable[[str], None] | None = None,
) -> tuple[
    str | None,
    list[dict[str, Any]] | None,
    str | None,
    dict[str, Any] | None,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    claim_plan: list[dict[str, str]] = []
    stream_observation = {
        "answer_stream_enabled": bool(getattr(config, "answer_stream_enabled", False)),
        "answer_stream_used": False,
        "answer_stream_first_token_ms": None,
        "answer_stream_fallback_reason": None,
        "answer_stream_events": [],
        "claim_binding": {
            "enabled": False,
            "claim_count": 0,
            "bound_claim_count": 0,
            "binding_ratio": 0.0,
            "missing_claim_chunk_ids": [],
            "claim_binding_mode": "chunk",
            "fallback_to_staged": False,
            "fallback_reason": None,
        },
    }
    context_budget: dict[str, Any] = {
        "prompt_tokens_est": 0,
        "discarded_evidence": [],
        "discarded_evidence_count": 0,
        "history_trimmed_turns": 0,
        "context_overflow_fallback": False,
    }
    if not config.answer_use_llm:
        return None, None, "llm_answer_disabled", None, stream_observation, context_budget, claim_plan
    if not config.llm_fallback_enabled:
        warning = "llm_fallback_disabled_skip_llm_answer"
        stream_observation["answer_stream_fallback_reason"] = warning
        return (
            None,
            None,
            warning,
            _build_answer_llm_diag(
                config=config,
                reason="fallback_disabled",
                warning=warning,
                attempts_used=0,
                max_retries=config.llm_max_retries,
                elapsed_ms=0,
                fallback_reason="fallback_disabled",
            ),
            stream_observation,
            context_budget,
            claim_plan,
        )
    policy = build_stage_policy(config, stage="answer")
    api_key = policy.primary.resolve_api_key()
    if not api_key and not policy.fallback:
        warning = "llm_answer_missing_api_key_fallback_to_template"
        stream_observation["answer_stream_fallback_reason"] = warning
        return (
            None,
            None,
            warning,
            _build_answer_llm_diag(
                config=config,
                reason="missing_api_key",
                warning=warning,
                attempts_used=0,
                max_retries=config.llm_max_retries,
                elapsed_ms=0,
                fallback_reason="missing_api_key",
            ),
            stream_observation,
            context_budget,
            claim_plan,
        )
    system_prompt = (
        "You are a strict evidence-grounded QA assistant. "
        "Only answer with the provided evidence. "
        "If evidence is insufficient, state uncertainty and keep citations empty."
    )
    claim_plan = _build_claim_plan(evidence_grouped, max_claims=5)
    base_user_prompt = _build_llm_answer_prompt(
        question=question,
        scope_mode=scope_mode,
        output_warnings=output_warnings,
        history_brief=build_history_brief(history_turns),
        claim_plan=claim_plan,
    )
    assembly: ContextAssemblyResult = assemble_prompt_with_budget(
        system_prompt=system_prompt,
        user_prompt=base_user_prompt,
        chat_history=history_turns,
        evidence_grouped=evidence_grouped,
        max_context_tokens=int(getattr(config, "max_context_tokens", 6000)),
    )
    context_budget = {
        "prompt_tokens_est": int(assembly.prompt_tokens_est),
        "discarded_evidence": list(assembly.discarded_evidence),
        "discarded_evidence_count": len(assembly.discarded_evidence),
        "history_trimmed_turns": int(assembly.history_trimmed_turns),
        "context_overflow_fallback": bool(assembly.context_overflow_fallback),
    }
    if assembly.context_overflow_fallback:
        warning = "context_overflow_fallback"
        stream_observation["answer_stream_fallback_reason"] = warning
        return None, None, warning, None, stream_observation, context_budget, claim_plan
    user_prompt = assembly.assembled_prompt

    use_stream = bool(getattr(config, "answer_stream_enabled", False))
    timeout_ms = int(getattr(config, "answer_llm_timeout_ms", config.llm_timeout_ms))
    if use_stream:
        stream_observation["answer_stream_used"] = True
        result = call_chat_completion_stream(
            provider=policy.primary.provider,
            model=policy.primary.model,
            api_key=api_key,
            api_base=policy.primary.api_base,
            fallback_provider=(policy.fallback.provider if policy.fallback else None),
            fallback_model=(policy.fallback.model if policy.fallback else None),
            fallback_api_key=(policy.fallback.resolve_api_key() if policy.fallback else None),
            fallback_api_base=(policy.fallback.api_base if policy.fallback else None),
            router_retry=policy.max_retries,
            router_cooldown_sec=policy.cooldown_seconds,
            router_failure_threshold=policy.failure_threshold,
            use_litellm_sdk=policy.use_litellm_sdk,
            use_legacy_client=policy.use_legacy_client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_ms=timeout_ms,
            max_retries=config.llm_max_retries,
            temperature=0.0,
            on_delta=on_stream_delta,
            debug_stage="answer",
        )
    else:
        result = call_chat_completion(
            provider=policy.primary.provider,
            model=policy.primary.model,
            api_key=api_key,
            api_base=policy.primary.api_base,
            fallback_provider=(policy.fallback.provider if policy.fallback else None),
            fallback_model=(policy.fallback.model if policy.fallback else None),
            fallback_api_key=(policy.fallback.resolve_api_key() if policy.fallback else None),
            fallback_api_base=(policy.fallback.api_base if policy.fallback else None),
            router_retry=policy.max_retries,
            router_cooldown_sec=policy.cooldown_seconds,
            router_failure_threshold=policy.failure_threshold,
            use_litellm_sdk=policy.use_litellm_sdk,
            use_legacy_client=policy.use_legacy_client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_ms=timeout_ms,
            max_retries=config.llm_max_retries,
            temperature=0.0,
            debug_stage="answer",
        )

    first_token_latency = getattr(result, "first_token_latency_ms", None)
    if first_token_latency is not None:
        stream_observation["answer_stream_first_token_ms"] = int(first_token_latency)
    stream_events = getattr(result, "stream_events", None)
    if isinstance(stream_events, list):
        stream_observation["answer_stream_events"] = stream_events[:32]
    if not result.ok:
        warning = _answer_warning_from_reason(result.reason)
        stream_observation["answer_stream_fallback_reason"] = warning
        return (
            None,
            None,
            warning,
            _build_answer_llm_diag(
                config=config,
                reason=str(result.reason or "unknown_error"),
                warning=warning,
                status_code=getattr(result, "status_code", None),
                attempts_used=getattr(result, "attempts_used", 0),
                max_retries=getattr(result, "max_retries", config.llm_max_retries),
                elapsed_ms=getattr(result, "elapsed_ms", 0),
                timestamp=getattr(result, "timestamp", None),
                provider_used=getattr(result, "provider_used", None),
                model_used=getattr(result, "model_used", None),
                fallback_reason=getattr(result, "fallback_reason", None) or str(result.reason or ""),
                error_category=getattr(result, "error_category", None)
                or classify_error_category(getattr(result, "reason", None), getattr(result, "status_code", None)),
            ),
            stream_observation,
            context_budget,
            claim_plan,
        )

    answer, normalized, warning = _parse_answer_payload(content=result.content or "")
    if warning is not None:
        stream_observation["answer_stream_fallback_reason"] = warning
        return (
            None,
            None,
            warning,
            _build_answer_llm_diag(
                config=config,
                reason="invalid_json" if warning == "llm_answer_invalid_json_fallback_to_template" else "invalid_payload",
                warning=warning,
                status_code=getattr(result, "status_code", None),
                attempts_used=getattr(result, "attempts_used", 0),
                max_retries=getattr(result, "max_retries", config.llm_max_retries),
                elapsed_ms=getattr(result, "elapsed_ms", 0),
                timestamp=getattr(result, "timestamp", None),
                provider_used=getattr(result, "provider_used", None),
                model_used=getattr(result, "model_used", None),
                fallback_reason=getattr(result, "fallback_reason", None) or str(warning),
                error_category="other",
            ),
            stream_observation,
            context_budget,
            claim_plan,
        )
    return answer, normalized, None, None, stream_observation, context_budget, claim_plan


def _build_answer(
    question: str,
    scope_mode: str,
    scope_reason: dict[str, Any],
    evidence_grouped: list[dict[str, Any]],
    output_warnings: list[str],
    config: Any,
    history_turns: list[dict[str, Any]],
    on_stream_delta: Callable[[str], None] | None = None,
) -> tuple[str, list[dict[str, Any]], bool, bool, dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    stream_observation = {
        "answer_stream_enabled": bool(getattr(config, "answer_stream_enabled", False)),
        "answer_stream_used": False,
        "answer_stream_first_token_ms": None,
        "answer_stream_fallback_reason": None,
        "answer_stream_events": [],
        "claim_binding": {
            "enabled": False,
            "claim_count": 0,
            "bound_claim_count": 0,
            "binding_ratio": 0.0,
            "missing_claim_chunk_ids": [],
            "claim_binding_mode": "chunk",
            "fallback_to_staged": False,
            "fallback_reason": None,
        },
    }
    if scope_mode == "clarify_scope":
        return (
            "请先指定具体论文（标题/作者/年份/会议），我再基于该论文给出证据化回答。",
            [],
            False,
            False,
            None,
            stream_observation,
            {
                "prompt_tokens_est": 0,
                "discarded_evidence": [],
                "discarded_evidence_count": 0,
                "history_trimmed_turns": 0,
                "context_overflow_fallback": False,
            },
        )

    has_paper_clue = bool(scope_reason.get("has_paper_clue"))
    if not has_paper_clue and _is_insufficient_evidence(evidence_grouped):
        if "insufficient_evidence_for_answer" not in output_warnings:
            output_warnings.append("insufficient_evidence_for_answer")
        return (
            "当前问题未指定具体论文，且检索到的证据不足以归纳出可靠结论。"
            "请提供论文标题/作者/年份，或描述研究主题关键词。",
            [],
            False,
            False,
            None,
            stream_observation,
            {
                "prompt_tokens_est": 0,
                "discarded_evidence": [],
                "discarded_evidence_count": 0,
                "history_trimmed_turns": 0,
                "context_overflow_fallback": False,
            },
        )

    llm_answer, llm_citations, llm_error, llm_diagnostics, stream_observation, context_budget, claim_plan = _try_llm_answer_with_evidence(
        question=question,
        scope_mode=scope_mode,
        evidence_grouped=evidence_grouped,
        output_warnings=output_warnings,
        config=config,
        history_turns=history_turns,
        on_stream_delta=on_stream_delta,
    )
    staged_answer, staged_citations = _render_claim_bound_answer(claim_plan)
    if llm_error == "context_overflow_fallback":
        if llm_error not in output_warnings:
            output_warnings.append(llm_error)
        return (
            staged_answer,
            staged_citations,
            False,
            True,
            None,
            stream_observation,
            context_budget,
        )
    if llm_answer is not None and llm_citations is not None:
        bound_answer, bound_citations, claim_binding_report = _bind_claim_plan_to_citations(
            claim_plan=claim_plan,
            answer=llm_answer,
            answer_citations=llm_citations,
            evidence_grouped=evidence_grouped,
        )
        stream_observation["claim_binding"] = claim_binding_report
        if bool(claim_binding_report.get("fallback_to_staged")):
            warning = str(claim_binding_report.get("fallback_reason") or "claim_binding_insufficient")
            if warning and warning not in output_warnings:
                output_warnings.append(warning)
            if "claim_binding_fallback_to_staged" not in output_warnings:
                output_warnings.append("claim_binding_fallback_to_staged")
        return bound_answer, bound_citations, True, False, None, stream_observation, context_budget
    if llm_error and llm_error != "llm_answer_disabled":
        output_warnings.append(llm_error)
    if staged_citations:
        stream_observation["claim_binding"] = {
            "enabled": True,
            "claim_count": len(claim_plan),
            "bound_claim_count": len(staged_citations),
            "binding_ratio": 1.0 if claim_plan else 0.0,
            "missing_claim_chunk_ids": [],
            "claim_binding_mode": ("claim_with_section" if any(str(row.get("section_id", "")).strip() for row in claim_plan) else "chunk"),
            "fallback_to_staged": True,
            "fallback_reason": "llm_unavailable_use_staged_claims",
        }
        return (
            staged_answer,
            staged_citations,
            False,
            bool(llm_error),
            llm_diagnostics,
            stream_observation,
            context_budget,
        )

    if scope_mode == "rewrite_scope":
        groups_with_evidence = [g for g in evidence_grouped if g.get("evidence")]
        if len(groups_with_evidence) >= 2:
            g1, g2 = groups_with_evidence[0], groups_with_evidence[1]
            c1 = g1["evidence"][0]["chunk_id"]
            c2 = g2["evidence"][0]["chunk_id"]
            answer = (
                "未指定具体论文，以下为知识库相关论文的综合证据。"
                f"跨论文看，问题“{question}”在 {g1['paper_title']} 与 {g2['paper_title']} 中均有直接证据支持。"
                f"代表性证据来自 {c1} 与 {c2}。"
            )
            citations = _build_answer_citations([g1, g2])
            return answer, citations, False, bool(llm_error), llm_diagnostics, stream_observation, context_budget

        only_group = groups_with_evidence[0]
        chunk_id = only_group["evidence"][0]["chunk_id"]
        answer = (
            "未指定具体论文，以下为知识库相关论文的综合证据。"
            f"当前可用证据主要来自 {only_group['paper_title']}（{chunk_id}），"
            "建议补充标题/作者/年份以获得更稳定的跨论文比较。"
        )
        return (
            answer,
            _build_answer_citations([only_group]),
            False,
            bool(llm_error),
            llm_diagnostics,
            stream_observation,
            context_budget,
        )

    if has_paper_clue:
        first_group = next((g for g in evidence_grouped if g.get("evidence")), None)
        if first_group is None:
            output_warnings.append("insufficient_evidence_for_answer")
            return (
                "检索未找到足够单论文证据，请提供更明确论文线索。",
                [],
                False,
                bool(llm_error),
                llm_diagnostics,
                stream_observation,
                context_budget,
            )
        first_item = first_group["evidence"][0]
        answer = (
            f"基于 {first_group['paper_title']} 的证据，问题“{question}”可由该论文内容直接回答。"
            f"关键证据见 {first_item['chunk_id']}。"
        )
        return (
            answer,
            _build_answer_citations([first_group]),
            False,
            bool(llm_error),
            llm_diagnostics,
            stream_observation,
            context_budget,
        )

    evidence_flat = _flatten_evidence(evidence_grouped)
    answer = build_answer(question, evidence_flat)
    return (
        answer,
        _build_answer_citations(evidence_grouped),
        False,
        bool(llm_error),
        llm_diagnostics,
        stream_observation,
        context_budget,
    )


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    run_dir_arg = str(getattr(args, "run_dir", "")).strip()
    if run_dir_arg:
        run_dir = Path(run_dir_arg)
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    run_id_arg = str(getattr(args, "run_id", "")).strip() or None
    return create_run_dir(RUNS_DIR, run_id_arg)


def _collect_planner_policy_constraint_signals(
    *,
    decision: str,
    clarify_questions: list[str],
    clarify_limit_hit: bool,
    forced_partial_answer: bool,
    sufficiency_gate: dict[str, Any],
    evidence_policy_gate: dict[str, Any],
    output_warnings: list[str],
    final_refuse_source: str | None,
) -> list[str]:
    signals: list[str] = []
    if clarify_questions or decision == "clarify":
        signals.append("missing_prerequisites")
    if "insufficient_evidence_for_answer" in output_warnings or final_refuse_source == "sufficiency_gate":
        signals.append("insufficient_evidence")
    if bool(evidence_policy_gate.get("triggered")) or "citation_mapping_incomplete_low_confidence" in output_warnings:
        signals.append("citation_incomplete")
    if bool(clarify_limit_hit):
        signals.append("clarify_limit_hit")
    if bool(forced_partial_answer):
        signals.append("forced_partial_answer")
    for rule in list(sufficiency_gate.get("triggered_rules", []) or []):
        normalized = str(rule).strip()
        if normalized.startswith("control_intent_anchor_"):
            signals.append("missing_prerequisites")
            break
    ordered: list[str] = []
    for signal in signals:
        if signal not in ordered:
            ordered.append(signal)
    return ordered


def _build_planner_policy_trace(
    *,
    planner_result: Any,
    decision: str,
    decision_reason: str,
    clarify_questions: list[str],
    assistant_mode_used: bool,
    clarify_limit_hit: bool,
    forced_partial_answer: bool,
    final_refuse_source: str | None,
    constraint_signals: list[str],
) -> dict[str, Any]:
    decision_source = "planner"
    if decision == "clarify" and clarify_questions:
        decision_source = "planner_policy"
    if assistant_mode_used or clarify_limit_hit or forced_partial_answer:
        decision_source = "planner_policy"
    if final_refuse_source in {"sufficiency_gate", "evidence_policy_gate"}:
        decision_source = "planner_policy"
    if getattr(planner_result, "decision_result", "") == "clarify" and decision == "clarify":
        decision_source = "planner"
    return {
        "decision": decision,
        "decision_reason": decision_reason,
        "decision_source": decision_source,
        "constraint_signals": list(constraint_signals),
        "requires_clarification": bool(decision == "clarify"),
        "clarify_question": clarify_questions[0] if clarify_questions else None,
        "clarify_limit_hit": bool(clarify_limit_hit),
        "forced_partial_answer": bool(forced_partial_answer),
        "assistant_mode_used": bool(assistant_mode_used),
        "final_refuse_source": final_refuse_source,
    }


def _derive_intent_from_planner_decision(
    *,
    standalone_query: str,
    planner_result: Any,
) -> tuple[str, float, str | None, str, bool, dict[str, Any], str | None]:
    primary_capability = str(getattr(planner_result, "primary_capability", "") or "").strip()
    planner_confidence = float(getattr(planner_result, "planner_confidence", 1.0) or 1.0)
    if primary_capability != "control":
        return "retrieval_query", planner_confidence, None, "planner_decision", False, {}, None

    intent_type, intent_confidence, intent_rule_matched = classify_intent_type_with_confidence(standalone_query)
    if intent_type == "retrieval_query":
        normalized = _normalize_spaces(standalone_query).lower()
        if any(token in normalized for token in ("继续", "接着", "上一个", "上一轮", "刚才")):
            intent_type = "continuation_control"
        elif any(token in normalized for token in ("表格", "table", "json", "markdown", "列表", "要点", "bullet")):
            intent_type = "format_control"
        else:
            intent_type = "style_control"
    intent_params = _extract_intent_params(standalone_query, intent_type)
    return intent_type, max(planner_confidence, intent_confidence), intent_rule_matched, "planner_decision", False, intent_params, None


def _resolve_primary_planner_result(
    *,
    user_input: str,
    standalone_query: str,
    dialog_state: str,
    history_topic_anchors: list[str],
    pending_clarify: dict[str, Any] | None,
    history_window: list[dict[str, Any]],
    config: Any,
    config_path: str,
) -> tuple[Any, str | None]:
    request = {
        "query": standalone_query,
        "mode": "local",
        "traceId": None,
        "configPath": config_path,
        "history": [],
    }
    planner_input_context = {
        "request": {
            "query": standalone_query,
            "mode": "local",
            "trace_id": None,
        },
        "conversation_context": {
            "history_size": len(history_window),
            "last_user_turn": None,
            "recent_topic_anchors": list(history_topic_anchors),
            "pending_clarify": pending_clarify,
            "previous_planner": None,
        },
        "capability_registry": _serialize_capability_registry(),
        "policy_flags": _planner_policy_flags(config),
    }
    try:
        llm_candidate_payload, llm_diagnostics = _build_planner_llm_candidate(
            request=request,
            planner_input_context=planner_input_context,
        )
    except Exception as exc:
        return (
            build_planner_fallback(
                user_input=user_input,
                standalone_query=standalone_query,
                reason="planner_exception",
                rejection_layer="runtime",
            ),
            str(exc),
        )

    if llm_candidate_payload is None:
        return (
            build_planner_fallback(
                user_input=user_input,
                standalone_query=standalone_query,
                reason=str(llm_diagnostics.get("reason") or "planner_llm_unavailable"),
                rejection_layer="llm_call",
            ),
            None,
        )

    validation = _validate_llm_planner_decision(
        llm_candidate_payload,
        policy_flags=dict(planner_input_context.get("policy_flags") or {}),
    )
    if validation.get("status") == "reject":
        rejected_layers = [str(item).strip() for item in list(validation.get("rejected_layers") or []) if str(item).strip()]
        return (
            build_planner_fallback(
                user_input=user_input,
                standalone_query=standalone_query,
                reason=str(validation.get("reason_code") or "planner_llm_invalid_schema"),
                rejection_layer=(rejected_layers[0] if rejected_layers else "validation"),
            ),
            None,
        )

    try:
        return parse_planner_result(llm_candidate_payload, default_query=standalone_query), None
    except (TypeError, ValueError) as exc:
        return (
            build_planner_fallback(
                user_input=user_input,
                standalone_query=standalone_query,
                reason="planner_llm_invalid_schema",
                rejection_layer="parse",
            ),
            str(exc),
        )


def _append_constraint_envelope(
    envelopes: list[dict[str, Any]],
    envelope: dict[str, Any] | None,
) -> None:
    if not isinstance(envelope, dict):
        return
    if envelope not in envelopes:
        envelopes.append(envelope)


def run_qa(args: argparse.Namespace) -> int:
    session_id = str(getattr(args, "session_id", "default"))
    session_store = str(getattr(args, "session_store", str(DATA_DIR / "session_store.json")))
    clear_session_flag = bool(getattr(args, "clear_session", False))
    session_cfg, _ = load_and_validate_config(str(getattr(args, "config", str(CONFIGS_DIR / "default.yaml"))))
    session_backend = str(getattr(session_cfg, "session_store_backend", "file"))
    session_redis_url = str(getattr(session_cfg, "session_redis_url", "redis://localhost:6379/0"))
    session_redis_ttl_sec = int(getattr(session_cfg, "session_redis_ttl_sec", 86400))
    session_redis_key_prefix = str(getattr(session_cfg, "session_redis_key_prefix", "rag"))
    session_redis_fallback_to_file = bool(getattr(session_cfg, "session_redis_fallback_to_file", True))
    session_recent_turns_window = int(getattr(session_cfg, "session_recent_turns_window", 3))
    session_memory_summary_enabled = bool(getattr(session_cfg, "session_memory_summary_enabled", True))
    session_memory_semantic_enabled = bool(getattr(session_cfg, "session_memory_semantic_enabled", True))
    topic_name = str(getattr(args, "topic_name", "")).strip()
    topic_paper_ids = {
        item.strip()
        for item in str(getattr(args, "topic_paper_ids", "")).split(",")
        if item.strip()
    }
    session_reset_applied = False

    if clear_session_flag:
        session_reset_applied = clear_session(
            session_id,
            session_store,
            backend=session_backend,
            redis_url=session_redis_url,
            redis_key_prefix=session_redis_key_prefix,
            redis_fallback_to_file=session_redis_fallback_to_file,
        )

    history_window, history_tokens_est = load_history_window(
        session_id,
        store_path=session_store,
        window_size=session_recent_turns_window,
        include_layered_memory=(session_memory_summary_enabled or session_memory_semantic_enabled),
        backend=session_backend,
        redis_url=session_redis_url,
        redis_ttl_sec=session_redis_ttl_sec,
        redis_key_prefix=session_redis_key_prefix,
        redis_fallback_to_file=session_redis_fallback_to_file,
    )
    dialog_state = load_dialog_state(
        session_id,
        store_path=session_store,
        backend=session_backend,
        redis_url=session_redis_url,
        redis_key_prefix=session_redis_key_prefix,
        redis_fallback_to_file=session_redis_fallback_to_file,
    )
    pending_clarify = load_pending_clarify(
        session_id,
        store_path=session_store,
        backend=session_backend,
        redis_url=session_redis_url,
        redis_key_prefix=session_redis_key_prefix,
        redis_fallback_to_file=session_redis_fallback_to_file,
    )
    (
        last_turn_decision,
        last_turn_warnings,
        entities_from_history,
        history_topic_anchors,
        transient_constraints,
    ) = derive_rewrite_context(history_window)
    history_used_turns = len([row for row in history_window if str(row.get("turn_type", "")).strip() != "summary_memory" and str(row.get("turn_type", "")).strip() != "semantic_recall_memory"])
    open_summary_intent = is_open_summary_intent(args.q)
    history_constraint_dropped = False
    dropped_constraints: list[str] = []
    if open_summary_intent and transient_constraints:
        history_constraint_dropped = True
        dropped_constraints = list(transient_constraints)
    _, preplanner_should_clear_pending, _ = detect_new_topic(
        user_input=args.q,
        dialog_state=dialog_state,
        history_topic_anchors=history_topic_anchors,
        pending_clarify=pending_clarify,
    )
    should_merge_pending = ((not open_summary_intent) or dialog_state in {"need_clarify", "waiting_followup"}) and not preplanner_should_clear_pending
    effective_input, merged_from_clarify = merge_with_pending_clarify(
        session_id,
        args.q,
        allow_pending_merge=should_merge_pending,
        store_path=session_store,
        backend=session_backend,
        redis_url=session_redis_url,
        redis_key_prefix=session_redis_key_prefix,
        redis_fallback_to_file=session_redis_fallback_to_file,
    )
    standalone_query, coreference_resolved = rewrite_with_history_context(effective_input, history_window)

    build_metrics = ensure_indexes(
        chunks_path=args.chunks,
        bm25_index_path=args.bm25_index,
        vec_index_path=args.vec_index,
        embed_index_path=args.embed_index,
        config_path=args.config,
        mode=args.mode,
    )

    bm25_index, vec_index, embed_index, config, cfg_warnings = load_indexes_and_config(
        bm25_index_path=args.bm25_index,
        vec_index_path=args.vec_index,
        embed_index_path=args.embed_index,
        config_path=args.config,
        include_embed_index=True,
    )
    for warning in cfg_warnings:
        print(f"[config-warning] {warning}", file=sys.stderr)

    guard_result = RewriteGuardResult(
        standalone_query=standalone_query,
        rewrite_meta_detected=False,
        rewrite_guard_applied=False,
        rewrite_guard_strategy="none",
        rewrite_notes=None,
    )
    if bool(getattr(config, "rewrite_meta_guard_enabled", True)):
        guard_result = apply_state_aware_rewrite_guard(
            user_input=effective_input,
            standalone_query=standalone_query,
            entities_from_history=entities_from_history,
            last_turn_decision=last_turn_decision,
            last_turn_warnings=last_turn_warnings,
            meta_patterns=config.rewrite_meta_patterns,
            meta_noise_terms=config.rewrite_meta_noise_terms,
        )
    standalone_query = guard_result.standalone_query
    open_summary_intent = is_open_summary_intent(standalone_query) or open_summary_intent
    current_topic_anchors = _derive_topic_anchors(standalone_query) or list(history_topic_anchors)
    clarify_streak_before_turn, topic_switched = _compute_same_topic_clarify_streak(
        history_window,
        current_topic_anchors,
    )
    planner_error: str | None = None
    if bool(getattr(config, "planner_enabled", True)):
        try:
            planner_result, planner_error = _resolve_primary_planner_result(
                user_input=args.q,
                standalone_query=standalone_query,
                dialog_state=dialog_state,
                history_topic_anchors=history_topic_anchors,
                pending_clarify=pending_clarify,
                history_window=history_window,
                config=config,
                config_path=args.config,
            )
        except Exception as exc:
            planner_error = str(exc)
            planner_result = build_planner_fallback(
                user_input=args.q,
                standalone_query=standalone_query,
                reason="planner_exception",
                rejection_layer="runtime",
            )
    else:
        planner_result = build_planner_fallback(
            user_input=args.q,
            standalone_query=standalone_query,
            reason="planner_disabled",
            rejection_layer="config",
        )
    standalone_query = planner_result.standalone_query or standalone_query
    open_summary_intent = open_summary_intent or planner_result.strictness == "summary"
    planner_primary_capability = planner_result.primary_capability
    planner_strictness = planner_result.strictness
    planner_action_plan = list(planner_result.action_plan or [])
    execution_trace: list[dict[str, Any]] = []
    planner_short_circuit: dict[str, Any] | None = None
    catalog_result: dict[str, Any] | None = None
    if planner_action_plan and str(planner_action_plan[0].get("action", "")) == "catalog_lookup":
        catalog_result = execute_catalog_lookup(
            query=str(planner_action_plan[0].get("query") or standalone_query),
            papers_path=(Path(args.chunks).parent / "papers.json"),
            max_papers=int(getattr(config, "planner_max_papers", 20)),
        )
        execution_trace.append(
            {
                "step": 1,
                "action": "catalog_lookup",
                "state": str(catalog_result.get("state", "ready")),
                "depends_on": [],
                "produces": ["paper_set"],
                "matched_count": int(catalog_result.get("matched_count", 0)),
                "selected_count": int(catalog_result.get("selected_count", 0)),
                "truncated": bool(catalog_result.get("truncated", False)),
                "short_circuit": bool(catalog_result.get("short_circuit", False)),
                "short_circuit_reason": catalog_result.get("short_circuit_reason"),
            }
        )
        if catalog_result.get("short_circuit"):
            planner_short_circuit = {
                "triggered": True,
                "reason": catalog_result.get("short_circuit_reason"),
                "step": "catalog_lookup",
            }
            if len(planner_action_plan) > 1:
                execution_trace.append(
                    {
                        "step": 2,
                        "action": str(planner_action_plan[1].get("action", "")),
                        "state": "short_circuit",
                        "depends_on": list(planner_action_plan[1].get("depends_on") or []),
                        "produces": [],
                        "short_circuit": True,
                        "short_circuit_reason": "missing_paper_set_dependency",
                    }
                )
        else:
            topic_paper_ids = {
                str(row.get("paper_id", "")).strip()
                for row in list(catalog_result.get("paper_set") or [])
                if str(row.get("paper_id", "")).strip()
            } or topic_paper_ids
            if len(planner_action_plan) > 1:
                execution_trace.append(
                    {
                        "step": 2,
                        "action": str(planner_action_plan[1].get("action", "")),
                        "state": "ready",
                        "depends_on": list(planner_action_plan[1].get("depends_on") or []),
                        "produces": [],
                        "short_circuit": False,
                        "short_circuit_reason": None,
                    }
                )
    else:
        planner_short_circuit = {"triggered": False, "reason": None, "step": None}
    if open_summary_intent and transient_constraints and not dropped_constraints:
        history_constraint_dropped = True
        dropped_constraints = list(transient_constraints)
    topic_switched = topic_switched or planner_result.is_new_topic
    if planner_result.is_new_topic:
        clarify_streak_before_turn = 0

    intent_router_enabled = bool(getattr(config, "intent_router_enabled", False))
    (
        intent_type,
        intent_confidence,
        intent_rule_matched,
        intent_route_source,
        intent_route_fallback,
        intent_params,
        intent_fallback_reason,
    ) = _derive_intent_from_planner_decision(
        standalone_query=standalone_query,
        planner_result=planner_result,
    )
    pre_output_warnings: list[str] = []
    if intent_router_enabled and str(planner_result.primary_capability or "") != "control":
        semantic_enabled = bool(getattr(config, "intent_router_semantic_enabled", True))
        if semantic_enabled:
            detected_intent, intent_confidence, intent_route_source, intent_params = semantic_route_intent(standalone_query)
            if detected_intent == "retrieval_query":
                detected_intent, intent_confidence, intent_rule_matched = classify_intent_type_with_confidence(standalone_query)
                intent_route_source = "rule_fallback"
                intent_route_fallback = True
            else:
                intent_rule_matched = None
        else:
            detected_intent, intent_confidence, intent_rule_matched = classify_intent_type_with_confidence(standalone_query)
            intent_route_source = "rule_fallback"
        intent_type = detected_intent
        min_confidence = float(getattr(config, "intent_control_min_confidence", 0.75))
        if intent_type != "retrieval_query" and intent_confidence < min_confidence:
            intent_fallback_reason = (
                f"low_confidence_control_intent({intent_type},{intent_confidence:.2f}<{min_confidence:.2f})"
            )
            intent_type = "retrieval_query"
            intent_route_fallback = True
            pre_output_warnings.append("intent_low_confidence_fallback_to_retrieval")
    anchor_query: str | None = None
    topic_query_source = "user_query"
    anchor_resolution: dict[str, Any] = {"status": "router_disabled"} if not intent_router_enabled else {"status": "not_control_intent"}
    force_clarify_due_to_anchor = False
    force_clarify_reason = ""
    force_clarify_code = ""

    if intent_router_enabled and intent_type != "retrieval_query":
        if bool(getattr(config, "style_control_reuse_last_topic", True)):
            anchor_query, anchor_resolution = build_control_intent_anchor_query(
                history_window,
                max_turn_distance=int(getattr(config, "style_control_max_turn_distance", 3)),
            )
            if anchor_query:
                topic_query_source = "anchor_query"
            else:
                force_clarify_due_to_anchor = True
                force_clarify_reason = "控制指令未绑定到近期主题，请补充论文标题、作者或研究主题。"
                force_clarify_code = "control_intent_anchor_missing_or_stale"
        else:
            anchor_resolution = {"status": "anchor_reuse_disabled"}

    policy_query = anchor_query or standalone_query
    scope_mode, scoped_query, scope_reason = resolve_scope_policy(policy_query)
    if force_clarify_due_to_anchor:
        scope_mode = "clarify_scope"
        scope_reason = {
            "rule": force_clarify_code,
            "has_paper_clue": False,
            "intent_type": intent_type,
            "anchor_resolution": anchor_resolution,
        }
        scoped_query = policy_query
    if merged_from_clarify and scope_mode == "clarify_scope":
        scope_mode = "open"
        scope_reason = {
            "rule": "clarify_merge_override_open_scope",
            "has_paper_clue": True,
            "merged_from_clarify": True,
            "matched_ambiguous_terms": scope_reason.get("matched_ambiguous_terms", []),
            "matched_clarify_terms": scope_reason.get("matched_clarify_terms", []),
        }
    top_k = args.top_k if args.top_k is not None else config.top_k_retrieval

    rewrite_result = RewriteResult(
        question=standalone_query,
        rewritten_query=scoped_query,
        rewrite_rule_query=scoped_query,
        rewrite_llm_query=None,
        keywords_entities={"keywords": [], "entities": []},
        strategy_hits=["rewrite_skipped_due_to_scope_clarify"],
        llm_used=False,
        llm_fallback=False,
        llm_diagnostics=None,
        rewrite_meta_detected=guard_result.rewrite_meta_detected,
        rewrite_guard_applied=guard_result.rewrite_guard_applied,
        rewrite_guard_strategy=guard_result.rewrite_guard_strategy,
        rewrite_notes=guard_result.rewrite_notes,
    )
    query_used = scoped_query
    if scope_mode != "clarify_scope":
        rewrite_result = rewrite_query(
            scoped_query,
            config,
            scope_mode=scope_mode,
            intent_type=intent_type,
            anchor_query=anchor_query,
            history_constraints_dropped=dropped_constraints,
        )
        rewrite_result.rewrite_meta_detected = guard_result.rewrite_meta_detected
        rewrite_result.rewrite_guard_applied = guard_result.rewrite_guard_applied
        rewrite_result.rewrite_guard_strategy = guard_result.rewrite_guard_strategy
        if guard_result.rewrite_notes and rewrite_result.rewrite_notes:
            rewrite_result.rewrite_notes = f"{guard_result.rewrite_notes}; {rewrite_result.rewrite_notes}"
        elif guard_result.rewrite_notes:
            rewrite_result.rewrite_notes = guard_result.rewrite_notes
        if rewrite_result.rewritten_query.strip():
            query_used = rewrite_result.rewritten_query
        min_preserve = float(getattr(config, "rewrite_entity_preservation_min_ratio", 0.6))
        if rewrite_result.rewrite_entity_preservation_ratio < min_preserve:
            pre_output_warnings.append("rewrite_entity_preservation_low")

        has_parallel_candidates = bool(rewrite_result.rewrite_llm_query and rewrite_result.rewrite_rule_query)
        if has_parallel_candidates and bool(getattr(config, "rewrite_parallel_candidates_enabled", True)):
            if bool(getattr(config, "rewrite_legacy_strategy_enabled", False)):
                rewrite_result.rewrite_candidate_scores = {
                    "rule": {"query": rewrite_result.rewrite_rule_query},
                    "llm": {"query": rewrite_result.rewrite_llm_query},
                    "selected": "llm",
                    "reason": "legacy_strategy_enabled",
                }
                rewrite_result.rewrite_selected_by = "legacy_strategy"
                query_used = rewrite_result.rewrite_llm_query or rewrite_result.rewrite_rule_query
                rewrite_result.rewritten_query = query_used
            elif bool(getattr(config, "rewrite_arbitration_enabled", True)):
                arbitration_top_k = max(6, min(12, int(top_k)))
                rule_metrics = _rewrite_candidate_metrics(
                    query=rewrite_result.rewrite_rule_query,
                    mode=args.mode,
                    top_k=arbitration_top_k,
                    bm25_index=bm25_index,
                    vec_index=vec_index,
                    embed_index=embed_index,
                    embed_index_path=args.embed_index,
                    config=config,
                )
                llm_metrics = _rewrite_candidate_metrics(
                    query=rewrite_result.rewrite_llm_query or rewrite_result.rewrite_rule_query,
                    mode=args.mode,
                    top_k=arbitration_top_k,
                    bm25_index=bm25_index,
                    vec_index=vec_index,
                    embed_index=embed_index,
                    embed_index_path=args.embed_index,
                    config=config,
                )
                margin_delta = float(getattr(config, "rewrite_arbitration_min_delta", 0.03))
                choose_llm = float(llm_metrics["final_score"]) >= float(rule_metrics["final_score"]) + margin_delta
                selected_label = "llm" if choose_llm else "rule"
                selected_query = rewrite_result.rewrite_llm_query if choose_llm else rewrite_result.rewrite_rule_query
                query_used = selected_query or rewrite_result.rewrite_rule_query
                rewrite_result.rewritten_query = query_used
                rewrite_result.rewrite_selected_by = "score_arbitration"
                rewrite_result.rewrite_candidate_scores = {
                    "rule": rule_metrics,
                    "llm": llm_metrics,
                    "selected": selected_label,
                    "margin_delta": margin_delta,
                }
                rewrite_result.strategy_hits.append(
                    "rewrite_arbitration_select_llm_query" if choose_llm else "rewrite_arbitration_select_rule_query"
                )

    calibration_result = CalibrationResult(
        calibrated_query=query_used,
        calibration_reason={"rule": "skip_calibration_for_clarify_scope"},
    )
    if scope_mode != "clarify_scope":
        calibration_result = calibrate_query_intent(
            question=standalone_query,
            rewritten_query=query_used,
            keywords_entities=rewrite_result.keywords_entities,
            scope_mode=scope_mode,
            scope_reason=scope_reason,
        )
        query_used = calibration_result.calibrated_query

    query_retry_used = False
    query_retry_reason: str | None = None
    query_retry_query: str | None = None
    output_warnings: list[str] = list(pre_output_warnings)
    if topic_switched:
        output_warnings.append("topic_switched_clarify_counter_reset")
    if history_constraint_dropped and "history_constraint_dropped" not in output_warnings:
        output_warnings.append("history_constraint_dropped")
    if force_clarify_due_to_anchor and force_clarify_code:
        output_warnings.append(force_clarify_code)
    rewrite_fallback_warning = next(
        (hit for hit in rewrite_result.strategy_hits if hit.startswith("llm_") and "fallback" in hit),
        None,
    )
    if rewrite_result.llm_fallback and rewrite_fallback_warning:
        output_warnings.append(rewrite_fallback_warning)
    removed_summary_cues = calibration_result.calibration_reason.get("removed_summary_cues", [])

    candidates: list[RetrievalCandidate] = []
    retrieval_candidates: list[RetrievalCandidate] = []
    rerank_score_distribution: dict[str, Any] = {
        "count": 0,
        "min": 0.0,
        "max": 0.0,
        "mean": 0.0,
        "p50": 0.0,
        "p90": 0.0,
    }
    expansion_stats: dict[str, Any] = {
        "enabled": False,
        "graph_loaded": False,
        "seed_count": 0,
        "added": 0,
        "added_chunk_ids": [],
    }
    if scope_mode != "clarify_scope":
        retrieval_metrics: dict[str, Any] = {
            "embedding_enabled": bool(config.embedding.enabled),
            "embedding_provider": config.embedding.provider,
            "embedding_model": config.embedding.model,
            "embedding_dim": (embed_index.embedding_dim if embed_index else 0),
            "embedding_batch_size": int(config.embedding.batch_size),
            "embedding_cache_enabled": bool(config.embedding.cache_enabled),
            "embedding_cache_hit": False,
            "embedding_cache_hits": 0,
            "embedding_cache_miss": 0,
            "embedding_api_calls": 0,
            "embedding_query_time_ms": 0,
            "embedding_build_time_ms": int(build_metrics.get("embedding_build_time_ms", 0)),
            "embedding_failed_count": int(build_metrics.get("embedding_failed_count", 0)),
            "embedding_failed_chunk_ids": list(build_metrics.get("embedding_failed_chunk_ids", [])),
            "embedding_batch_failures": list(build_metrics.get("embedding_batch_failures", [])),
            "rate_limited_count": int(build_metrics.get("rate_limited_count", 0)),
            "backoff_total_ms": int(build_metrics.get("backoff_total_ms", 0)),
            "truncated_count": int(build_metrics.get("truncated_count", 0)),
            "skipped_over_limit_count": int(build_metrics.get("skipped_over_limit_count", 0)),
            "skipped_empty": int(build_metrics.get("skipped_empty", 0)),
            "skipped_empty_chunk_ids": list(build_metrics.get("skipped_empty_chunk_ids", [])),
            "dense_score_type": "cosine",
            "hybrid_fusion_weight": float(config.fusion_weight),
            "summary_recall_enabled": False,
            "summary_candidate_count": 0,
            "summary_recall_fallback": False,
            "summary_recall_source": "paper_summary",
            "retrieval_route": "chunk",
            "structure_parse_status": "unavailable",
            "section_candidates_count": 0,
            "section_route_used": False,
            "structure_route_fallback": None,
            "structure_parse_reasons": [],
            "semantic_strategy_tier": "balanced",
        }
        summary_candidates = recall_papers_by_summary(
            query_used,
            load_paper_summaries(args.chunks),
            top_k=max(8, top_k),
        )
        summary_candidate_ids = {row.paper_id for row in summary_candidates}
        if summary_candidate_ids:
            retrieval_metrics["summary_recall_enabled"] = True
            retrieval_metrics["summary_candidate_count"] = len(summary_candidate_ids)
        else:
            retrieval_metrics["summary_recall_fallback"] = True
        structure_index = load_structure_index(args.chunks)
        structure_scope_ids = summary_candidate_ids if summary_candidate_ids else None
        structure_status, structure_reasons = summarize_structure_status(
            structure_index,
            paper_ids=set(structure_scope_ids or []),
        )
        retrieval_metrics["structure_parse_status"] = structure_status
        retrieval_metrics["structure_parse_reasons"] = structure_reasons[:10]
        section_lookup = _build_candidate_lookup(bm25_index=bm25_index, vec_index=vec_index)
        structure_query = is_structure_question(query_used)
        if structure_query and structure_status == STRUCTURE_READY:
            section_matches = retrieve_sections(
                query=query_used,
                structure_index=structure_index,
                allowed_paper_ids=(set(structure_scope_ids) if structure_scope_ids else None),
                top_k=max(3, min(8, top_k)),
            )
            retrieval_metrics["section_candidates_count"] = len(section_matches)
            if section_matches:
                retrieval_metrics["retrieval_route"] = "section"
                retrieval_metrics["section_route_used"] = True
                candidates = []
                seen_section_chunks: set[str] = set()
                for match in section_matches:
                    for rank, chunk_id in enumerate(match.child_chunk_ids, start=1):
                        base = section_lookup.get(chunk_id)
                        if base is None or chunk_id in seen_section_chunks:
                            continue
                        seen_section_chunks.add(chunk_id)
                        candidates.append(
                            _candidate_from_section_match(
                                match=match,
                                chunk_id=chunk_id,
                                base=base,
                                rank=rank,
                            )
                        )
                candidates = candidates[:top_k]
                if not candidates:
                    retrieval_metrics["structure_route_fallback"] = "section_retrieval_empty"
            else:
                retrieval_metrics["structure_route_fallback"] = "section_retrieval_empty"
        elif structure_query:
            retrieval_metrics["structure_route_fallback"] = "structure_unavailable"

        if not candidates:
            candidates = retrieve_candidates(
                query_used,
                mode=args.mode,
                top_k=top_k,
                bm25_index=bm25_index,
                vec_index=vec_index,
                embed_index=embed_index,
                embed_index_path=args.embed_index,
                config=config,
                runtime_metrics=retrieval_metrics,
            )
        shell_ratio = summary_shell_ratio(candidates, top_n=5)
        if shell_ratio > 0.6 and not query_retry_used:
            query_retry_used = True
            stripped_query, _ = strip_summary_cues(query_used)
            retry_reason = calibration_result.calibration_reason if isinstance(calibration_result.calibration_reason, dict) else {}
            added_cues = [str(x) for x in retry_reason.get("added_cues", [])]
            forced_query = stripped_query
            if added_cues:
                forced_query = f"{forced_query} {' '.join(added_cues)}".strip()
            query_retry_query = forced_query or query_used
            query_retry_reason = (
                f"summary_shell_ratio={shell_ratio:.2f}>0.60; remove shell cues and force semantic cues"
            )
            candidates = retrieve_candidates(
                query_retry_query,
                mode=args.mode,
                top_k=top_k,
                bm25_index=bm25_index,
                vec_index=vec_index,
                embed_index=embed_index,
                embed_index_path=args.embed_index,
                config=config,
                runtime_metrics=retrieval_metrics,
            )
            query_used = query_retry_query
        if summary_candidate_ids:
            narrowed, _ = _filter_candidates_by_topic(candidates, summary_candidate_ids)
            if narrowed:
                candidates = narrowed
            else:
                retrieval_metrics["summary_recall_fallback"] = True
                retrieval_metrics["summary_recall_enabled"] = False
                candidates = retrieve_candidates(
                    query_used,
                    mode=args.mode,
                    top_k=top_k,
                    bm25_index=bm25_index,
                    vec_index=vec_index,
                    embed_index=embed_index,
                    embed_index_path=args.embed_index,
                    config=config,
                    runtime_metrics=retrieval_metrics,
                )
        use_graph_expansion = (
            retrieval_metrics["retrieval_route"] != "section"
            or len(candidates) < top_k
        )
        if use_graph_expansion:
            candidates, expansion_stats = expand_candidates_with_graph(
                candidates,
                query=query_used,
                top_k=top_k,
                bm25_index=bm25_index,
                vec_index=vec_index,
                config=config,
            )
        else:
            expansion_stats = {
                "expansion_budget": 0,
                "added_chunk_ids": [],
                "skipped_reason": "section_route_sufficient_candidates",
            }
        retrieval_candidates = list(candidates)
        rerank_input: list[RetrievalCandidate] = []
        for row in candidates:
            payload = dict(row.payload or {})
            payload.setdefault("score_retrieval", float(row.score))
            payload.setdefault("source", str(payload.get("source") or args.mode))
            payload.setdefault("dense_backend", str(payload.get("dense_backend") or config.dense_backend))
            payload.setdefault("retrieval_mode", str(payload.get("retrieval_mode") or args.mode))
            if payload.get("dense_backend") == "embedding":
                payload.setdefault("embedding_provider", config.embedding.provider)
                payload.setdefault("embedding_model", config.embedding.model)
            rerank_input.append(
                RetrievalCandidate(
                    chunk_id=row.chunk_id,
                    score=row.score,
                    content_type=row.content_type,
                    payload=payload,
                    paper_id=row.paper_id,
                    page_start=row.page_start,
                    section=row.section,
                    text=row.text,
                    clean_text=row.clean_text,
                )
            )
        rerank_outcome = rerank_candidates(query=query_used, candidates=rerank_input, config=config)
        candidates = list(rerank_outcome.candidates)
        rerank_score_distribution = dict(rerank_outcome.score_distribution)
        output_warnings.extend(rerank_outcome.warnings)
    else:
        retrieval_metrics = {
            "embedding_enabled": bool(config.embedding.enabled),
            "embedding_provider": config.embedding.provider,
            "embedding_model": config.embedding.model,
            "embedding_dim": (embed_index.embedding_dim if embed_index else 0),
            "embedding_batch_size": int(config.embedding.batch_size),
            "embedding_cache_enabled": bool(config.embedding.cache_enabled),
            "embedding_cache_hit": False,
            "embedding_cache_hits": 0,
            "embedding_cache_miss": 0,
            "embedding_api_calls": 0,
            "embedding_query_time_ms": 0,
            "embedding_build_time_ms": int(build_metrics.get("embedding_build_time_ms", 0)),
            "embedding_failed_count": int(build_metrics.get("embedding_failed_count", 0)),
            "embedding_failed_chunk_ids": list(build_metrics.get("embedding_failed_chunk_ids", [])),
            "embedding_batch_failures": list(build_metrics.get("embedding_batch_failures", [])),
            "rate_limited_count": int(build_metrics.get("rate_limited_count", 0)),
            "backoff_total_ms": int(build_metrics.get("backoff_total_ms", 0)),
            "truncated_count": int(build_metrics.get("truncated_count", 0)),
            "skipped_over_limit_count": int(build_metrics.get("skipped_over_limit_count", 0)),
            "skipped_empty": int(build_metrics.get("skipped_empty", 0)),
            "skipped_empty_chunk_ids": list(build_metrics.get("skipped_empty_chunk_ids", [])),
            "dense_score_type": "cosine",
            "hybrid_fusion_weight": float(config.fusion_weight),
            "summary_recall_enabled": False,
            "summary_candidate_count": 0,
            "summary_recall_fallback": False,
            "summary_recall_source": "paper_summary",
            "retrieval_route": "chunk",
            "structure_parse_status": "unavailable",
            "section_candidates_count": 0,
            "section_route_used": False,
            "structure_route_fallback": None,
            "structure_parse_reasons": [],
            "semantic_strategy_tier": "balanced",
        }
        retrieval_candidates = list(candidates)

    candidates, topic_scope_dropped = _filter_candidates_by_topic(candidates, topic_paper_ids)
    retrieval_candidates, retrieval_scope_dropped = _filter_candidates_by_topic(retrieval_candidates, topic_paper_ids)
    if topic_paper_ids and not candidates and "topic_scope_filtered_all_candidates" not in output_warnings:
        output_warnings.append("topic_scope_filtered_all_candidates")

    paper_titles = _load_paper_title_map(args.chunks)
    papers_ranked = _build_papers_ranked(candidates, paper_titles)
    evidence_grouped, allocation_warnings = _build_evidence_grouped(
        candidates,
        papers_ranked,
        paper_titles,
        max_per_paper=MAX_EVIDENCE_PER_PAPER,
        max_papers_display=MAX_PAPERS_DISPLAY,
    )
    output_warnings.extend(allocation_warnings)
    structure_coverage_notice = _build_structure_coverage_notice(
        retrieval_route=str(retrieval_metrics.get("retrieval_route", "")),
        structure_parse_status=str(retrieval_metrics.get("structure_parse_status", "")),
        evidence_grouped=evidence_grouped,
    )
    if structure_coverage_notice and "structure_partial_coverage_disclosed" not in output_warnings:
        output_warnings.append("structure_partial_coverage_disclosed")
    assistant_mode_enabled = bool(getattr(config, "assistant_mode_enabled", True))
    assistant_mode_force_legacy_gate = bool(getattr(config, "assistant_mode_force_legacy_gate", False))
    clarify_limit = max(1, int(getattr(config, "assistant_mode_clarify_limit", 2)))
    force_partial_answer_on_limit = bool(getattr(config, "assistant_mode_force_partial_answer_on_limit", True))
    constraint_envelopes: list[dict[str, Any]] = []
    planner_catalog_short_circuit = bool(
        planner_short_circuit
        and bool(planner_short_circuit.get("triggered"))
        and (
            planner_strictness == "catalog"
            or any(term in standalone_query for term in ("列出", "列一下", "有哪些论文", "上传", "昨天", "今天", "库中"))
        )
    )
    if planner_catalog_short_circuit:
        sufficiency_gate = {
            "decision": "answer",
            "reason": "planner_short_circuit",
            "reason_code": str(planner_short_circuit.get("reason") or "planner_short_circuit"),
            "severity": "info",
            "triggered_rules": [str(planner_short_circuit.get("reason") or "planner_short_circuit")],
            "clarify_questions": [],
            "output_warnings": [],
            "clarify_limit_hit": False,
            "forced_partial_answer": False,
            "missing_aspects": [],
            "coverage_summary": {},
            "judge_source": "planner_short_circuit",
            "validator_source": "deterministic_validator_v1",
            "semantic_policy": planner_strictness,
            "constraints_envelope": None,
        }
        decision = "answer"
        decision_reason = "未找到符合条件的论文，因此未继续执行后续步骤。"
    elif planner_strictness == "catalog":
        sufficiency_gate = {
            "decision": "answer",
            "reason": "catalog_route_bypass_retrieval_gate",
            "reason_code": "catalog_route",
            "severity": "info",
            "triggered_rules": ["catalog_route"],
            "clarify_questions": [],
            "output_warnings": [],
            "clarify_limit_hit": False,
            "forced_partial_answer": False,
            "missing_aspects": [],
            "coverage_summary": {},
            "judge_source": "catalog_route_bypass",
            "validator_source": "deterministic_validator_v1",
            "semantic_policy": "catalog",
            "constraints_envelope": None,
        }
        decision = "answer"
        decision_reason = "catalog 路径绕过正文证据门控。"
    else:
        sufficiency_gate = run_sufficiency_gate(
            question=standalone_query,
            query_used=query_used,
            topic_query_source=topic_query_source,
            topic_query_text=(anchor_query if topic_query_source == "anchor_query" else query_used),
            open_summary_intent=(open_summary_intent and not assistant_mode_force_legacy_gate),
            scope_mode=scope_mode,
            evidence_grouped=evidence_grouped,
            config=config,
            clarify_count_for_topic=clarify_streak_before_turn,
            clarify_limit=clarify_limit,
            force_partial_answer_on_limit=force_partial_answer_on_limit,
        )
        decision = str(sufficiency_gate.get("decision", "answer"))
        decision_reason = str(sufficiency_gate.get("reason", "")).strip()
    _append_constraint_envelope(constraint_envelopes, sufficiency_gate.get("constraints_envelope"))
    retrieval_metrics["semantic_strategy_tier"] = sufficiency_gate.get("semantic_policy", planner_strictness)
    if force_clarify_due_to_anchor:
        decision_reason = force_clarify_reason
        sufficiency_gate["reason"] = force_clarify_reason
        sufficiency_gate["reason_code"] = force_clarify_code or "control_intent_anchor_missing_or_stale"
        triggered_rules = sufficiency_gate.get("triggered_rules")
        if isinstance(triggered_rules, list) and force_clarify_code not in triggered_rules:
            triggered_rules.append(force_clarify_code)
        sufficiency_gate["constraints_envelope"] = build_constraint_envelope(
            constraint_type="control_intent_anchor",
            reason_code=force_clarify_code or "control_intent_anchor_missing_or_stale",
            severity="warning",
            retryable=True,
            blocking_scope="topic_binding",
            user_safe_summary=force_clarify_reason,
            evidence_snapshot={"anchor_resolution": anchor_resolution},
            suggested_next_actions=["补充论文标题、作者或研究主题。"],
            clarify_questions=[],
        )
        _append_constraint_envelope(constraint_envelopes, sufficiency_gate.get("constraints_envelope"))
    clarify_questions = [str(q).strip() for q in sufficiency_gate.get("clarify_questions", []) if str(q).strip()][:1]
    assistant_policy = apply_assistant_mode_decision_policy(
        assistant_mode_enabled=assistant_mode_enabled,
        open_summary_intent=open_summary_intent,
        assistant_mode_force_legacy_gate=assistant_mode_force_legacy_gate,
        decision=decision,
        clarify_questions=clarify_questions,
        sufficiency_gate=sufficiency_gate,
        force_partial_answer_on_limit=force_partial_answer_on_limit,
        clarify_streak_before_turn=clarify_streak_before_turn,
        clarify_limit=clarify_limit,
    )
    decision = assistant_policy.decision
    decision_reason = assistant_policy.decision_reason
    clarify_questions = list(assistant_policy.clarify_questions)
    assistant_mode_used = assistant_policy.assistant_mode_used
    clarify_limit_hit = assistant_policy.clarify_limit_hit
    forced_partial_answer = assistant_policy.forced_partial_answer
    final_refuse_source: str | None = "sufficiency_gate" if decision == "refuse" else None
    if forced_partial_answer and not any(
        str((item or {}).get("reason_code", "")).strip() == "clarify_limit_reached_force_partial_answer"
        for item in constraint_envelopes
        if isinstance(item, dict)
    ):
        _append_constraint_envelope(
            constraint_envelopes,
            build_constraint_envelope(
                constraint_type="partial_answer",
                reason_code="clarify_limit_reached_force_partial_answer",
                severity="warning",
                retryable=True,
                blocking_scope="full_answer",
                user_safe_summary="连续澄清达到上限，改为低置信可追溯回答。",
                evidence_snapshot={"clarify_count_before_turn": clarify_streak_before_turn},
                suggested_next_actions=["补充更具体的论文线索或实验指标。"],
                allows_partial_answer=True,
            ),
        )
    assistant_summary_suggestions: list[str] = []
    stream_display = {
        "enabled": False,
        "chunks": 0,
    }

    def _cli_stream_delta(text_piece: str) -> None:
        piece = str(text_piece or "")
        if not piece:
            return
        if not stream_display["enabled"]:
            stream_display["enabled"] = True
            print("Answer (streaming): ", end="", flush=True)
        print(piece, end="", flush=True)
        stream_display["chunks"] += 1
        external_stream_cb = getattr(args, "on_stream_delta", None)
        if callable(external_stream_cb):
            external_stream_cb(piece)

    empty_stream_observation = {
        "answer_stream_enabled": bool(getattr(config, "answer_stream_enabled", False)),
        "answer_stream_used": False,
        "answer_stream_first_token_ms": None,
        "answer_stream_fallback_reason": None,
        "answer_stream_events": [],
        "claim_binding": {
            "enabled": False,
            "claim_count": 0,
            "bound_claim_count": 0,
            "binding_ratio": 0.0,
            "missing_claim_chunk_ids": [],
            "claim_binding_mode": "chunk",
            "fallback_to_staged": False,
            "fallback_reason": None,
        },
    }
    empty_context_budget = {
        "prompt_tokens_est": 0,
        "discarded_evidence": [],
        "discarded_evidence_count": 0,
        "history_trimmed_turns": 0,
        "context_overflow_fallback": False,
    }

    evidence_policy_gate: dict[str, Any] = {"enabled": bool(config.evidence_policy_enforced), "skipped": "not_evaluated"}
    answer_guardrail_requires_replan = False
    answer_guardrail_reason = ""
    answer_guardrail_clarify_questions: list[str] = []
    if decision == "answer":
        if planner_strictness == "catalog" or planner_catalog_short_circuit:
            answer = compose_catalog_answer(catalog_result or {})
            answer_citations = []
            assistant_summary_suggestions = []
            answer_llm_used = False
            answer_llm_fallback = False
            answer_llm_diagnostics = None
            answer_stream_observation = dict(empty_stream_observation)
            context_budget = dict(empty_context_budget)
            evidence_policy_gate = {"enabled": bool(config.evidence_policy_enforced), "skipped": "catalog_route"}
        elif assistant_mode_enabled and open_summary_intent and not assistant_mode_force_legacy_gate:
            assistant_mode_used = True
            answer, answer_citations, assistant_summary_suggestions, summary_ready = _build_assistant_summary_answer(
                question=standalone_query,
                evidence_grouped=evidence_grouped,
                min_topics=max(3, int(getattr(config, "planner_summary_min_papers", 3))) if not forced_partial_answer else 1,
                low_confidence_note=forced_partial_answer,
            )
            if summary_ready:
                answer_llm_used = False
                answer_llm_fallback = False
                answer_llm_diagnostics = None
                answer_stream_observation = dict(empty_stream_observation)
                context_budget = dict(empty_context_budget)
            else:
                if forced_partial_answer:
                    answer = "当前证据仍有限，我先给出低置信度可追溯摘要：\n"
                    answer += "1. 可用证据覆盖较少，请优先核对引用内容。\n"
                    answer += "2. 你可以继续追问具体方法或实验指标以提高结论可靠性。"
                    answer_citations = _build_answer_citations(evidence_grouped)[:3]
                    assistant_summary_suggestions = ["请指定一个主题方向（方法、实验结果或应用场景）继续深入。"]
                    answer_llm_used = False
                    answer_llm_fallback = False
                    answer_llm_diagnostics = None
                    answer_stream_observation = dict(empty_stream_observation)
                    context_budget = dict(empty_context_budget)
                    evidence_policy_gate = {"enabled": bool(config.evidence_policy_enforced), "skipped": "forced_partial_answer"}
                else:
                    answer_guardrail_requires_replan = True
                    answer_guardrail_reason = "可追溯主题不足 3 条，先最小澄清以补齐方向。"
                    answer_guardrail_clarify_questions = ["你最关心哪一类主题（方法、实验结果、应用场景）？"]
                    answer = ""
                    answer_citations = []
                    answer_llm_used = False
                    answer_llm_fallback = False
                    answer_llm_diagnostics = None
                    answer_stream_observation = dict(empty_stream_observation)
                    context_budget = dict(empty_context_budget)
                    evidence_policy_gate = {
                        "enabled": bool(config.evidence_policy_enforced),
                        "skipped": "assistant_summary_insufficient_topics",
                        "constraints_envelope": build_constraint_envelope(
                            constraint_type="evidence_insufficient",
                            reason_code="assistant_summary_insufficient_topics",
                            severity="warning",
                            retryable=True,
                            blocking_scope="summary_answer",
                            user_safe_summary=answer_guardrail_reason,
                            evidence_snapshot={"topic_count": len(evidence_grouped)},
                            suggested_next_actions=answer_guardrail_clarify_questions,
                            clarify_questions=answer_guardrail_clarify_questions,
                        ),
                    }
        else:
            (
                answer,
                answer_citations,
                answer_llm_used,
                answer_llm_fallback,
                answer_llm_diagnostics,
                answer_stream_observation,
                context_budget,
            ) = _build_answer(
                standalone_query,
                scope_mode,
                scope_reason,
                evidence_grouped,
                output_warnings,
                config,
                history_turns=history_window,
                on_stream_delta=_cli_stream_delta,
            )
        if decision == "answer" and not forced_partial_answer and planner_strictness == "strict_fact":
            answer, answer_citations, evidence_policy_gate = _apply_evidence_policy_gate(
                question=standalone_query,
                answer=answer,
                answer_citations=answer_citations,
                evidence_grouped=evidence_grouped,
                output_warnings=output_warnings,
                policy_enforced=bool(config.evidence_policy_enforced),
                claim_binding_report=answer_stream_observation.get("claim_binding"),
            )
            _append_constraint_envelope(constraint_envelopes, evidence_policy_gate.get("constraints_envelope"))
            if bool(evidence_policy_gate.get("triggered")):
                policy_override = prefer_assistant_mode_clarify(
                    assistant_mode_used=assistant_mode_used,
                    clarify_limit_hit=clarify_limit_hit,
                    decision=decision,
                    refuse_reason="关键结论缺少可追溯证据，触发证据门控。",
                    final_refuse_source=final_refuse_source,
                )
                if policy_override.applied:
                    answer_guardrail_requires_replan = True
                    answer_guardrail_reason = policy_override.decision_reason
                    answer_guardrail_clarify_questions = list(policy_override.clarify_questions)
                    answer = ""
                    answer_citations = []
                    final_refuse_source = policy_override.final_refuse_source
                else:
                    answer_guardrail_requires_replan = True
                    answer_guardrail_reason = "关键结论缺少可追溯证据，触发证据门控拒答。"
                    answer_guardrail_clarify_questions = []
                    final_refuse_source = "evidence_policy_gate"
        elif decision == "answer":
            evidence_policy_gate = {"enabled": bool(config.evidence_policy_enforced), "skipped": "forced_partial_answer"}
    elif decision == "clarify":
        if "insufficient_evidence_for_answer" not in output_warnings:
            output_warnings.append("insufficient_evidence_for_answer")
        clarify_questions = (clarify_questions or ["请提供论文标题、作者、年份或会议等线索。"])[:1]
        answer = "为确保回答基于充分证据，请先澄清以下问题："
        for idx, q in enumerate(clarify_questions, start=1):
            answer += f"\n{idx}. {q}"
        answer_citations = []
        answer_llm_used = False
        answer_llm_fallback = False
        answer_llm_diagnostics = None
        answer_stream_observation = dict(empty_stream_observation)
        context_budget = dict(empty_context_budget)
        evidence_policy_gate = {"enabled": bool(config.evidence_policy_enforced), "skipped": "sufficiency_gate_clarify"}
    else:
        decision = "refuse"
        if "insufficient_evidence_for_answer" not in output_warnings:
            output_warnings.append("insufficient_evidence_for_answer")
        final_refuse_source = final_refuse_source or "sufficiency_gate"
        answer = _m8_weak_answer(standalone_query, source=final_refuse_source)
        answer_citations = []
        answer_llm_used = False
        answer_llm_fallback = False
        answer_llm_diagnostics = None
        answer_stream_observation = dict(empty_stream_observation)
        context_budget = dict(empty_context_budget)
        evidence_policy_gate = {"enabled": bool(config.evidence_policy_enforced), "skipped": "sufficiency_gate_refuse"}

    final_shell_ratio = summary_shell_ratio(candidates, top_n=5)
    if (query_retry_used or bool(removed_summary_cues)) and final_shell_ratio > 0.6:
        output_warnings.append("summary_shell_still_dominant")

    citation_chunk_ids = {c["chunk_id"] for c in answer_citations}
    grouped_chunk_ids = {item["chunk_id"] for item in _flatten_evidence(evidence_grouped)}
    if not citation_chunk_ids.issubset(grouped_chunk_ids):
        policy_override = prefer_assistant_mode_clarify(
            assistant_mode_used=assistant_mode_used,
            clarify_limit_hit=clarify_limit_hit,
            decision=decision,
            refuse_reason="回答引用与已分配证据不一致，触发低置信降级。",
            final_refuse_source=final_refuse_source,
        )
        if not policy_override.applied:
            output_warnings.append("citation_mapping_incomplete_low_confidence")
            _append_constraint_envelope(
                constraint_envelopes,
                build_constraint_envelope(
                    constraint_type="citation_legality",
                    reason_code="citation_mapping_incomplete_low_confidence",
                    severity="warning",
                    retryable=True,
                    blocking_scope="citation_mapping",
                    user_safe_summary="部分引用未能完整映射到证据分组，回答已降级为低置信提示。",
                    citation_status="mapping_incomplete",
                    suggested_next_actions=["结合原文核验引用，或追问更具体的结论。"],
                ),
            )
            answer_citations = [c for c in answer_citations if c.get("chunk_id") in grouped_chunk_ids]
            low_conf_note = "低置信提示：部分引用未能完整映射到证据分组，请结合原文核验。"
            if low_conf_note not in answer:
                answer = f"{answer}\n\n{low_conf_note}".strip()
        else:
            answer_guardrail_requires_replan = True
            answer_guardrail_reason = policy_override.decision_reason
            answer_guardrail_clarify_questions = list(policy_override.clarify_questions)
            answer = ""
            answer_citations = []
            final_refuse_source = policy_override.final_refuse_source

    if answer_guardrail_requires_replan:
        if final_refuse_source == "evidence_policy_gate":
            decision = "refuse"
            clarify_questions = []
        else:
            decision = "clarify"
            clarify_questions = list(answer_guardrail_clarify_questions or clarify_questions or ["请提供论文标题、作者、年份或会议等线索。"])[:1]
        decision_reason = answer_guardrail_reason or decision_reason
    final_interaction = resolve_final_interaction_decision(
        planner_result=planner_result,
        proposed_decision=decision,
        decision_reason=decision_reason,
        clarify_questions=clarify_questions,
        final_refuse_source=final_refuse_source,
        constraint_envelopes=constraint_envelopes,
        forced_partial_answer=forced_partial_answer,
        posture_override_forbidden=False,
    )
    decision = final_interaction.decision
    decision_reason = final_interaction.decision_reason
    clarify_questions = list(final_interaction.clarify_questions)

    planner_policy_constraint_signals = _collect_planner_policy_constraint_signals(
        decision=decision,
        clarify_questions=clarify_questions,
        clarify_limit_hit=clarify_limit_hit,
        forced_partial_answer=forced_partial_answer,
        sufficiency_gate=sufficiency_gate,
        evidence_policy_gate=evidence_policy_gate,
        output_warnings=output_warnings,
        final_refuse_source=final_refuse_source,
    )
    planner_policy_trace = _build_planner_policy_trace(
        planner_result=planner_result,
        decision=decision,
        decision_reason=decision_reason,
        clarify_questions=clarify_questions,
        assistant_mode_used=assistant_mode_used,
        clarify_limit_hit=clarify_limit_hit,
        forced_partial_answer=forced_partial_answer,
        final_refuse_source=final_refuse_source,
        constraint_signals=planner_policy_constraint_signals,
    )

    if decision == "clarify":
        if "insufficient_evidence_for_answer" not in output_warnings:
            output_warnings.append("insufficient_evidence_for_answer")
        clarify_questions = (clarify_questions or ["请提供论文标题、作者、年份或会议等线索。"])[:1]
        answer = "为确保回答基于充分证据，请先澄清以下问题："
        for idx, q in enumerate(clarify_questions, start=1):
            answer += f"\n{idx}. {q}"
        answer_citations = []
        answer_llm_used = False
        answer_llm_fallback = False
        answer_llm_diagnostics = None
        answer_stream_observation = dict(empty_stream_observation)
        context_budget = dict(empty_context_budget)
    elif decision == "refuse":
        if "insufficient_evidence_for_answer" not in output_warnings:
            output_warnings.append("insufficient_evidence_for_answer")
        final_refuse_source = final_refuse_source or "sufficiency_gate"
        answer = _m8_weak_answer(standalone_query, source=final_refuse_source)
        answer_citations = []
        answer_llm_used = False
        answer_llm_fallback = False
        answer_llm_diagnostics = None
        answer_stream_observation = dict(empty_stream_observation)
        context_budget = dict(empty_context_budget)

    answer = _prepend_notice(answer, structure_coverage_notice)

    evidence_flat = _flatten_evidence(evidence_grouped)

    if stream_display["enabled"]:
        print()
    print(f"Answer: {answer}")
    print("Top evidence (grouped by paper):")
    for group in evidence_grouped:
        print(f"- {group['paper_id']} | {group['paper_title']}")
        for item in group["evidence"]:
            print(f"  - {item['chunk_id']} [{item['section_page']}] {item['quote']}")

    run_dir = _resolve_run_dir(args)
    need_scope_clarification = final_interaction.user_visible_posture == "clarify" or scope_mode == "clarify_scope" or (
        not bool(scope_reason.get("has_paper_clue")) and "请提供论文标题/作者/年份" in answer
    )
    final_decision = (
        "need_scope_clarification"
        if need_scope_clarification
        else (
            "insufficient_evidence"
            if final_interaction.user_visible_posture == "refuse"
            else (
                "answer_with_catalog"
                if planner_strictness == "catalog" or planner_catalog_short_circuit
                else ("llm_answer_with_evidence" if answer_llm_used else ("answer_with_evidence" if evidence_flat else "insufficient_evidence"))
            )
        )
    )
    next_transient_constraints = [str(x).strip() for x in sufficiency_gate.get("missing_aspects", []) if str(x).strip()]
    if not need_scope_clarification:
        next_transient_constraints = []
    clarify_count = (0 if planner_result.is_new_topic else clarify_streak_before_turn) + (1 if final_interaction.user_visible_posture == "clarify" else 0)

    turn_number = append_turn_record(
        session_id,
        user_input=args.q,
        standalone_query=standalone_query,
        answer=answer,
        cited_chunk_ids=[str(c.get("chunk_id", "")).strip() for c in answer_citations],
        decision=final_decision,
        output_warnings=output_warnings,
        topic_anchors=current_topic_anchors,
        transient_constraints=next_transient_constraints,
        clarify_count_for_topic=(clarify_count if decision == "clarify" else 0),
        planner_summary={
            "decision_result": planner_result.decision_result,
            "primary_capability": planner_result.primary_capability,
            "strictness": planner_result.strictness,
            "selected_tools_or_skills": list(planner_result.selected_tools_or_skills or []),
            "standalone_query": standalone_query,
            "clarify_question": (
                clarify_questions[0]
                if clarify_questions
                else (planner_result.clarify_question if planner_result.requires_clarification else None)
            ),
        },
        session_reset_applied=session_reset_applied,
        clear_pending_clarify=(planner_result.should_clear_pending_clarify or not need_scope_clarification),
        set_pending_clarify=(
            {
                "original_question": standalone_query,
                "clarify_question": (clarify_questions[0] if clarify_questions else "请提供论文标题/作者/年份/会议等线索。"),
            }
            if need_scope_clarification
            else None
        ),
        store_path=session_store,
        backend=session_backend,
        redis_url=session_redis_url,
        redis_ttl_sec=session_redis_ttl_sec,
        redis_key_prefix=session_redis_key_prefix,
        redis_fallback_to_file=session_redis_fallback_to_file,
    )
    session_reset_audit = {
        "session_reset_requested": clear_session_flag,
        "session_reset_applied": session_reset_applied,
        "history_used_turns": history_used_turns,
        "constraints_inherited_after_reset": bool(session_reset_applied and transient_constraints),
        "session_store_backend": session_backend,
        "dialog_state_before_turn": dialog_state,
    }

    trace = {
        "input_question": args.q,
        "session_id": session_id,
        "session_reset": clear_session_flag,
        "session_reset_applied": session_reset_applied,
        "session_store_backend": session_backend,
        "dialog_state": dialog_state,
        "turn_number": turn_number,
        "history_used_turns": history_used_turns,
        "history_tokens_est": history_tokens_est,
        "history_trimmed_turns": int(context_budget.get("history_trimmed_turns", 0)),
        "history_constraint_dropped": history_constraint_dropped,
        "dropped_constraints": dropped_constraints,
        "coreference_resolved": bool(coreference_resolved or merged_from_clarify),
        "standalone_query": standalone_query,
        "is_new_topic": planner_result.is_new_topic,
        "should_clear_pending_clarify": planner_result.should_clear_pending_clarify,
        "relation_to_previous": planner_result.relation_to_previous,
        "planner_used": planner_result.planner_used,
        "planner_decision_version": planner_result.decision_version,
        "user_goal": planner_result.user_goal,
        "planner_source": planner_result.planner_source,
        "planner_fallback": planner_result.planner_fallback,
        "planner_fallback_reason": planner_result.planner_fallback_reason or planner_error,
        "planner_confidence": planner_result.planner_confidence,
        "primary_capability": planner_primary_capability,
        "strictness": planner_strictness,
        "decision_result": planner_result.decision_result,
        "knowledge_route": planner_result.knowledge_route,
        "research_mode": planner_result.research_mode,
        "requires_clarification": planner_result.requires_clarification,
        "selected_tools_or_skills": list(planner_result.selected_tools_or_skills or []),
        "action_plan": planner_action_plan,
        "execution_trace": execution_trace,
        "short_circuit": planner_short_circuit or {"triggered": False, "reason": None, "step": None},
        "truncated": bool(catalog_result and catalog_result.get("truncated")),
        "intent_router_enabled": intent_router_enabled,
        "intent_type": intent_type,
        "intent_confidence": intent_confidence,
        "intent_rule_matched": intent_rule_matched,
        "intent_route_source": intent_route_source,
        "intent_route_fallback": intent_route_fallback,
        "intent_params": intent_params,
        "intent_fallback_reason": intent_fallback_reason,
        "anchor_query": anchor_query,
        "anchor_resolution": anchor_resolution,
        "topic_query_source": topic_query_source,
        "topic_name": topic_name,
        "topic_scope_paper_ids": sorted(topic_paper_ids),
        "topic_scope_filtered_count": int(topic_scope_dropped),
        "topic_scope_filtered_count_retrieval": int(retrieval_scope_dropped),
        "prompt_tokens_est": int(context_budget.get("prompt_tokens_est", 0)),
        "discarded_evidence": list(context_budget.get("discarded_evidence", [])),
        "discarded_evidence_count": int(context_budget.get("discarded_evidence_count", 0)),
        "context_overflow_fallback": bool(context_budget.get("context_overflow_fallback", False)),
        "rewrite_query": query_used,
        "retrieval_top_k": [
            {
                "chunk_id": c.chunk_id,
                "score": (c.payload or {}).get("score_retrieval", c.score),
                "score_retrieval": (c.payload or {}).get("score_retrieval", c.score),
                "mode": args.mode,
                "content_type": c.content_type,
                "paper_id": c.paper_id,
                "payload": dict(c.payload or {}),
            }
            for c in retrieval_candidates
        ],
        "expansion_added_chunks": [],
        "rerank_top_n": [
            {
                "chunk_id": c.chunk_id,
                "score": c.score,
                "score_retrieval": (c.payload or {}).get("score_retrieval"),
                "score_rerank": (c.payload or {}).get("score_rerank"),
                "mode": args.mode,
                "paper_id": c.paper_id,
                "payload": dict(c.payload or {}),
            }
            for c in candidates
        ],
        "rerank_score_distribution": rerank_score_distribution,
        "final_decision": final_decision,
        "decision": decision,
        "decision_reason": decision_reason,
        "final_interaction_authority": final_interaction.final_interaction_authority,
        "interaction_decision_source": final_interaction.interaction_decision_source,
        "final_user_visible_posture": final_interaction.user_visible_posture,
        "kernel_constraint_summary": final_interaction.kernel_constraint_summary,
        "guardrail_blocked": final_interaction.guardrail_blocked,
        "posture_override_forbidden": final_interaction.posture_override_forbidden,
        "constraints_envelope": constraint_envelopes,
        "assistant_mode_enabled": assistant_mode_enabled,
        "assistant_mode_used": assistant_mode_used,
        "assistant_summary_suggestions": assistant_summary_suggestions,
        "clarify_count": clarify_count,
        "clarify_limit_hit": clarify_limit_hit,
        "forced_partial_answer": forced_partial_answer,
        "gate_trigger_reason": list(sufficiency_gate.get("triggered_rules", []) or []),
        "final_refuse_source": final_refuse_source,
        "clarify_questions": clarify_questions,
        "sufficiency_gate": sufficiency_gate,
        "planner_policy": planner_policy_trace,
        "planner_policy_constraint_signals": planner_policy_constraint_signals,
        "session_reset_audit": session_reset_audit,
        "final_answer": answer,
        "mode": args.mode,
        "dense_backend": config.dense_backend,
        "graph_expand_alpha": float(config.graph_expand_alpha),
        "expansion_budget": int(expansion_stats.get("expansion_budget", 0)),
        "final_evidence": evidence_flat,
        "question": standalone_query,
        "scope_mode": scope_mode,
        "scope_reason": scope_reason,
        "query_used": query_used,
        "rewritten_query": rewrite_result.rewritten_query,
        "calibrated_query": query_used,
        "calibration_reason": calibration_result.calibration_reason,
        "query_retry_used": query_retry_used,
        "query_retry_reason": query_retry_reason,
        "query_retry_query": query_retry_query,
        "evidence_policy_gate": evidence_policy_gate,
        "evidence_policy_enforced": bool(config.evidence_policy_enforced),
        "rewrite_rule_query": rewrite_result.rewrite_rule_query,
        "rewrite_llm_query": rewrite_result.rewrite_llm_query,
        "keywords_entities": rewrite_result.keywords_entities,
        "strategy_hits": rewrite_result.strategy_hits,
        "rewrite_llm_used": rewrite_result.llm_used,
        "rewrite_llm_fallback": rewrite_result.llm_fallback,
        "rewrite_llm_diagnostics": rewrite_result.llm_diagnostics,
        "rewrite_meta_detected": rewrite_result.rewrite_meta_detected,
        "rewrite_guard_applied": rewrite_result.rewrite_guard_applied,
        "rewrite_guard_strategy": rewrite_result.rewrite_guard_strategy,
        "rewrite_notes": rewrite_result.rewrite_notes,
        "rewrite_quality_score": rewrite_result.rewrite_quality_score,
        "rewrite_entity_preservation_ratio": rewrite_result.rewrite_entity_preservation_ratio,
        "rewrite_entity_lost_terms": list(rewrite_result.rewrite_entity_lost_terms or []),
        "rewrite_candidate_scores": rewrite_result.rewrite_candidate_scores,
        "rewrite_selected_by": rewrite_result.rewrite_selected_by,
        "answer_llm_used": answer_llm_used,
        "answer_llm_fallback": answer_llm_fallback,
        "answer_llm_diagnostics": answer_llm_diagnostics,
        "answer_stream_enabled": answer_stream_observation["answer_stream_enabled"],
        "answer_stream_used": answer_stream_observation["answer_stream_used"],
        "answer_stream_first_token_ms": answer_stream_observation["answer_stream_first_token_ms"],
        "answer_stream_fallback_reason": answer_stream_observation["answer_stream_fallback_reason"],
        "answer_stream_events": answer_stream_observation["answer_stream_events"],
        "claim_binding": answer_stream_observation.get("claim_binding", empty_stream_observation["claim_binding"]),
        "papers_ranked": papers_ranked,
        "evidence_grouped": evidence_grouped,
        "answer_citations": answer_citations,
        "output_warnings": output_warnings,
        "summary_shell_ratio_top5": final_shell_ratio,
        "graph_expansion_stats": expansion_stats,
        "embedding_enabled": retrieval_metrics["embedding_enabled"],
        "embedding_provider": retrieval_metrics["embedding_provider"],
        "embedding_model": retrieval_metrics["embedding_model"],
        "embedding_dim": retrieval_metrics["embedding_dim"],
        "embedding_batch_size": retrieval_metrics["embedding_batch_size"],
        "embedding_cache_enabled": retrieval_metrics["embedding_cache_enabled"],
        "embedding_cache_hit": retrieval_metrics["embedding_cache_hit"],
        "embedding_cache_hits": retrieval_metrics["embedding_cache_hits"],
        "embedding_cache_miss": retrieval_metrics["embedding_cache_miss"],
        "embedding_api_calls": retrieval_metrics["embedding_api_calls"],
        "embedding_query_time_ms": retrieval_metrics["embedding_query_time_ms"],
        "embedding_build_time_ms": retrieval_metrics["embedding_build_time_ms"],
        "embedding_failed_count": retrieval_metrics["embedding_failed_count"],
        "embedding_failed_chunk_ids": retrieval_metrics["embedding_failed_chunk_ids"],
        "embedding_batch_failures": retrieval_metrics["embedding_batch_failures"],
        "rate_limited_count": retrieval_metrics["rate_limited_count"],
        "backoff_total_ms": retrieval_metrics["backoff_total_ms"],
        "truncated_count": retrieval_metrics["truncated_count"],
        "skipped_over_limit_count": retrieval_metrics["skipped_over_limit_count"],
        "skipped_empty": retrieval_metrics["skipped_empty"],
        "skipped_empty_chunk_ids": retrieval_metrics["skipped_empty_chunk_ids"],
        "dense_score_type": retrieval_metrics["dense_score_type"],
        "hybrid_fusion_weight": retrieval_metrics["hybrid_fusion_weight"],
        "summary_recall_enabled": retrieval_metrics["summary_recall_enabled"],
        "summary_candidate_count": retrieval_metrics["summary_candidate_count"],
        "summary_recall_fallback": retrieval_metrics["summary_recall_fallback"],
        "summary_recall_source": retrieval_metrics["summary_recall_source"],
        "retrieval_route": retrieval_metrics["retrieval_route"],
        "structure_parse_status": retrieval_metrics["structure_parse_status"],
        "structure_parse_reasons": retrieval_metrics["structure_parse_reasons"],
        "section_candidates_count": retrieval_metrics["section_candidates_count"],
        "section_route_used": retrieval_metrics["section_route_used"],
        "structure_route_fallback": retrieval_metrics["structure_route_fallback"],
        "structure_coverage_limited": bool(structure_coverage_notice),
        "structure_coverage_notice": structure_coverage_notice,
        "semantic_strategy_tier": retrieval_metrics["semantic_strategy_tier"],
    }
    trace["expansion_added_chunks"] = [
        {
            "chunk_id": cid,
            "source": "graph_expand",
            "dense_backend": str(
                next(((c.payload or {}).get("dense_backend") for c in retrieval_candidates if c.chunk_id == cid), None)
                or config.dense_backend
            ),
            "retrieval_mode": str(
                next(((c.payload or {}).get("retrieval_mode") for c in retrieval_candidates if c.chunk_id == cid), None)
                or args.mode
            ),
            "embedding_provider": (
                next(((c.payload or {}).get("embedding_provider") for c in retrieval_candidates if c.chunk_id == cid), None)
                if config.dense_backend == "embedding"
                else None
            ),
            "embedding_model": (
                next(((c.payload or {}).get("embedding_model") for c in retrieval_candidates if c.chunk_id == cid), None)
                if config.dense_backend == "embedding"
                else None
            ),
            "embedding_version": (
                next(((c.payload or {}).get("embedding_version") for c in retrieval_candidates if c.chunk_id == cid), None)
                if config.dense_backend == "embedding"
                else None
            ),
        }
        for cid in expansion_stats.get("added_chunk_ids", [])
    ]

    ok, errors = validate_trace_schema(trace)
    save_json(trace, run_dir / "run_trace.json")
    save_json({"trace_validation_ok": ok, "trace_validation_errors": errors}, run_dir / "run_trace_validation.json")

    qa_report = {
        "question": args.q,
        "session_id": session_id,
        "session_reset": clear_session_flag,
        "session_reset_applied": session_reset_applied,
        "session_store_backend": session_backend,
        "dialog_state": dialog_state,
        "turn_number": turn_number,
        "history_used_turns": history_used_turns,
        "history_tokens_est": history_tokens_est,
        "history_trimmed_turns": int(context_budget.get("history_trimmed_turns", 0)),
        "history_constraint_dropped": history_constraint_dropped,
        "dropped_constraints": dropped_constraints,
        "coreference_resolved": bool(coreference_resolved or merged_from_clarify),
        "standalone_query": standalone_query,
        "is_new_topic": planner_result.is_new_topic,
        "should_clear_pending_clarify": planner_result.should_clear_pending_clarify,
        "relation_to_previous": planner_result.relation_to_previous,
        "planner_used": planner_result.planner_used,
        "planner_decision_version": planner_result.decision_version,
        "user_goal": planner_result.user_goal,
        "planner_source": planner_result.planner_source,
        "planner_fallback": planner_result.planner_fallback,
        "planner_fallback_reason": planner_result.planner_fallback_reason or planner_error,
        "planner_confidence": planner_result.planner_confidence,
        "primary_capability": planner_primary_capability,
        "strictness": planner_strictness,
        "decision_result": planner_result.decision_result,
        "knowledge_route": planner_result.knowledge_route,
        "research_mode": planner_result.research_mode,
        "requires_clarification": planner_result.requires_clarification,
        "selected_tools_or_skills": list(planner_result.selected_tools_or_skills or []),
        "action_plan": planner_action_plan,
        "execution_trace": execution_trace,
        "short_circuit": planner_short_circuit or {"triggered": False, "reason": None, "step": None},
        "truncated": bool(catalog_result and catalog_result.get("truncated")),
        "intent_router_enabled": intent_router_enabled,
        "intent_type": intent_type,
        "intent_confidence": intent_confidence,
        "intent_rule_matched": intent_rule_matched,
        "intent_route_source": intent_route_source,
        "intent_route_fallback": intent_route_fallback,
        "intent_params": intent_params,
        "intent_fallback_reason": intent_fallback_reason,
        "anchor_query": anchor_query,
        "anchor_resolution": anchor_resolution,
        "topic_query_source": topic_query_source,
        "topic_name": topic_name,
        "topic_scope_paper_ids": sorted(topic_paper_ids),
        "topic_scope_filtered_count": int(topic_scope_dropped),
        "topic_scope_filtered_count_retrieval": int(retrieval_scope_dropped),
        "prompt_tokens_est": int(context_budget.get("prompt_tokens_est", 0)),
        "discarded_evidence": list(context_budget.get("discarded_evidence", [])),
        "discarded_evidence_count": int(context_budget.get("discarded_evidence_count", 0)),
        "context_overflow_fallback": bool(context_budget.get("context_overflow_fallback", False)),
        "mode": args.mode,
        "dense_backend": config.dense_backend,
        "rerank_top_n": [
            {
                "chunk_id": c.chunk_id,
                "score_retrieval": (c.payload or {}).get("score_retrieval"),
                "score_rerank": (c.payload or {}).get("score_rerank"),
                "paper_id": c.paper_id,
            }
            for c in candidates
        ],
        "rerank_score_distribution": rerank_score_distribution,
        "graph_expand_alpha": float(config.graph_expand_alpha),
        "expansion_budget": int(expansion_stats.get("expansion_budget", 0)),
        "scope_mode": scope_mode,
        "scope_reason": scope_reason,
        "query_used": query_used,
        "calibrated_query": query_used,
        "calibration_reason": calibration_result.calibration_reason,
        "query_retry_used": query_retry_used,
        "query_retry_reason": query_retry_reason,
        "query_retry_query": query_retry_query,
        "final_decision": final_decision,
        "decision": decision,
        "decision_reason": decision_reason,
        "final_interaction_authority": final_interaction.final_interaction_authority,
        "interaction_decision_source": final_interaction.interaction_decision_source,
        "final_user_visible_posture": final_interaction.user_visible_posture,
        "kernel_constraint_summary": final_interaction.kernel_constraint_summary,
        "guardrail_blocked": final_interaction.guardrail_blocked,
        "posture_override_forbidden": final_interaction.posture_override_forbidden,
        "constraints_envelope": constraint_envelopes,
        "assistant_mode_enabled": assistant_mode_enabled,
        "assistant_mode_used": assistant_mode_used,
        "assistant_summary_suggestions": assistant_summary_suggestions,
        "clarify_count": clarify_count,
        "clarify_limit_hit": clarify_limit_hit,
        "forced_partial_answer": forced_partial_answer,
        "gate_trigger_reason": list(sufficiency_gate.get("triggered_rules", []) or []),
        "final_refuse_source": final_refuse_source,
        "clarify_questions": clarify_questions,
        "sufficiency_gate": sufficiency_gate,
        "planner_policy": planner_policy_trace,
        "planner_policy_constraint_signals": planner_policy_constraint_signals,
        "session_reset_audit": session_reset_audit,
        "evidence_policy_gate": evidence_policy_gate,
        "evidence_policy_enforced": bool(config.evidence_policy_enforced),
        "rewritten_query": rewrite_result.rewritten_query,
        "rewrite_rule_query": rewrite_result.rewrite_rule_query,
        "rewrite_llm_query": rewrite_result.rewrite_llm_query,
        "keywords_entities": rewrite_result.keywords_entities,
        "strategy_hits": rewrite_result.strategy_hits,
        "rewrite_llm_used": rewrite_result.llm_used,
        "rewrite_llm_fallback": rewrite_result.llm_fallback,
        "rewrite_llm_diagnostics": rewrite_result.llm_diagnostics,
        "rewrite_meta_detected": rewrite_result.rewrite_meta_detected,
        "rewrite_guard_applied": rewrite_result.rewrite_guard_applied,
        "rewrite_guard_strategy": rewrite_result.rewrite_guard_strategy,
        "rewrite_notes": rewrite_result.rewrite_notes,
        "rewrite_quality_score": rewrite_result.rewrite_quality_score,
        "rewrite_entity_preservation_ratio": rewrite_result.rewrite_entity_preservation_ratio,
        "rewrite_entity_lost_terms": list(rewrite_result.rewrite_entity_lost_terms or []),
        "rewrite_candidate_scores": rewrite_result.rewrite_candidate_scores,
        "rewrite_selected_by": rewrite_result.rewrite_selected_by,
        "answer_llm_used": answer_llm_used,
        "answer_llm_fallback": answer_llm_fallback,
        "answer_llm_diagnostics": answer_llm_diagnostics,
        "answer_stream_enabled": answer_stream_observation["answer_stream_enabled"],
        "answer_stream_used": answer_stream_observation["answer_stream_used"],
        "answer_stream_first_token_ms": answer_stream_observation["answer_stream_first_token_ms"],
        "answer_stream_fallback_reason": answer_stream_observation["answer_stream_fallback_reason"],
        "answer_stream_events": answer_stream_observation["answer_stream_events"],
        "claim_binding": answer_stream_observation.get("claim_binding", empty_stream_observation["claim_binding"]),
        "top_k": top_k,
        "answer": answer,
        "answer_citations": answer_citations,
        "output_warnings": output_warnings,
        "graph_expansion_stats": expansion_stats,
        "embedding_enabled": retrieval_metrics["embedding_enabled"],
        "embedding_provider": retrieval_metrics["embedding_provider"],
        "embedding_model": retrieval_metrics["embedding_model"],
        "embedding_dim": retrieval_metrics["embedding_dim"],
        "embedding_batch_size": retrieval_metrics["embedding_batch_size"],
        "embedding_cache_enabled": retrieval_metrics["embedding_cache_enabled"],
        "embedding_cache_hit": retrieval_metrics["embedding_cache_hit"],
        "embedding_cache_hits": retrieval_metrics["embedding_cache_hits"],
        "embedding_cache_miss": retrieval_metrics["embedding_cache_miss"],
        "embedding_api_calls": retrieval_metrics["embedding_api_calls"],
        "embedding_query_time_ms": retrieval_metrics["embedding_query_time_ms"],
        "embedding_build_time_ms": retrieval_metrics["embedding_build_time_ms"],
        "embedding_failed_count": retrieval_metrics["embedding_failed_count"],
        "embedding_failed_chunk_ids": retrieval_metrics["embedding_failed_chunk_ids"],
        "embedding_batch_failures": retrieval_metrics["embedding_batch_failures"],
        "rate_limited_count": retrieval_metrics["rate_limited_count"],
        "backoff_total_ms": retrieval_metrics["backoff_total_ms"],
        "truncated_count": retrieval_metrics["truncated_count"],
        "skipped_over_limit_count": retrieval_metrics["skipped_over_limit_count"],
        "skipped_empty": retrieval_metrics["skipped_empty"],
        "skipped_empty_chunk_ids": retrieval_metrics["skipped_empty_chunk_ids"],
        "dense_score_type": retrieval_metrics["dense_score_type"],
        "hybrid_fusion_weight": retrieval_metrics["hybrid_fusion_weight"],
        "summary_recall_enabled": retrieval_metrics["summary_recall_enabled"],
        "summary_candidate_count": retrieval_metrics["summary_candidate_count"],
        "summary_recall_fallback": retrieval_metrics["summary_recall_fallback"],
        "summary_recall_source": retrieval_metrics["summary_recall_source"],
        "retrieval_route": retrieval_metrics["retrieval_route"],
        "structure_parse_status": retrieval_metrics["structure_parse_status"],
        "structure_parse_reasons": retrieval_metrics["structure_parse_reasons"],
        "section_candidates_count": retrieval_metrics["section_candidates_count"],
        "section_route_used": retrieval_metrics["section_route_used"],
        "structure_route_fallback": retrieval_metrics["structure_route_fallback"],
        "structure_coverage_limited": bool(structure_coverage_notice),
        "structure_coverage_notice": structure_coverage_notice,
        "semantic_strategy_tier": retrieval_metrics["semantic_strategy_tier"],
        "papers_ranked": papers_ranked,
        "evidence_grouped": evidence_grouped,
        "config_warnings": cfg_warnings,
        "index_paths": {
            "bm25": args.bm25_index,
            "vec": args.vec_index,
            "embed": args.embed_index,
        },
    }
    save_json(qa_report, run_dir / "qa_report.json")
    print(f"Run logs: {run_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_qa(args)


if __name__ == "__main__":
    raise SystemExit(main())
