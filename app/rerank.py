from __future__ import annotations

import json
import os
from time import perf_counter
import urllib.error
import urllib.request
from dataclasses import dataclass
from statistics import mean
from typing import Any

from app.config import PipelineConfig
from app.llm_client import emit_llm_debug_event
from app.llm_observability import format_llm_debug_text
from app.llm_routing import (
    build_stage_fallback_signal,
    build_stage_policy,
    register_stage_failure,
    register_stage_success,
)
from app.retrieve import RetrievalCandidate


@dataclass
class RerankOutcome:
    candidates: list[RetrievalCandidate]
    warnings: list[str]
    score_distribution: dict[str, float | int]
    used_fallback: bool
    provider: str
    model: str


def _clone_candidate(
    candidate: RetrievalCandidate,
    *,
    score_retrieval: float,
    score_rerank: float,
) -> RetrievalCandidate:
    payload = dict(candidate.payload or {})
    payload["score_retrieval"] = float(score_retrieval)
    payload["score_rerank"] = float(score_rerank)
    return RetrievalCandidate(
        chunk_id=candidate.chunk_id,
        score=float(score_rerank),
        content_type=candidate.content_type,
        payload=payload,
        paper_id=candidate.paper_id,
        page_start=candidate.page_start,
        section=candidate.section,
        text=candidate.text,
        clean_text=candidate.clean_text,
    )


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    p = max(0.0, min(1.0, q))
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return float(values[lo])
    frac = pos - lo
    return float(values[lo] * (1 - frac) + values[hi] * frac)


def _score_distribution(scores: list[float]) -> dict[str, float | int]:
    if not scores:
        return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0}
    vals = sorted(float(s) for s in scores)
    return {
        "count": len(vals),
        "min": float(vals[0]),
        "max": float(vals[-1]),
        "mean": float(mean(vals)),
        "p50": _quantile(vals, 0.50),
        "p90": _quantile(vals, 0.90),
    }


def _fallback_lexical_score(query: str, text: str) -> float:
    q_tokens = {t for t in query.lower().split() if t}
    if not q_tokens:
        return 0.0
    doc_tokens = {t for t in text.lower().split() if t}
    if not doc_tokens:
        return 0.0
    overlap = len(q_tokens & doc_tokens)
    return overlap / max(1, len(q_tokens))


def _read_trace_id(headers: Any) -> str | None:
    if headers is None:
        return None
    for key in ("x-siliconcloud-trace-id", "x-trace-id", "trace-id"):
        value = headers.get(key)
        if value:
            return str(value)
    return None


def _rerank_response_summary(scores: list[float]) -> dict[str, float | int]:
    if not scores:
        return {"score_count": 0, "max_score": 0.0, "min_score": 0.0}
    return {
        "score_count": len(scores),
        "max_score": max(float(score) for score in scores),
        "min_score": min(float(score) for score in scores),
    }


