from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.chunks_dataset import ChunkDoc, load_chunks_clean, tokenize
from app.config import EmbeddingConfig
from app.embedding_api import EmbeddingAPIError, fetch_embeddings


@dataclass
class VecDoc:
    chunk_id: str
    paper_id: str
    page_start: int
    section: str | None
    text: str
    clean_text: str
    content_type: str


@dataclass
class VecIndex:
    docs: list[VecDoc]
    idf: dict[str, float]
    doc_vectors: list[dict[str, float]]
    doc_norms: list[float]
    index_type: str = "tfidf"
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_dim: int = 0
    embedding_build_time: str = ""
    embeddings: list[list[float]] | None = None


@dataclass
class EmbeddingBuildStats:
    cache_hits: int = 0
    cache_miss: int = 0
    api_calls: int = 0
    failed_items: int = 0
    failure_records_written: int = 0
    skipped_empty: int = 0
    truncated_count: int = 0
    skipped_over_limit_count: int = 0
    skipped_empty_chunk_ids: list[str] = field(default_factory=list)
    embedding_failed_chunk_ids: list[str] = field(default_factory=list)
    rate_limited_count: int = 0
    backoff_total_ms: int = 0
    embedding_batch_failures: list[dict[str, Any]] = field(default_factory=list)
    build_time_ms: int = 0


@dataclass
class _EmbeddingWorkItem:
    idx: int
    doc: VecDoc
    texts: list[str]
    normalized_text_hash: str


@dataclass
class _EmbeddingTaskResult:
    succeeded: list[tuple[_EmbeddingWorkItem, list[float]]] = field(default_factory=list)
    failed: list[tuple[_EmbeddingWorkItem, EmbeddingAPIError | None, int]] = field(default_factory=list)
    cache_rows: list[dict[str, Any]] = field(default_factory=list)
    failure_rows: list[dict[str, Any]] = field(default_factory=list)
    status_messages: list[str] = field(default_factory=list)
    batch_failures: list[dict[str, Any]] = field(default_factory=list)
    api_calls: int = 0
    rate_limited_count: int = 0
    backoff_total_ms: int = 0


class _RateLimiter:
    def __init__(self, max_requests_per_minute: int) -> None:
        self.max_requests_per_minute = max(1, int(max_requests_per_minute))
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def wait_for_slot(self) -> None:
        while True:
            sleep_sec = 0.0
            with self._lock:
                now = time.monotonic()
                cutoff = now - 60.0
                self._timestamps = [x for x in self._timestamps if x >= cutoff]
                if len(self._timestamps) < self.max_requests_per_minute:
                    self._timestamps.append(now)
                    return
                oldest = self._timestamps[0]
                sleep_sec = max(0.0, 60.0 - (now - oldest))
            if sleep_sec <= 0:
                continue
            time.sleep(sleep_sec)


def _to_tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf: dict[str, int] = {}
    for tok in tokens:
        tf[tok] = tf.get(tok, 0) + 1
    vec: dict[str, float] = {}
    if not tf:
        return vec
    max_tf = max(tf.values())
    for term, freq in tf.items():
        w_tf = 0.5 + 0.5 * (freq / max_tf)
        vec[term] = w_tf * idf.get(term, 0.0)
    return vec


def _norm(vec: dict[str, float]) -> float:
    return math.sqrt(sum(v * v for v in vec.values()))


