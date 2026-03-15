from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from time import perf_counter
from typing import Any

from app.config import DEFAULT_CONFIG_PATH, PipelineConfig, load_and_validate_config
from app.embedding_api import EmbeddingAPIError, fetch_embeddings
from app.graph_build import ChunkGraph, load_graph
from app.index_bm25 import BM25Doc, BM25Index, load_bm25_index, search_bm25
from app.index_vec import VecDoc, VecIndex, load_vec_index, search_vec, search_vec_with_query_embedding
from app.llm_routing import (
    build_stage_fallback_signal,
    build_stage_policy,
    register_stage_failure,
    register_stage_success,
)


AUTHOR_INTENT_KEYWORDS = (
    "author",
    "affiliation",
    "university",
    "institute",
    "email",
    "corresponding",
    "作者",
    "单位",
    "机构",
    "通讯作者",
    "邮箱",
)

REFERENCE_INTENT_KEYWORDS = (
    "reference",
    "citation",
    "appendix",
    "scale",
    "questionnaire",
    "validate",
    "引用",
    "参考文献",
    "量表",
    "验证",
)

_GRAPH_CACHE: dict[str, ChunkGraph] = {}
_QUERY_EMBED_CACHE: dict[tuple[str, str], list[float]] = {}
_SUMMARY_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[\u4e00-\u9fff]{1,}")


class EmbeddingStageUnavailableError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _resolve_embedding_route(config: PipelineConfig) -> tuple[str, str, str]:
    policy = build_stage_policy(config, stage="embedding")
    primary = policy.primary
    if primary.resolve_api_key():
        return primary.api_base, primary.model, primary.api_key_env
    if policy.fallback and policy.fallback.resolve_api_key():
        return policy.fallback.api_base, policy.fallback.model, policy.fallback.api_key_env
    raise EmbeddingStageUnavailableError("missing_api_key")


def _embedding_reason_from_error(exc: Exception) -> str:
    if isinstance(exc, EmbeddingStageUnavailableError):
        return "missing_api_key"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, EmbeddingAPIError):
        category = str(getattr(exc, "category", "")).strip().lower()
        if category == "auth_failed":
            return "auth_failed"
        if category in {"rate_limit", "network_error"}:
            return "network_error"
        if category in {"server_error", "http_error"}:
            return "server_error"
        if category == "dimension_mismatch":
            return "dimension_mismatch"
        if "missing api key" in str(exc).lower():
            return "missing_api_key"
    return "network_error"


@dataclass
class PaperSummaryCandidate:
    paper_id: str
    score: float
    title: str
    keywords: list[str]


@dataclass
class RetrievalCandidate:
    chunk_id: str
    score: float
    content_type: str = "body"
    payload: dict[str, Any] | None = None
    paper_id: str = ""
    page_start: int = 0
    section: str | None = None
    text: str = ""
    clean_text: str = ""
    block_type: str | None = None
    markdown_source: str | None = None
    structure_provenance: dict[str, Any] | None = None


def _from_bm25(doc: BM25Doc, score: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=doc.chunk_id,
        score=score,
        content_type=doc.content_type,
        payload={"source": "bm25"},
        paper_id=doc.paper_id,
        page_start=doc.page_start,
        section=doc.section,
        text=doc.text,
        clean_text=doc.clean_text,
        block_type=getattr(doc, "block_type", None),
        markdown_source=getattr(doc, "markdown_source", None),
        structure_provenance=getattr(doc, "structure_provenance", None),
    )


def _from_vec(doc: VecDoc, score: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=doc.chunk_id,
        score=score,
        content_type=doc.content_type,
        payload={"source": "dense"},
        paper_id=doc.paper_id,
        page_start=doc.page_start,
        section=doc.section,
        text=doc.text,
        clean_text=doc.clean_text,
        block_type=getattr(doc, "block_type", None),
        markdown_source=getattr(doc, "markdown_source", None),
        structure_provenance=getattr(doc, "structure_provenance", None),
    )