def _siliconflow_rerank(
    *,
    query: str,
    documents: list[str],
    provider: str,
    api_base: str,
    model: str,
    api_key_env: str,
    timeout_ms: int,
) -> list[float]:
    endpoint = api_base.rstrip("/") + "/rerank"
    request_payload = format_llm_debug_text(
        {
            "model": model,
            "query": query,
            "documents": documents,
        }
    )
    started_at = perf_counter()
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "rerank",
                "debug_stage": "rerank",
                "provider": provider,
                "model": model,
                "api_base": api_base,
                "endpoint": endpoint,
                "transport": "urllib",
                "reason": "missing_api_key",
                "error_category": "missing_api_key",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "request_payload": request_payload,
            }
        )
        raise RuntimeError(f"missing_api_key_env:{api_key_env}")

    payload = {
        "model": model,
        "query": query,
        "documents": documents,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    timeout_sec = max(1.0, float(timeout_ms) / 1000.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            trace_id = _read_trace_id(getattr(resp, "headers", None))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        trace_id = _read_trace_id(getattr(exc, "headers", None))
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "rerank",
                "debug_stage": "rerank",
                "provider": provider,
                "model": model,
                "api_base": api_base,
                "endpoint": endpoint,
                "transport": "urllib",
                "status_code": int(exc.code),
                "reason": "http_error",
                "error_category": "http_error",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(detail),
            }
        )
        raise
    except (urllib.error.URLError, TimeoutError) as exc:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "rerank",
                "debug_stage": "rerank",
                "provider": provider,
                "model": model,
                "api_base": api_base,
                "endpoint": endpoint,
                "transport": "urllib",
                "reason": "network_error",
                "error_category": "network_error",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(str(exc)),
            }
        )
        raise

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "rerank",
                "debug_stage": "rerank",
                "provider": provider,
                "model": model,
                "api_base": api_base,
                "endpoint": endpoint,
                "transport": "urllib",
                "status_code": 200,
                "reason": "invalid_response",
                "error_category": "invalid_response",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(raw),
            }
        )
        raise

    rows = data.get("results")
    if not isinstance(rows, list):
        rows = data.get("data")
    if not isinstance(rows, list):
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "rerank",
                "debug_stage": "rerank",
                "provider": provider,
                "model": model,
                "api_base": api_base,
                "endpoint": endpoint,
                "transport": "urllib",
                "status_code": 200,
                "reason": "invalid_response",
                "error_category": "invalid_response",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(data),
            }
        )
        raise RuntimeError("invalid_rerank_response")

    scores: list[float] = [0.0 for _ in documents]
    seen: set[int] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        idx = row.get("index", i)
        try:
            idx_int = int(idx)
        except (TypeError, ValueError):
            continue
        if idx_int < 0 or idx_int >= len(documents):
            continue
        score_val = row.get("relevance_score", row.get("score", 0.0))
        try:
            score = float(score_val)
        except (TypeError, ValueError):
            score = 0.0
        scores[idx_int] = score
        seen.add(idx_int)
    if not seen:
        emit_llm_debug_event(
            {
                "event": "request_failure",
                "stage": "rerank",
                "debug_stage": "rerank",
                "provider": provider,
                "model": model,
                "api_base": api_base,
                "endpoint": endpoint,
                "transport": "urllib",
                "status_code": 200,
                "reason": "empty_scores",
                "error_category": "invalid_response",
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
                "trace_id": trace_id,
                "request_payload": request_payload,
                "response_payload": format_llm_debug_text(data),
            }
        )
        raise RuntimeError("empty_rerank_scores")
    emit_llm_debug_event(
        {
            "event": "request_success",
            "stage": "rerank",
            "debug_stage": "rerank",
            "provider": provider,
            "model": model,
            "api_base": api_base,
            "endpoint": endpoint,
            "transport": "urllib",
            "status_code": 200,
            "elapsed_ms": int((perf_counter() - started_at) * 1000),
            "trace_id": trace_id,
            "request_payload": request_payload,
            "response_payload": format_llm_debug_text(data),
            "response_text": format_llm_debug_text(_rerank_response_summary(scores)),
        }
    )
    return scores


def _compute_scores(
    *,
    query: str,
    candidates: list[RetrievalCandidate],
    config: PipelineConfig,
) -> tuple[list[float], bool]:
    docs = [c.clean_text or c.text for c in candidates]
    provider = (config.rerank.provider or "").strip().lower()
    if provider in {"siliconflow", "silicon-flow"}:
        attempts = max(0, int(config.rerank.max_retries)) + 1
        policy = build_stage_policy(config, stage="rerank")
        target = policy.primary
        if not target.resolve_api_key() and policy.fallback:
            target = policy.fallback
        if not target.resolve_api_key():
            raise RuntimeError("missing_api_key")
        last_err: Exception | None = None
        for _ in range(attempts):
            try:
                return _siliconflow_rerank(
                    query=query,
                    documents=docs,
                    provider=target.provider,
                    api_base=target.api_base,
                    model=target.model,
                    api_key_env=target.api_key_env,
                    timeout_ms=config.rerank.timeout_ms,
                ), False
            except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                last_err = exc
        # Let caller apply the canonical retrieval-score fallback path.
        if last_err is not None:
            raise last_err
        raise RuntimeError("rerank_provider_failed")
    scores = [_fallback_lexical_score(query, doc) for doc in docs]
    return scores, True