def _l2_norm_dense(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def _normalize_dense(vec: list[float]) -> list[float]:
    norm = _l2_norm_dense(vec)
    if norm <= 1e-12:
        return [0.0 for _ in vec]
    return [v / norm for v in vec]


def _build_tfidf_index_from_docs(docs: list[ChunkDoc]) -> VecIndex:
    n_docs = len(docs)
    if n_docs == 0:
        return VecIndex(docs=[], idf={}, doc_vectors=[], doc_norms=[], index_type="tfidf")

    tokenized = [tokenize(d.clean_text) for d in docs]
    df: dict[str, int] = {}
    for toks in tokenized:
        seen = set(toks)
        for term in seen:
            df[term] = df.get(term, 0) + 1

    idf = {term: math.log((n_docs + 1) / (term_df + 1)) + 1.0 for term, term_df in df.items()}
    doc_vectors = [_to_tfidf(toks, idf) for toks in tokenized]
    doc_norms = [_norm(v) for v in doc_vectors]

    return VecIndex(
        docs=[VecDoc(**asdict(d)) for d in docs],
        idf=idf,
        doc_vectors=doc_vectors,
        doc_norms=doc_norms,
        index_type="tfidf",
    )


def _normalize_text_for_hash(text: str) -> str:
    return " ".join((text or "").strip().split())


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_embedding_cache(
    cache_path: str | Path,
    *,
    provider: str,
    model: str,
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    path = Path(cache_path)
    if not path.exists():
        return {}, {}

    by_hash: dict[str, list[float]] = {}
    legacy_by_chunk: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            row_model = str(row.get("model", "")).strip()
            if row_model != model:
                continue
            row_provider = str(row.get("provider", provider)).strip()
            if row_provider != provider:
                continue

            emb = row.get("embedding")
            if not isinstance(emb, list):
                continue
            try:
                vec = [float(x) for x in emb]
            except (TypeError, ValueError):
                continue

            text_hash = str(row.get("normalized_text_hash", "")).strip()
            if text_hash:
                by_hash[text_hash] = vec
                continue

            chunk_id = str(row.get("chunk_id", "")).strip()
            if chunk_id:
                legacy_by_chunk[chunk_id] = vec

    return by_hash, legacy_by_chunk


def _append_jsonl_rows(path_like: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path = Path(path_like)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_embedding_cache(cache_path: str | Path, rows: list[dict[str, Any]]) -> None:
    _append_jsonl_rows(cache_path, rows)


def _append_embedding_failures(failure_path: str | Path, rows: list[dict[str, Any]]) -> None:
    _append_jsonl_rows(failure_path, rows)


def _is_recoverable_error(exc: EmbeddingAPIError) -> bool:
    if exc.recoverable:
        return True
    if exc.status_code == 429:
        return True
    if exc.status_code is not None and 500 <= exc.status_code <= 599:
        return True
    if exc.category in {"network_error", "rate_limit", "server_error"}:
        return True
    lowered = (exc.message or "").lower()
    if "429" in lowered or "rate limit" in lowered:
        return True
    if "timeout" in lowered or "temporarily unavailable" in lowered:
        return True
    return False


def _backoff_sleep_ms(attempt_idx: int, cfg: EmbeddingConfig) -> int:
    base_ms = max(1, int(cfg.backoff_base_ms))
    max_ms = max(base_ms, int(cfg.backoff_max_ms))
    sleep_ms = min(max_ms, base_ms * (2 ** max(0, attempt_idx)))
    time.sleep(sleep_ms / 1000.0)
    return sleep_ms


def _fetch_with_guard(
    texts: list[str],
    cfg: EmbeddingConfig,
    *,
    rate_limiter: _RateLimiter,
    semaphore: threading.Semaphore,
) -> list[list[float]]:
    rate_limiter.wait_for_slot()
    with semaphore:
        return fetch_embeddings(
            texts,
            base_url=cfg.base_url,
            model=cfg.model,
            api_key_env=cfg.api_key_env,
        )


def _record_id_limited(bucket: list[str], value: str, limit: int) -> None:
    if not value:
        return
    if len(bucket) < max(1, limit):
        bucket.append(value)


def _embed_single_item(
    item: _EmbeddingWorkItem,
    cfg: EmbeddingConfig,
    *,
    rate_limiter: _RateLimiter,
    semaphore: threading.Semaphore,
) -> tuple[list[float] | None, EmbeddingAPIError | None, int, int, int, int]:
    attempts = max(0, int(cfg.max_retries)) + 1
    last_exc: EmbeddingAPIError | None = None
    api_calls = 0
    rate_limited_count = 0
    backoff_total_ms = 0

    for attempt in range(attempts):
        try:
            vectors = _fetch_with_guard(item.texts, cfg, rate_limiter=rate_limiter, semaphore=semaphore)
            api_calls += 1
            if not vectors:
                raise EmbeddingAPIError("Embedding API returned empty vectors", category="invalid_response")
            if len(item.texts) == 1:
                return vectors[0], None, attempt, api_calls, rate_limited_count, backoff_total_ms
            # split strategy: mean pooling
            dim = len(vectors[0])
            if any(len(v) != dim for v in vectors):
                raise EmbeddingAPIError("split embedding dim mismatch", category="invalid_response")
            merged = [0.0] * dim
            for vec in vectors:
                for i, val in enumerate(vec):
                    merged[i] += float(val)
            merged = [v / len(vectors) for v in merged]
            return merged, None, attempt, api_calls, rate_limited_count, backoff_total_ms
        except EmbeddingAPIError as exc:
            api_calls += 1
            last_exc = exc
            if exc.status_code == 429:
                rate_limited_count += 1
            if not _is_recoverable_error(exc):
                return None, exc, attempt, api_calls, rate_limited_count, backoff_total_ms
            if attempt >= attempts - 1:
                return None, exc, attempt, api_calls, rate_limited_count, backoff_total_ms
            backoff_total_ms += _backoff_sleep_ms(attempt, cfg)

    return None, last_exc, max(0, attempts - 1), api_calls, rate_limited_count, backoff_total_ms


def build_embedding_vec_index(
    chunks_path: str | Path = "data/processed/chunks_clean.jsonl",
    output_path: str | Path = "data/indexes/vec_index_embed.json",
    *,
    embedding_cfg: EmbeddingConfig,
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> tuple[VecIndex, EmbeddingBuildStats]:
    build_started = time.perf_counter()
    docs = load_chunks_clean(chunks_path, filter_watermark=True, filter_suppressed=True)
    vec_docs = [VecDoc(**asdict(d)) for d in docs]
    stats = EmbeddingBuildStats()

    cache_by_hash: dict[str, list[float]] = {}
    cache_legacy: dict[str, list[float]] = {}
    if embedding_cfg.cache_enabled:
        cache_by_hash, cache_legacy = _load_embedding_cache(
            embedding_cfg.cache_path,
            provider=embedding_cfg.provider,
            model=embedding_cfg.model,
        )

    embeddings: list[list[float]] = [[] for _ in vec_docs]
    pending: list[_EmbeddingWorkItem] = []
    failed_indices: list[int] = []

    max_tokens = max(1, int(embedding_cfg.max_tokens_per_chunk))
    strategy = embedding_cfg.over_limit_strategy

    for i, doc in enumerate(vec_docs):
        normalized = _normalize_text_for_hash(doc.clean_text)
        if not normalized:
            stats.skipped_empty += 1
            _record_id_limited(stats.skipped_empty_chunk_ids, doc.chunk_id, embedding_cfg.max_skipped_chunk_ids)
            failed_indices.append(i)
            continue

        tokenized = tokenize(normalized)
        if not tokenized:
            stats.skipped_empty += 1
            _record_id_limited(stats.skipped_empty_chunk_ids, doc.chunk_id, embedding_cfg.max_skipped_chunk_ids)
            failed_indices.append(i)
            continue

        texts: list[str] = [" ".join(tokenized)]
        if len(tokenized) > max_tokens:
            if strategy == "truncate":
                tokenized = tokenized[:max_tokens]
                texts = [" ".join(tokenized)]
                stats.truncated_count += 1
            elif strategy == "split":
                texts = [" ".join(tokenized[j : j + max_tokens]) for j in range(0, len(tokenized), max_tokens)]
                texts = [x for x in texts if x]
            else:
                stats.skipped_over_limit_count += 1
                failed_indices.append(i)
                continue

        if not texts:
            stats.skipped_over_limit_count += 1
            failed_indices.append(i)
            continue

        hash_source = "\n".join(texts)
        text_hash = _hash_text(hash_source)
        cached = cache_by_hash.get(text_hash)
        if cached is None:
            cached = cache_legacy.get(doc.chunk_id)

        if cached is not None:
            stats.cache_hits += 1
            embeddings[i] = _normalize_dense(cached) if embedding_cfg.normalize else list(cached)
            continue

        stats.cache_miss += 1
        pending.append(_EmbeddingWorkItem(idx=i, doc=doc, texts=texts, normalized_text_hash=text_hash))

    total_docs = len(vec_docs)
    processed = stats.cache_hits + stats.skipped_empty + stats.skipped_over_limit_count
    if progress_callback:
        progress_callback(processed, total_docs)

    new_cache_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []

    def _flush_buffers() -> None:
        nonlocal new_cache_rows, failure_rows
        if embedding_cfg.cache_enabled and new_cache_rows:
            _append_embedding_cache(embedding_cfg.cache_path, new_cache_rows)
            new_cache_rows = []
        if failure_rows:
            _append_embedding_failures(embedding_cfg.failure_log_path, failure_rows)
            stats.failure_records_written += len(failure_rows)
            failure_rows = []

    rate_limiter = _RateLimiter(max(1, int(embedding_cfg.max_requests_per_minute)))
    semaphore = threading.Semaphore(max(1, int(embedding_cfg.max_concurrent_requests)))

    batch_size = max(1, int(embedding_cfg.batch_size))

    single_items = [x for x in pending if len(x.texts) == 1]
    split_items = [x for x in pending if len(x.texts) > 1]
    total_batches = (len(single_items) + batch_size - 1) // batch_size if single_items else 0

    def _process_single_batch(batch: list[_EmbeddingWorkItem], batch_idx: int) -> _EmbeddingTaskResult:
        result = _EmbeddingTaskResult()
        texts = [it.texts[0] for it in batch]
        try:
            vectors = _fetch_with_guard(texts, embedding_cfg, rate_limiter=rate_limiter, semaphore=semaphore)
            result.api_calls += 1
            if len(vectors) != len(batch):
                raise EmbeddingAPIError(
                    f"batch response size mismatch: expected {len(batch)}, got {len(vectors)}",
                    category="invalid_response",
                )
            for item, vec in zip(batch, vectors):
                normed = _normalize_dense(vec) if embedding_cfg.normalize else vec
                result.succeeded.append((item, normed))
                if embedding_cfg.cache_enabled:
                    result.cache_rows.append(
                        {
                            "chunk_id": item.doc.chunk_id,
                            "provider": embedding_cfg.provider,
                            "model": embedding_cfg.model,
                            "normalized_text_hash": item.normalized_text_hash,
                            "embedding": vec,
                        }
                    )
            return result
        except EmbeddingAPIError as exc:
            result.api_calls += 1
            if exc.status_code == 429:
                result.rate_limited_count += 1
            result.batch_failures.append(
                {
                    "batch_index": int(batch_idx),
                    "batch_total": int(max(1, total_batches)),
                    "count": int(len(batch)),
                    "status_code": exc.status_code,
                    "trace_id": exc.trace_id,
                    "response_body": (exc.response_body[:1000] if exc.response_body else None),
                    "error_category": exc.category,
                }
            )
            result.status_messages.append(
                f"batch {batch_idx}/{max(1, total_batches)} failed: status={exc.status_code} "
                f"trace_id={exc.trace_id or '-'}; fallback to per-item"
            )
            for item in batch:
                vec, err, retries, api_calls, rate_limited, backoff_ms = _embed_single_item(
                    item,
                    embedding_cfg,
                    rate_limiter=rate_limiter,
                    semaphore=semaphore,
                )
                result.api_calls += api_calls
                result.rate_limited_count += rate_limited
                result.backoff_total_ms += backoff_ms
                if vec is None:
                    result.failed.append((item, err, retries))
                    result.failure_rows.append(
                        {
                            "chunk_id": item.doc.chunk_id,
                            "provider": embedding_cfg.provider,
                            "model": embedding_cfg.model,
                            "normalized_text_hash": item.normalized_text_hash,
                            "error": str(err.message if err else "embedding_request_failed"),
                            "error_category": (err.category if err else "unknown"),
                            "recoverable": bool(err.recoverable) if err else False,
                            "retries": int(retries),
                            "status_code": (err.status_code if err else None),
                            "response_body": (err.response_body[:1000] if err and err.response_body else None),
                            "trace_id": (err.trace_id if err else None),
                        }
                    )
                    continue
                normed = _normalize_dense(vec) if embedding_cfg.normalize else vec
                result.succeeded.append((item, normed))
                if embedding_cfg.cache_enabled:
                    result.cache_rows.append(
                        {
                            "chunk_id": item.doc.chunk_id,
                            "provider": embedding_cfg.provider,
                            "model": embedding_cfg.model,
                            "normalized_text_hash": item.normalized_text_hash,
                            "embedding": vec,
                        }
                    )
            return result

    def _process_split_item(item: _EmbeddingWorkItem) -> _EmbeddingTaskResult:
        result = _EmbeddingTaskResult()
        vec, err, retries, api_calls, rate_limited, backoff_ms = _embed_single_item(
            item,
            embedding_cfg,
            rate_limiter=rate_limiter,
            semaphore=semaphore,
        )
        result.api_calls += api_calls
        result.rate_limited_count += rate_limited
        result.backoff_total_ms += backoff_ms
        if vec is None:
            result.failed.append((item, err, retries))
            result.failure_rows.append(
                {
                    "chunk_id": item.doc.chunk_id,
                    "provider": embedding_cfg.provider,
                    "model": embedding_cfg.model,
                    "normalized_text_hash": item.normalized_text_hash,
                    "error": str(err.message if err else "embedding_request_failed"),
                    "error_category": (err.category if err else "unknown"),
                    "recoverable": bool(err.recoverable) if err else False,
                    "retries": int(retries),
                    "status_code": (err.status_code if err else None),
                    "response_body": (err.response_body[:1000] if err and err.response_body else None),
                    "trace_id": (err.trace_id if err else None),
                }
            )
            return result
        normed = _normalize_dense(vec) if embedding_cfg.normalize else vec
        result.succeeded.append((item, normed))
        if embedding_cfg.cache_enabled:
            result.cache_rows.append(
                {
                    "chunk_id": item.doc.chunk_id,
                    "provider": embedding_cfg.provider,
                    "model": embedding_cfg.model,
                    "normalized_text_hash": item.normalized_text_hash,
                    "embedding": vec,
                }
            )
        return result

    try:
        max_workers = max(1, int(embedding_cfg.max_concurrent_requests))
        if single_items:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for start in range(0, len(single_items), batch_size):
                    batch = single_items[start : start + batch_size]
                    batch_idx = (start // batch_size) + 1
                    if status_callback:
                        status_callback(
                            f"requesting embedding batch {batch_idx}/{max(1, total_batches)} "
                            f"(size={len(batch)}, concurrent={max_workers})"
                        )
                    futures.append(executor.submit(_process_single_batch, batch, batch_idx))

                for fut in as_completed(futures):
                    result = fut.result()
                    stats.api_calls += result.api_calls
                    stats.rate_limited_count += result.rate_limited_count
                    stats.backoff_total_ms += result.backoff_total_ms
                    stats.embedding_batch_failures.extend(result.batch_failures)
                    for msg in result.status_messages:
                        if status_callback:
                            status_callback(msg)
                    for item, vec in result.succeeded:
                        embeddings[item.idx] = vec
                    for item, err, retries in result.failed:
                        stats.failed_items += 1
                        _record_id_limited(
                            stats.embedding_failed_chunk_ids, item.doc.chunk_id, embedding_cfg.max_failed_chunk_ids
                        )
                        failed_indices.append(item.idx)
                    new_cache_rows.extend(result.cache_rows)
                    failure_rows.extend(result.failure_rows)
                    processed += len(result.succeeded) + len(result.failed)
                    _flush_buffers()
                    if progress_callback:
                        progress_callback(processed, total_docs)

        if split_items and status_callback:
            status_callback(f"processing split-over-limit items: {len(split_items)}")
        if split_items:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_process_split_item, item) for item in split_items]
                for fut in as_completed(futures):
                    result = fut.result()
                    stats.api_calls += result.api_calls
                    stats.rate_limited_count += result.rate_limited_count
                    stats.backoff_total_ms += result.backoff_total_ms
                    for item, vec in result.succeeded:
                        embeddings[item.idx] = vec
                    for item, err, retries in result.failed:
                        stats.failed_items += 1
                        _record_id_limited(
                            stats.embedding_failed_chunk_ids, item.doc.chunk_id, embedding_cfg.max_failed_chunk_ids
                        )
                        failed_indices.append(item.idx)
                    new_cache_rows.extend(result.cache_rows)
                    failure_rows.extend(result.failure_rows)
                    processed += len(result.succeeded) + len(result.failed)
                    _flush_buffers()
                    if progress_callback:
                        progress_callback(processed, total_docs)
    finally:
        _flush_buffers()

    dim = 0
    for vec in embeddings:
        if vec:
            dim = len(vec)
            break
    if dim == 0:
        dim = 1

    for idx in failed_indices:
        embeddings[idx] = [0.0] * dim
    for vec in embeddings:
        if vec and len(vec) != dim:
            raise ValueError(f"Embedding dimension mismatch: expected {dim}, got {len(vec)}")

    build_time_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    index = VecIndex(
        docs=vec_docs,
        idf={},
        doc_vectors=[],
        doc_norms=[],
        index_type="embedding",
        embedding_provider=embedding_cfg.provider,
        embedding_model=embedding_cfg.model,
        embedding_dim=dim,
        embedding_build_time=build_time_iso,
        embeddings=embeddings,
    )
    save_vec_index(index, output_path)

    stats.build_time_ms = int((time.perf_counter() - build_started) * 1000)
    return index, stats


def build_vec_index(
    chunks_path: str | Path = "data/processed/chunks_clean.jsonl",
    output_path: str | Path = "data/indexes/vec_index.json",
) -> VecIndex:
    docs = load_chunks_clean(chunks_path, filter_watermark=True, filter_suppressed=True)
    index = _build_tfidf_index_from_docs(docs)
    save_vec_index(index, output_path)
    return index


def save_vec_index(index: VecIndex, output_path: str | Path) -> None:
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if index.index_type == "embedding":
        payload = {
            "index_type": "embedding",
            "embedding_provider": index.embedding_provider,
            "embedding_model": index.embedding_model,
            "embedding_dim": index.embedding_dim,
            "build_time": index.embedding_build_time,
            "docs": [
                {
                    "chunk_id": d.chunk_id,
                    "paper_id": d.paper_id,
                    "content_type": d.content_type,
                    "page": d.page_start,
                    "page_start": d.page_start,
                    "section": d.section,
                    "text": d.text,
                    "clean_text": d.clean_text,
                    "embedding": (index.embeddings[i] if index.embeddings else []),
                }
                for i, d in enumerate(index.docs)
            ],
        }
    else:
        payload = {
            "docs": [asdict(d) for d in index.docs],
            "idf": index.idf,
            "doc_vectors": index.doc_vectors,
            "doc_norms": index.doc_norms,
            "index_type": "tfidf",
        }
    dst.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_vec_index(index_path: str | Path = "data/indexes/vec_index.json") -> VecIndex:
    src = Path(index_path)
    if not src.exists():
        raise FileNotFoundError(f"vector index not found: {src}")
    payload = json.loads(src.read_text(encoding="utf-8"))

    if payload.get("index_type") == "embedding" or (
        "embedding_provider" in payload and "embedding_model" in payload
    ):
        docs_raw = payload.get("docs", [])
        docs: list[VecDoc] = []
        embs: list[list[float]] = []
        for row in docs_raw:
            docs.append(
                VecDoc(
                    chunk_id=str(row.get("chunk_id", "")),
                    paper_id=str(row.get("paper_id", "")),
                    page_start=int(row.get("page_start", row.get("page", 0))),
                    section=row.get("section"),
                    text=str(row.get("text", "")),
                    clean_text=str(row.get("clean_text", "")),
                    content_type=str(row.get("content_type", "body")),
                )
            )
            emb = row.get("embedding", [])
            embs.append([float(x) for x in emb])
        return VecIndex(
            docs=docs,
            idf={},
            doc_vectors=[],
            doc_norms=[],
            index_type="embedding",
            embedding_provider=str(payload.get("embedding_provider", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            embedding_dim=int(payload.get("embedding_dim", 0)),
            embedding_build_time=str(payload.get("build_time", "")),
            embeddings=embs,
        )

    return VecIndex(
        docs=[VecDoc(**d) for d in payload.get("docs", [])],
        idf={k: float(v) for k, v in payload.get("idf", {}).items()},
        doc_vectors=[{k: float(v) for k, v in vec.items()} for vec in payload.get("doc_vectors", [])],
        doc_norms=[float(x) for x in payload.get("doc_norms", [])],
        index_type=str(payload.get("index_type", "tfidf")),
    )


def search_vec(index: VecIndex, query: str, top_k: int = 20) -> list[tuple[VecDoc, float]]:
    if index.index_type != "tfidf":
        raise ValueError("search_vec supports tfidf index only; use search_vec_with_query_embedding for embedding indexes")

    q_tokens = tokenize(query)
    if not q_tokens or not index.docs:
        return []
    q_vec = _to_tfidf(q_tokens, index.idf)
    q_norm = _norm(q_vec)
    if q_norm == 0:
        return []

    scores: list[tuple[int, float]] = []
    for i, d_vec in enumerate(index.doc_vectors):
        denom = q_norm * max(1e-12, index.doc_norms[i])
        if denom == 0:
            continue
        dot = 0.0
        smaller, larger = (q_vec, d_vec) if len(q_vec) < len(d_vec) else (d_vec, q_vec)
        for term, value in smaller.items():
            dot += value * larger.get(term, 0.0)
        score = dot / denom
        if score > 0:
            scores.append((i, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [(index.docs[i], s) for i, s in scores[:top_k]]


def search_vec_with_query_embedding(
    index: VecIndex,
    query_embedding: list[float],
    *,
    top_k: int = 20,
    normalize_query: bool = True,
) -> list[tuple[VecDoc, float]]:
    if index.index_type != "embedding":
        raise ValueError("search_vec_with_query_embedding requires embedding index")
    if not index.docs or not query_embedding:
        return []

    q = _normalize_dense(query_embedding) if normalize_query else query_embedding
    embeddings = index.embeddings or []
    if index.embedding_dim and len(q) != index.embedding_dim:
        raise ValueError(f"Query embedding dim mismatch: expected {index.embedding_dim}, got {len(q)}")

    scores: list[tuple[int, float]] = []
    for i, emb in enumerate(embeddings):
        if not emb:
            continue
        if len(emb) != len(q):
            continue
        score = sum(a * b for a, b in zip(emb, q))
        if score > 0:
            scores.append((i, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [(index.docs[i], s) for i, s in scores[:top_k]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build lightweight vector index from chunks_clean.jsonl")
    parser.add_argument("--input", default="data/processed/chunks_clean.jsonl", help="Input chunks_clean.jsonl path")
    parser.add_argument("--out", default="data/indexes/vec_index.json", help="Output vector index path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    index = build_vec_index(args.input, args.out)
    print(f"Vector index built: {len(index.docs)} docs")
    print(f"Output: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