def load_paper_summaries(chunks_path: str) -> list[dict[str, Any]]:
    summary_path = Path(chunks_path).parent / "paper_summary.json"
    if not summary_path.exists():
        return []
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        if not paper_id:
            continue
        rows.append(row)
    return rows


def recall_papers_by_summary(
    query: str,
    summaries: list[dict[str, Any]],
    *,
    top_k: int = 20,
) -> list[PaperSummaryCandidate]:
    if not summaries:
        return []
    q_tokens = {t.lower() for t in _SUMMARY_TOKEN_RE.findall(query or "") if t.strip()}
    if not q_tokens:
        return []

    hits: list[PaperSummaryCandidate] = []
    for row in summaries:
        paper_id = str(row.get("paper_id", "")).strip()
        if not paper_id:
            continue
        title = str(row.get("title", "")).strip()
        summary = str(row.get("one_paragraph_summary", "")).strip()
        keywords = [str(x).strip() for x in row.get("keywords", []) if str(x).strip()]
        haystack = " ".join([title, summary] + keywords).lower()
        if not haystack:
            continue
        overlap = sum(1 for token in q_tokens if token in haystack)
        if overlap <= 0:
            continue
        score = overlap / max(1, len(q_tokens))
        hits.append(
            PaperSummaryCandidate(
                paper_id=paper_id,
                score=float(score),
                title=title or paper_id,
                keywords=keywords[:8],
            )
        )
    hits.sort(key=lambda x: x.score, reverse=True)
    return hits[:top_k]


def apply_content_type_weights(
    candidates: list[RetrievalCandidate],
    *,
    query: str = "",
    table_list_downweight: float,
    front_matter_downweight: float = 0.3,
    reference_downweight: float = 0.3,
) -> list[RetrievalCandidate]:
    q_lower = query.lower()
    allow_front_matter = any(k in q_lower for k in AUTHOR_INTENT_KEYWORDS)
    allow_reference = any(k in q_lower for k in REFERENCE_INTENT_KEYWORDS)
    allow_table = any(k in q_lower for k in ("table", "tables", "表", "表格"))
    allow_formula = any(k in q_lower for k in ("formula", "equation", "eq.", "公式", "方程"))

    weighted: list[RetrievalCandidate] = []
    for item in candidates:
        score = item.score
        content_type = (item.content_type or "").lower()
        weight_reason = "none"
        if content_type == "table_list":
            score *= table_list_downweight
            weight_reason = "table_list_downweight"
        elif content_type == "table_block":
            score *= 1.12 if allow_table else 0.92
            weight_reason = "table_block_boost" if allow_table else "table_block_downweight"
        elif content_type == "formula_block":
            score *= 1.12 if allow_formula else 0.9
            weight_reason = "formula_block_boost" if allow_formula else "formula_block_downweight"
        elif content_type == "front_matter" and not allow_front_matter:
            score *= front_matter_downweight
            weight_reason = "front_matter_downweight"
        elif content_type == "reference" and not allow_reference:
            score *= reference_downweight
            weight_reason = "reference_downweight"

        payload = dict(item.payload or {})
        payload["weight_reason"] = weight_reason
        payload["allow_front_matter"] = allow_front_matter
        payload["allow_reference"] = allow_reference
        payload["allow_table"] = allow_table
        payload["allow_formula"] = allow_formula

        weighted.append(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                score=score,
                content_type=item.content_type,
                payload=payload,
                paper_id=item.paper_id,
                page_start=item.page_start,
                section=item.section,
                text=item.text,
                clean_text=item.clean_text,
                block_type=item.block_type,
                markdown_source=item.markdown_source,
                structure_provenance=dict(item.structure_provenance or {}) or None,
            )
        )
    return weighted