def rerank_candidates(
    *,
    query: str,
    candidates: list[RetrievalCandidate],
    config: PipelineConfig,
) -> RerankOutcome:
    warnings: list[str] = []
    top_n = max(1, int(config.rerank.top_n))

    prepared: list[tuple[RetrievalCandidate, float]] = []
    invalid_contract = 0
    missing_embed_meta = 0
    for row in candidates:
        payload = dict(row.payload or {})
        score_retrieval = float(payload.get("score_retrieval", row.score))
        payload.setdefault("score_retrieval", score_retrieval)
        payload.setdefault("source", payload.get("source"))
        payload.setdefault("dense_backend", payload.get("dense_backend"))

        required = (
            ("score_retrieval", payload.get("score_retrieval") is not None),
            ("payload.source", bool(payload.get("source"))),
            ("payload.dense_backend", bool(payload.get("dense_backend"))),
        )
        missing = [name for name, ok in required if not ok]
        if payload.get("dense_backend") == "embedding":
            embed_required = (
                ("payload.embedding_provider", bool(payload.get("embedding_provider"))),
                ("payload.embedding_model", bool(payload.get("embedding_model"))),
            )
            embed_missing = [name for name, ok in embed_required if not ok]
            if embed_missing:
                missing_embed_meta += 1
                missing.extend(embed_missing)
        if missing:
            invalid_contract += 1
            continue

        prepared.append(
            (
                RetrievalCandidate(
                    chunk_id=row.chunk_id,
                    score=score_retrieval,
                    content_type=row.content_type,
                    payload=payload,
                    paper_id=row.paper_id,
                    page_start=row.page_start,
                    section=row.section,
                    text=row.text,
                    clean_text=row.clean_text,
                ),
                score_retrieval,
            )
        )

    if invalid_contract > 0:
        warnings.append("rerank_input_contract_violation")
    if missing_embed_meta > 0:
        warnings.append("rerank_input_missing_embedding_metadata")

    if not prepared:
        return RerankOutcome(
            candidates=[],
            warnings=warnings + ["rerank_no_valid_candidates"],
            score_distribution=_score_distribution([]),
            used_fallback=True,
            provider=config.rerank.provider,
            model=config.rerank.model,
        )

    scored_rows: list[RetrievalCandidate] = []
    if not config.rerank.enabled:
        for row, retrieval_score in prepared:
            scored_rows.append(_clone_candidate(row, score_retrieval=retrieval_score, score_rerank=retrieval_score))
        scored_rows.sort(key=lambda x: float(x.score), reverse=True)
        return RerankOutcome(
            candidates=scored_rows[:top_n],
            warnings=warnings,
            score_distribution=_score_distribution([float(r.score) for r in scored_rows]),
            used_fallback=False,
            provider="disabled",
            model=config.rerank.model,
        )

    used_fallback = False
    try:
        scores, used_fallback = _compute_scores(query=query, candidates=[x[0] for x in prepared], config=config)
        if len(scores) != len(prepared):
            raise RuntimeError("rerank_score_length_mismatch")
        for (row, retrieval_score), rerank_score in zip(prepared, scores):
            scored_rows.append(
                _clone_candidate(
                    row,
                    score_retrieval=retrieval_score,
                    score_rerank=float(rerank_score),
                )
            )
        register_stage_success("rerank")
    except Exception as exc:
        if not config.rerank.fallback_to_retrieval:
            raise
        warnings.append("rerank_fallback_to_retrieval")
        used_fallback = True
        reason = "server_error"
        text = str(exc).lower()
        if "missing_api_key" in text:
            reason = "missing_api_key"
        elif isinstance(exc, urllib.error.HTTPError) and int(exc.code or 0) in {401, 403}:
            reason = "auth_failed"
        elif isinstance(exc, TimeoutError):
            reason = "timeout"
        elif isinstance(exc, urllib.error.URLError):
            reason = "network_error"
        signal = build_stage_fallback_signal("rerank", category=reason)
        register_stage_failure("rerank", category=signal.failure_category, reason=signal.failure_category)
        for row, retrieval_score in prepared:
            cloned = _clone_candidate(row, score_retrieval=retrieval_score, score_rerank=retrieval_score)
            payload = dict(cloned.payload or {})
            payload["used_fallback"] = True
            payload["rerank_fallback_to_retrieval"] = True
            cloned.payload = payload
            scored_rows.append(cloned)

    scored_rows.sort(key=lambda x: float(x.score), reverse=True)
    return RerankOutcome(
        candidates=scored_rows[:top_n],
        warnings=warnings,
        score_distribution=_score_distribution([float(r.score) for r in scored_rows]),
        used_fallback=used_fallback,
        provider=config.rerank.provider,
        model=config.rerank.model,
    )