def _minmax_normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo = min(vals)
    hi = max(vals)
    if hi - lo < 1e-12:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _merge_hybrid(
    bm25: list[RetrievalCandidate],
    dense: list[RetrievalCandidate],
    fusion_weight: float,
) -> list[RetrievalCandidate]:
    bm25_map = {c.chunk_id: c for c in bm25}
    dense_map = {c.chunk_id: c for c in dense}
    bm25_scores = _minmax_normalize({c.chunk_id: c.score for c in bm25})
    dense_scores = _minmax_normalize({c.chunk_id: c.score for c in dense})

    all_ids = set(bm25_scores) | set(dense_scores)
    merged: list[RetrievalCandidate] = []
    for cid in all_ids:
        d_score = dense_scores.get(cid, 0.0)
        b_score = bm25_scores.get(cid, 0.0)
        score = fusion_weight * d_score + (1.0 - fusion_weight) * b_score

        base = dense_map.get(cid) or bm25_map[cid]
        payload = dict(base.payload or {})
        payload["dense_norm"] = d_score
        payload["bm25_norm"] = b_score
        payload["source"] = "hybrid"

        merged.append(
            RetrievalCandidate(
                chunk_id=cid,
                score=score,
                content_type=base.content_type,
                payload=payload,
                paper_id=base.paper_id,
                page_start=base.page_start,
                section=base.section,
                text=base.text,
                clean_text=base.clean_text,
                block_type=base.block_type,
                markdown_source=base.markdown_source,
                structure_provenance=dict(base.structure_provenance or {}) or None,
            )
        )

    merged.sort(key=lambda x: x.score, reverse=True)
    return merged


def retrieve_candidates(
    query: str,
    *,
    mode: str,
    top_k: int,
    bm25_index: BM25Index,
    vec_index: VecIndex,
    config: PipelineConfig,
    embed_index: VecIndex | None = None,
    runtime_metrics: dict[str, Any] | None = None,
    allow_embedding_fallback: bool = True,
) -> list[RetrievalCandidate]:
    mode = mode.lower()
    backend = config.dense_backend
    metrics = runtime_metrics if runtime_metrics is not None else {}
    metrics.setdefault("embedding_query_time_ms", 0)
    metrics.setdefault("embedding_cache_hit", False)
    metrics.setdefault("embedding_cache_hits", 0)
    metrics.setdefault("embedding_cache_miss", 0)
    metrics.setdefault("embedding_api_calls", 0)
    metrics.setdefault("embedding_build_time_ms", 0)
    metrics.setdefault("embedding_failed_count", 0)
    metrics.setdefault("embedding_failed_chunk_ids", [])
    metrics.setdefault("rate_limited_count", 0)
    metrics.setdefault("backoff_total_ms", 0)
    metrics.setdefault("truncated_count", 0)
    metrics.setdefault("skipped_over_limit_count", 0)
    metrics.setdefault("skipped_empty", 0)
    metrics.setdefault("skipped_empty_chunk_ids", [])
    metrics.setdefault("dense_score_type", "cosine")
    metrics.setdefault("embedding_fallback_reason", None)
    metrics.setdefault("embedding_fallback_success", False)
    metrics.setdefault("embedding_fallback_signal", None)
    effective_backend = backend

    bm25_candidates = [_from_bm25(doc, score) for doc, score in search_bm25(bm25_index, query, top_k=top_k)]
    dense_candidates: list[RetrievalCandidate] = []
    if mode in {"dense", "hybrid"}:
        if backend == "embedding":
            try:
                if embed_index is None or embed_index.index_type != "embedding":
                    raise EmbeddingStageUnavailableError("dimension_mismatch")
                api_base, model, api_key_env = _resolve_embedding_route(config)
                cache_key = (embed_index.embedding_model, query)
                query_vec = _QUERY_EMBED_CACHE.get(cache_key)
                if query_vec is None:
                    t0 = perf_counter()
                    vectors = fetch_embeddings(
                        [query],
                        base_url=api_base,
                        model=model,
                        api_key_env=api_key_env,
                    )
                    metrics["embedding_query_time_ms"] = int((perf_counter() - t0) * 1000)
                    metrics["embedding_cache_hit"] = False
                    metrics["embedding_cache_miss"] = 1
                    metrics["embedding_api_calls"] = 1
                    query_vec = vectors[0]
                    _QUERY_EMBED_CACHE[cache_key] = query_vec
                else:
                    metrics["embedding_cache_hit"] = True
                    metrics["embedding_cache_hits"] = 1
                if len(query_vec) != int(embed_index.embedding_dim):
                    raise EmbeddingAPIError(
                        f"embedding dimension mismatch: query={len(query_vec)} index={embed_index.embedding_dim}",
                        category="dimension_mismatch",
                    )
                dense_candidates = [
                    _from_vec(doc, score)
                    for doc, score in search_vec_with_query_embedding(
                        embed_index,
                        query_vec,
                        top_k=top_k,
                        normalize_query=config.embedding.normalize,
                    )
                ]
                register_stage_success("embedding")
            except Exception as exc:
                reason = _embedding_reason_from_error(exc)
                signal = build_stage_fallback_signal("embedding", category=reason)
                metrics["embedding_fallback_reason"] = reason
                metrics["embedding_fallback_signal"] = signal.fallback_mode
                register_stage_failure("embedding", category=reason, reason=reason)
                if (not signal.can_fallback) or (not allow_embedding_fallback):
                    raise
                effective_backend = "tfidf"
                metrics["embedding_fallback_success"] = True
                dense_candidates = [_from_vec(doc, score) for doc, score in search_vec(vec_index, query, top_k=top_k)]
        else:
            dense_candidates = [_from_vec(doc, score) for doc, score in search_vec(vec_index, query, top_k=top_k)]

    if mode == "bm25":
        candidates = bm25_candidates
    elif mode == "dense":
        candidates = dense_candidates
    elif mode == "hybrid":
        candidates = _merge_hybrid(bm25_candidates, dense_candidates, fusion_weight=config.fusion_weight)
    else:
        raise ValueError(f"unsupported mode: {mode}")

    candidates = apply_content_type_weights(
        candidates,
        query=query,
        table_list_downweight=config.table_list_downweight,
        front_matter_downweight=config.front_matter_downweight,
        reference_downweight=config.reference_downweight,
    )
    enriched: list[RetrievalCandidate] = []
    for item in candidates:
        payload = dict(item.payload or {})
        payload["source"] = str(payload.get("source") or mode)
        payload["dense_backend"] = effective_backend
        payload["retrieval_mode"] = mode
        payload["score_retrieval"] = float(item.score)
        if effective_backend == "embedding":
            payload["embedding_provider"] = config.embedding.provider
            payload["embedding_model"] = config.embedding.model
            version = payload.get("embedding_version")
            if version is not None:
                payload["embedding_version"] = str(version)
        enriched.append(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                score=item.score,
                content_type=item.content_type,
                payload=payload,
                paper_id=item.paper_id,
                page_start=item.page_start,
                section=item.section,
                text=item.text,
                clean_text=item.clean_text,
                block_type=item.block_type,
                markdown_source=item.markdown_source,
                structure_provenance=dict(item.structure_provenance or {}) or None,
            )
        )
    enriched.sort(key=lambda x: x.score, reverse=True)
    return enriched[:top_k]


def _load_graph_cached(path: str) -> ChunkGraph | None:
    normalized = str(Path(path))
    if normalized in _GRAPH_CACHE:
        return _GRAPH_CACHE[normalized]
    try:
        graph = load_graph(normalized)
    except (FileNotFoundError, OSError, ValueError, TypeError, KeyError):
        return None
    _GRAPH_CACHE[normalized] = graph
    return graph


def _build_doc_lookup(bm25_index: BM25Index, vec_index: VecIndex) -> dict[str, RetrievalCandidate]:
    lookup: dict[str, RetrievalCandidate] = {}
    for doc in bm25_index.docs:
        lookup[doc.chunk_id] = _from_bm25(doc, 0.0)
    for doc in vec_index.docs:
        lookup.setdefault(doc.chunk_id, _from_vec(doc, 0.0))
    return lookup


def _allow_front_matter(query: str, keywords: list[str] | tuple[str, ...]) -> bool:
    q = query.lower()
    return any(k.lower() in q for k in keywords)


def _allow_reference(query: str, keywords: list[str] | tuple[str, ...]) -> bool:
    q = query.lower()
    return any(k.lower() in q for k in keywords)


def expand_candidates_with_graph(
    seeds: list[RetrievalCandidate],
    *,
    query: str,
    top_k: int,
    bm25_index: BM25Index,
    vec_index: VecIndex,
    config: PipelineConfig,
) -> tuple[list[RetrievalCandidate], dict[str, Any]]:
    seed_unique: list[RetrievalCandidate] = []
    seen_seed: set[str] = set()
    for item in seeds:
        if item.chunk_id in seen_seed:
            continue
        seen_seed.add(item.chunk_id)
        seed_payload = dict(item.payload or {})
        seed_payload.setdefault("score_retrieval", float(item.score))
        seed_unique.append(
            RetrievalCandidate(
                chunk_id=item.chunk_id,
                score=item.score,
                content_type=item.content_type,
                payload=seed_payload,
                paper_id=item.paper_id,
                page_start=item.page_start,
                section=item.section,
                text=item.text,
                clean_text=item.clean_text,
                block_type=item.block_type,
                markdown_source=item.markdown_source,
                structure_provenance=dict(item.structure_provenance or {}) or None,
            )
        )

    alpha = max(0.0, float(config.graph_expand_alpha))
    global_max = max(1, int(config.graph_expand_max_candidates))
    max_total_by_ratio = max(1, int(top_k * (1.0 + alpha)))
    max_total = max(len(seed_unique), min(max_total_by_ratio, global_max))
    budget = max(0, max_total - len(seed_unique))

    stats: dict[str, Any] = {
        "enabled": alpha > 0,
        "graph_loaded": False,
        "seed_count": len(seed_unique),
        "adjacent_queries": 0,
        "entity_queries": 0,
        "neighbors_considered": 0,
        "added": 0,
        "added_by_source": {"adjacent": 0, "entity": 0},
        "duplicate_hits": 0,
        "filtered_watermark": 0,
        "filtered_front_matter": 0,
        "filtered_reference": 0,
        "skipped_by_budget": 0,
        "missing_nodes": 0,
        "missing_docs": 0,
        "allow_front_matter": False,
        "allow_reference": False,
        "graph_expand_alpha": alpha,
        "alpha": alpha,
        "max_total_candidates": max_total,
        "expansion_budget": budget,
        "added_chunk_ids": [],
    }
    if alpha <= 0:
        stats["reason"] = "graph_expand_alpha_disabled"
        return seed_unique[:max_total], stats

    graph = _load_graph_cached(config.graph_path)
    if graph is None:
        stats["reason"] = "graph_unavailable"
        return seed_unique[:max_total], stats
    stats["graph_loaded"] = True

    allow_front_matter = _allow_front_matter(query, config.graph_expand_author_keywords or AUTHOR_INTENT_KEYWORDS)
    allow_reference = _allow_reference(query, config.graph_expand_reference_keywords or REFERENCE_INTENT_KEYWORDS)
    stats["allow_front_matter"] = allow_front_matter
    stats["allow_reference"] = allow_reference
    doc_lookup = _build_doc_lookup(bm25_index, vec_index)

    out: list[RetrievalCandidate] = list(seed_unique[:max_total])
    seen_ids = {c.chunk_id for c in out}
    remaining = max(0, max_total - len(out))

    for seed in seed_unique:
        for edge_type in ("adjacent", "entity"):
            if edge_type == "adjacent":
                stats["adjacent_queries"] += 1
            else:
                stats["entity_queries"] += 1
            neighbor_ids = graph.neighbors(seed.chunk_id, type=edge_type, hop=1)
            for neighbor_id in neighbor_ids:
                stats["neighbors_considered"] += 1
                if neighbor_id in seen_ids:
                    stats["duplicate_hits"] += 1
                    continue
                node = graph.nodes.get(neighbor_id)
                if node is None:
                    stats["missing_nodes"] += 1
                    continue
                content_type = (node.content_type or "body").lower()
                if content_type == "watermark":
                    stats["filtered_watermark"] += 1
                    continue
                if content_type == "front_matter" and not allow_front_matter:
                    stats["filtered_front_matter"] += 1
                    continue
                if content_type == "reference" and not allow_reference:
                    stats["filtered_reference"] += 1
                    continue
                if remaining <= 0:
                    stats["skipped_by_budget"] += 1
                    continue

                base = doc_lookup.get(neighbor_id)
                if base is None:
                    stats["missing_docs"] += 1
                    base = RetrievalCandidate(
                        chunk_id=neighbor_id,
                        score=0.0,
                        content_type=content_type,
                        paper_id=node.paper_id,
                        page_start=node.page_start,
                        section=node.section,
                        block_type=None,
                        markdown_source=None,
                        structure_provenance=None,
                    )
                seed_payload = dict(seed.payload or {})
                payload = dict(base.payload or {})
                for key in (
                    "dense_backend",
                    "retrieval_mode",
                    "embedding_provider",
                    "embedding_model",
                    "embedding_version",
                ):
                    if key in seed_payload:
                        payload[key] = seed_payload[key]
                if (
                    payload.get("dense_backend") == "embedding"
                    and "embedding_provider" not in payload
                    and "embedding_model" not in payload
                ):
                    payload["embedding_provider"] = config.embedding.provider
                    payload["embedding_model"] = config.embedding.model
                payload["source"] = "graph_expand"
                payload["retrieval_source"] = edge_type
                payload["expanded_from"] = seed.chunk_id
                payload["graph_hop"] = 1
                payload["allow_front_matter"] = allow_front_matter
                payload["allow_reference"] = allow_reference
                expanded_score = max(seed.score * (0.97 if edge_type == "adjacent" else 0.94), 1e-9)
                payload["score_retrieval"] = float(expanded_score)

                out.append(
                    RetrievalCandidate(
                        chunk_id=base.chunk_id,
                        score=expanded_score,
                        content_type=base.content_type or content_type,
                        payload=payload,
                        paper_id=base.paper_id,
                        page_start=base.page_start,
                        section=base.section,
                        text=base.text,
                        clean_text=base.clean_text,
                        block_type=base.block_type,
                        markdown_source=base.markdown_source,
                        structure_provenance=dict(base.structure_provenance or {}) or None,
                    )
                )
                seen_ids.add(neighbor_id)
                remaining -= 1
                stats["added"] += 1
                if edge_type in stats["added_by_source"]:
                    stats["added_by_source"][edge_type] += 1
                stats["added_chunk_ids"].append(neighbor_id)

    return out[:max_total], stats


def load_table_list_downweight(config_path: str = str(DEFAULT_CONFIG_PATH)) -> tuple[float, list[str]]:
    config, warnings = load_and_validate_config(config_path)
    return config.table_list_downweight, warnings


def load_indexes_and_config(
    *,
    bm25_index_path: str = "data/indexes/bm25_index.json",
    vec_index_path: str = "data/indexes/vec_index.json",
    embed_index_path: str = "data/indexes/vec_index_embed.json",
    config_path: str = str(DEFAULT_CONFIG_PATH),
    include_embed_index: bool = False,
) -> tuple[BM25Index, VecIndex, PipelineConfig, list[str]] | tuple[BM25Index, VecIndex, VecIndex | None, PipelineConfig, list[str]]:
    config, warnings = load_and_validate_config(config_path)
    bm25_index = load_bm25_index(bm25_index_path)
    vec_index = load_vec_index(vec_index_path)
    if not include_embed_index:
        return bm25_index, vec_index, config, warnings

    embed_index: VecIndex | None = None
    embed_path = Path(embed_index_path)
    if embed_path.exists():
        embed_index = load_vec_index(embed_path)
    return bm25_index, vec_index, embed_index, config, warnings


def main() -> int:
    return 0
