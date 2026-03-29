from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import load_config
from app.config_governance import load_resolved_llm_stage


DEFAULT_LLM_SYSTEM_PROMPT = (
    "You extract entities from academic text. "
    "Return only strict JSON with top-level key 'entities'. "
    "Each entity must include 'entity_name' and 'entity_type'."
)


@dataclass
class GraphNode:
    chunk_id: str
    paper_id: str
    page_start: int
    section: str | None
    content_type: str
    entities: list[str]


@dataclass
class GraphBuildStats:
    input_total: int = 0
    kept_nodes: int = 0
    excluded_suppressed: int = 0
    excluded_watermark: int = 0
    excluded_front_matter: int = 0
    adjacent_edges_undirected: int = 0
    entity_edges_directed: int = 0
    entity_pairs_above_threshold: int = 0
    entity_neighbors_clipped: int = 0
    entity_empty_chunks: int = 0
    llm_entity_calls: int = 0
    llm_entity_failures: int = 0
    llm_entity_rate_limits: int = 0
    llm_entity_retries: int = 0
    llm_entity_fallback_empty: int = 0
    llm_entity_elapsed_ms: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class ChunkGraph:
    """论文 chunk 图的内存表示与查询接口。"""

    def __init__(
        self,
        *,
        nodes: dict[str, GraphNode],
        adjacent: dict[str, list[str]],
        entity: dict[str, list[tuple[str, int]]],
        stats: GraphBuildStats,
        config: dict[str, Any],
    ) -> None:
        self.nodes = nodes
        self.adjacent = adjacent
        self.entity = entity
        self.stats = stats
        self.config = config

    def neighbors(self, chunk_id: str, type: str = "adjacent", hop: int = 1) -> list[str]:
        """查询指定节点在指定边类型下的 hop 邻居。"""
        if hop < 1 or chunk_id not in self.nodes:
            return []
        graph = self._graph_for_type(type)
        if graph is None:
            return []
        if hop == 1:
            return list(graph.get(chunk_id, []))

        visited = {chunk_id}
        q: deque[tuple[str, int]] = deque([(chunk_id, 0)])
        out: set[str] = set()
        while q:
            current, depth = q.popleft()
            if depth == hop:
                continue
            for nxt in graph.get(current, []):
                if nxt in visited:
                    continue
                visited.add(nxt)
                out.add(nxt)
                q.append((nxt, depth + 1))
        return sorted(out)

    def neighbors_with_weight(
        self,
        chunk_id: str,
        type: str = "entity",
        hop: int = 1,
    ) -> list[dict[str, Any]]:
        """查询邻居并返回权重与边类型。adjacent 权重固定为 1。"""
        if hop != 1 or chunk_id not in self.nodes:
            return []
        if type == "adjacent":
            return [
                {"chunk_id": nid, "weight": 1, "edge_type": "adjacent"}
                for nid in self.adjacent.get(chunk_id, [])
            ]
        if type == "entity":
            return [
                {"chunk_id": nid, "weight": weight, "edge_type": "entity"}
                for nid, weight in self.entity.get(chunk_id, [])
            ]
        return []

    def _graph_for_type(self, edge_type: str) -> dict[str, list[str]] | None:
        if edge_type == "adjacent":
            return self.adjacent
        if edge_type == "entity":
            return {k: [nid for nid, _ in v] for k, v in self.entity.items()}
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": {
                "stats": self.stats.to_dict(),
                "config": self.config,
            },
            "nodes": {cid: asdict(node) for cid, node in self.nodes.items()},
            "adjacent": self.adjacent,
            "entity": {
                cid: [
                    {"chunk_id": nid, "weight": weight}
                    for nid, weight in neighbors
                ]
                for cid, neighbors in self.entity.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkGraph":
        nodes_raw = data.get("nodes", {})
        nodes: dict[str, GraphNode] = {}
        for cid, node in nodes_raw.items():
            nodes[cid] = GraphNode(
                chunk_id=str(node.get("chunk_id", cid)),
                paper_id=str(node.get("paper_id", "")),
                page_start=int(node.get("page_start", 0)),
                section=node.get("section"),
                content_type=str(node.get("content_type", "body")),
                entities=[str(x) for x in node.get("entities", [])],
            )

        adjacent = {
            str(cid): [str(x) for x in neighbors]
            for cid, neighbors in data.get("adjacent", {}).items()
        }
        entity = {
            str(cid): [
                (str(item.get("chunk_id", "")), int(item.get("weight", 1)))
                for item in neighbors
            ]
            for cid, neighbors in data.get("entity", {}).items()
        }
        stats_data = data.get("meta", {}).get("stats", {})
        stats = GraphBuildStats(**{k: int(v) for k, v in stats_data.items() if k in GraphBuildStats.__annotations__})
        config = data.get("meta", {}).get("config", {})
        return cls(nodes=nodes, adjacent=adjacent, entity=entity, stats=stats, config=config)


@dataclass
class LLMEntityExtractionConfig:
    provider: str = "siliconflow"
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key_env: str = "SILICONFLOW_API_KEY"
    api_key: str = ""
    model: str = "Pro/deepseek-ai/DeepSeek-V3.2"
    timeout_ms: int = 12000
    max_concurrency: int = 4
    max_retries: int = 1


@dataclass
class LLMExtractionMetrics:
    calls: int = 0
    failures: int = 0
    rate_limits: int = 0
    retries: int = 0
    fallback_empty: int = 0
    elapsed_ms: int = 0


class EntityExtractionItem(BaseModel):
    entity_name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)


class EntityExtractionResult(BaseModel):
    entities: list[EntityExtractionItem] = Field(default_factory=list)


EntityExtractor = Callable[[str, LLMEntityExtractionConfig], Awaitable[EntityExtractionResult]]
ProgressCallback = Callable[[dict[str, Any]], None]



def _chunk_sort_key(chunk_id: str) -> tuple[str, int]:
    if ":" not in chunk_id:
        return chunk_id, 0
    prefix, suffix = chunk_id.rsplit(":", 1)
    try:
        idx = int(suffix)
    except ValueError:
        idx = 0
    return prefix, idx



def _chat_completions_endpoint(base_url: str, provider: str = "siliconflow") -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        normalized = str(provider or "").strip().lower()
        if normalized == "openai":
            return "https://api.openai.com/v1/chat/completions"
        if normalized == "ollama":
            return "http://127.0.0.1:11434/v1/chat/completions"
        if normalized == "siliconflow":
            return "https://api.siliconflow.cn/v1/chat/completions"
        return "https://api.siliconflow.cn/v1/chat/completions"
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _load_api_key(api_key_env: str, api_key: str = "") -> str:
    if str(api_key or "").strip():
        return str(api_key).strip()
    return str(os.getenv(api_key_env, "")).strip()


def _sanitize_entities(payload: EntityExtractionResult) -> list[str]:
    names: list[str] = []
    for item in payload.entities:
        name = str(item.entity_name).strip()
        if name and name not in names:
            names.append(name)
    return names


async def extract_entities_from_text_llm(
    clean_text: str,
    cfg: LLMEntityExtractionConfig,
    *,
    client: httpx.AsyncClient | None = None,
    metrics: LLMExtractionMetrics | None = None,
    on_failure: Callable[[str, str | None], None] | None = None,
) -> EntityExtractionResult:
    if not clean_text.strip():
        return EntityExtractionResult()

    api_key = _load_api_key(cfg.api_key_env, cfg.api_key)
    if not api_key:
        if metrics is not None:
            metrics.failures += 1
            metrics.fallback_empty += 1
        if on_failure is not None:
            on_failure("missing_api_key", f"env={cfg.api_key_env}")
        return EntityExtractionResult()

    prompt = (
        "Extract entities from the following text. "
        "Return only JSON in this shape: "
        '{"entities":[{"entity_name":"...","entity_type":"..."}]}.'
        f"\n\nText:\n{clean_text}"
    )
    payload = {
        "model": cfg.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": DEFAULT_LLM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    endpoint = _chat_completions_endpoint(cfg.base_url, cfg.provider)
    timeout_s = max(0.1, float(cfg.timeout_ms) / 1000.0)
    own_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout_s)

    try:
        for attempt in range(max(0, int(cfg.max_retries)) + 1):
            if metrics is not None:
                metrics.calls += 1
            t0 = time.perf_counter()
            try:
                response = await active_client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if metrics is not None:
                    metrics.elapsed_ms += int((time.perf_counter() - t0) * 1000)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt < max(0, int(cfg.max_retries)):
                    if metrics is not None:
                        metrics.retries += 1
                    await asyncio.sleep(min(0.5 * (2 ** attempt), 4.0))
                    continue
                if metrics is not None:
                    metrics.failures += 1
                    metrics.fallback_empty += 1
                if on_failure is not None:
                    on_failure("timeout_or_transport", "request timeout/transport after retries")
                return EntityExtractionResult()

            if response.status_code == 429:
                if metrics is not None:
                    metrics.rate_limits += 1
                if attempt < max(0, int(cfg.max_retries)):
                    if metrics is not None:
                        metrics.retries += 1
                    await asyncio.sleep(min(0.8 * (2 ** attempt), 6.0))
                    continue
                if metrics is not None:
                    metrics.failures += 1
                    metrics.fallback_empty += 1
                if on_failure is not None:
                    on_failure("http_429", "rate limited after retries")
                return EntityExtractionResult()

            if response.status_code >= 400:
                if metrics is not None:
                    metrics.failures += 1
                    metrics.fallback_empty += 1
                if on_failure is not None:
                    on_failure(f"http_{response.status_code}", response.text[:200])
                return EntityExtractionResult()

            try:
                data = response.json()
                choices = data.get("choices", []) if isinstance(data, dict) else []
                first = choices[0] if isinstance(choices, list) and choices else {}
                message = first.get("message", {}) if isinstance(first, dict) else {}
                content = message.get("content") if isinstance(message, dict) else ""
                raw_json: Any
                if isinstance(content, dict):
                    raw_json = content
                else:
                    raw_json = json.loads(str(content or "{}"))
                return EntityExtractionResult.model_validate(raw_json)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                if attempt < max(0, int(cfg.max_retries)):
                    if metrics is not None:
                        metrics.retries += 1
                    await asyncio.sleep(min(0.4 * (2 ** attempt), 3.0))
                    continue
                if metrics is not None:
                    metrics.failures += 1
                    metrics.fallback_empty += 1
                if on_failure is not None:
                    on_failure("invalid_json_or_schema", "model payload is not valid JSON schema")
                return EntityExtractionResult()
        if metrics is not None:
            metrics.failures += 1
            metrics.fallback_empty += 1
        if on_failure is not None:
            on_failure("unknown_failure", "extraction failed without explicit branch")
        return EntityExtractionResult()
    finally:
        if own_client:
            await active_client.aclose()


async def extract_entities_for_chunks_async(
    chunk_inputs: list[tuple[str, str]],
    cfg: LLMEntityExtractionConfig,
    *,
    extractor: EntityExtractor | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    collect_failures: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, list[str]], LLMExtractionMetrics]:
    out: dict[str, list[str]] = {}
    metrics = LLMExtractionMetrics()
    if not chunk_inputs:
        return out, metrics

    sem = asyncio.Semaphore(max(1, int(cfg.max_concurrency)))
    use_extractor = extractor or extract_entities_from_text_llm

    async def _one(chunk_id: str, clean_text: str) -> tuple[str, list[str]]:
        async with sem:
            failure_recorded = False

            def _record_failure(reason: str, detail: str | None) -> None:
                nonlocal failure_recorded
                failure_recorded = True
                if collect_failures is None:
                    return
                collect_failures.append(
                    {
                        "chunk_id": chunk_id,
                        "reason": reason,
                        "detail": detail or "",
                        "text_len": len(clean_text),
                    }
                )

            try:
                if extractor is None:
                    result = await extract_entities_from_text_llm(clean_text, cfg, metrics=metrics, on_failure=_record_failure)
                else:
                    result = await use_extractor(clean_text, cfg)
                if isinstance(result, EntityExtractionResult):
                    validated = result
                else:
                    validated = EntityExtractionResult.model_validate(result)
                return chunk_id, _sanitize_entities(validated)
            except Exception:
                metrics.failures += 1
                metrics.fallback_empty += 1
                if not failure_recorded:
                    _record_failure("extractor_exception", "unexpected exception in extractor")
                return chunk_id, []

    started = time.perf_counter()
    tasks = [_one(cid, text) for cid, text in chunk_inputs]
    total = len(tasks)
    processed = 0
    for future in asyncio.as_completed(tasks):
        item = await future
        processed += 1
        if on_progress is not None:
            on_progress(processed, total)
        if isinstance(item, BaseException):
            metrics.failures += 1
            metrics.fallback_empty += 1
            continue
        chunk_id, entities = item
        out[chunk_id] = entities
    metrics.elapsed_ms += int((time.perf_counter() - started) * 1000)
    return out, metrics


def extract_entities_for_chunks(
    chunk_inputs: list[tuple[str, str]],
    cfg: LLMEntityExtractionConfig,
    *,
    extractor: EntityExtractor | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    collect_failures: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, list[str]], LLMExtractionMetrics]:
    return asyncio.run(
        extract_entities_for_chunks_async(
            chunk_inputs,
            cfg,
            extractor=extractor,
            on_progress=on_progress,
            collect_failures=collect_failures,
        )
    )



def load_chunk_rows(path: str | Path) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"chunks file not found: {src}")
    rows: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows



def build_graph(
    rows: list[dict[str, Any]],
    *,
    entity_overlap_threshold: int = 1,
    entity_top_m: int = 30,
    include_front_matter: bool = False,
    llm_entity_config: LLMEntityExtractionConfig | None = None,
    llm_entity_extractor: EntityExtractor | None = None,
    on_progress: ProgressCallback | None = None,
    llm_failure_records_out: list[dict[str, Any]] | None = None,
) -> ChunkGraph:
    started = time.perf_counter()
    if on_progress is not None:
        on_progress(
            {
                "stage": "load_rows",
                "processed": 0,
                "total": len(rows),
                "elapsed_ms": 0,
                "message": "已加载输入 rows",
            }
        )
    stats = GraphBuildStats(input_total=len(rows))

    nodes: dict[str, GraphNode] = {}
    by_paper: dict[str, list[GraphNode]] = defaultdict(list)

    pending_llm_chunks: list[tuple[str, str]] = []
    pending_llm_ids: set[str] = set()
    for row in rows:
        suppressed = bool(row.get("suppressed", False))
        content_type = str(row.get("content_type", "body"))
        if suppressed or content_type == "watermark":
            continue
        if not include_front_matter and content_type == "front_matter":
            continue
        chunk_id = str(row.get("chunk_id", "")).strip()
        if not chunk_id:
            continue
        if "entities" not in row:
            clean_text = str(row.get("clean_text", ""))
            pending_llm_chunks.append((chunk_id, clean_text))
            pending_llm_ids.add(chunk_id)
    if on_progress is not None:
        on_progress(
            {
                "stage": "filter_rows",
                "processed": len(rows),
                "total": len(rows),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "message": f"筛选完成，待抽取实体 chunk 数={len(pending_llm_chunks)}",
            }
        )

    llm_entities_by_chunk: dict[str, list[str]] = {}
    if pending_llm_chunks:
        llm_cfg = llm_entity_config or LLMEntityExtractionConfig()
        llm_entities_by_chunk, llm_metrics = extract_entities_for_chunks(
            pending_llm_chunks,
            llm_cfg,
            extractor=llm_entity_extractor,
            collect_failures=llm_failure_records_out,
            on_progress=(
                (lambda processed, total: on_progress(
                    {
                        "stage": "extract_entities",
                        "processed": processed,
                        "total": total,
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "message": f"实体抽取进行中 {processed}/{total}",
                    }
                ))
                if on_progress is not None
                else None
            ),
        )
        stats.llm_entity_calls += llm_metrics.calls
        stats.llm_entity_failures += llm_metrics.failures
        stats.llm_entity_rate_limits += llm_metrics.rate_limits
        stats.llm_entity_retries += llm_metrics.retries
        stats.llm_entity_fallback_empty += llm_metrics.fallback_empty
        stats.llm_entity_elapsed_ms += llm_metrics.elapsed_ms

    for row in rows:
        suppressed = bool(row.get("suppressed", False))
        content_type = str(row.get("content_type", "body"))
        if suppressed:
            stats.excluded_suppressed += 1
            continue
        if content_type == "watermark":
            stats.excluded_watermark += 1
            continue
        if not include_front_matter and content_type == "front_matter":
            stats.excluded_front_matter += 1
            continue

        chunk_id = str(row.get("chunk_id", "")).strip()
        if not chunk_id:
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        clean_text = str(row.get("clean_text", ""))

        entities_raw = row.get("entities")
        entities: list[str]
        if "entities" in row:
            if isinstance(entities_raw, list):
                entities = [str(v).strip() for v in entities_raw if str(v).strip()]
            else:
                entities = []
        else:
            entities = llm_entities_by_chunk.get(chunk_id, [])
            if chunk_id in pending_llm_ids and not entities:
                stats.entity_empty_chunks += 1

        if not entities and chunk_id not in pending_llm_ids:
            stats.entity_empty_chunks += 1

        node = GraphNode(
            chunk_id=chunk_id,
            paper_id=paper_id,
            page_start=int(row.get("page_start", 0)),
            section=(str(row.get("section")).strip() if row.get("section") else None),
            content_type=content_type,
            entities=entities,
        )
        nodes[chunk_id] = node
        by_paper[paper_id].append(node)

    if on_progress is not None:
        on_progress(
            {
                "stage": "build_nodes",
                "processed": len(nodes),
                "total": max(1, len(rows)),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "message": f"节点构建完成，节点数={len(nodes)}",
            }
        )

    stats.kept_nodes = len(nodes)

    adjacent_sets: dict[str, set[str]] = {cid: set() for cid in nodes}
    entity_scores: dict[str, dict[str, int]] = {cid: {} for cid in nodes}

    # adjacent edges
    for paper_nodes in by_paper.values():
        ordered = sorted(paper_nodes, key=lambda n: (n.page_start, _chunk_sort_key(n.chunk_id)))
        for i in range(len(ordered) - 1):
            left, right = ordered[i], ordered[i + 1]
            if left.section and right.section and left.section != right.section:
                continue
            adjacent_sets[left.chunk_id].add(right.chunk_id)
            adjacent_sets[right.chunk_id].add(left.chunk_id)

    stats.adjacent_edges_undirected = sum(len(v) for v in adjacent_sets.values()) // 2
    if on_progress is not None:
        on_progress(
            {
                "stage": "build_adjacent_edges",
                "processed": stats.adjacent_edges_undirected,
                "total": stats.adjacent_edges_undirected,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "message": f"相邻边构建完成，边数={stats.adjacent_edges_undirected}",
            }
        )

    # entity co-occurrence edges (within same paper)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for paper_nodes in by_paper.values():
        entity_to_chunks: dict[str, list[str]] = defaultdict(list)
        for node in paper_nodes:
            for ent in set(node.entities):
                entity_to_chunks[ent].append(node.chunk_id)
        for chunk_ids in entity_to_chunks.values():
            unique_ids = sorted(set(chunk_ids))
            if len(unique_ids) < 2:
                continue
            for i in range(len(unique_ids) - 1):
                for j in range(i + 1, len(unique_ids)):
                    a, b = unique_ids[i], unique_ids[j]
                    pair_counts[(a, b)] += 1

    for (a, b), weight in pair_counts.items():
        if weight < entity_overlap_threshold:
            continue
        stats.entity_pairs_above_threshold += 1
        entity_scores[a][b] = weight
        entity_scores[b][a] = weight

    entity_adj: dict[str, list[tuple[str, int]]] = {}
    for cid, scored in entity_scores.items():
        ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
        if len(ranked) > entity_top_m:
            stats.entity_neighbors_clipped += len(ranked) - entity_top_m
        entity_adj[cid] = ranked[:entity_top_m]

    stats.entity_edges_directed = sum(len(v) for v in entity_adj.values())
    if on_progress is not None:
        on_progress(
            {
                "stage": "build_entity_edges",
                "processed": stats.entity_edges_directed,
                "total": stats.entity_edges_directed,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "message": f"实体边构建完成，边数={stats.entity_edges_directed}",
            }
        )

    adjacent = {cid: sorted(neigh) for cid, neigh in adjacent_sets.items()}
    graph = ChunkGraph(
        nodes=nodes,
        adjacent=adjacent,
        entity=entity_adj,
        stats=stats,
        config={
            "entity_overlap_threshold": entity_overlap_threshold,
            "entity_top_m": entity_top_m,
            "include_front_matter": include_front_matter,
        },
    )
    return graph



def save_graph(graph: ChunkGraph, path: str | Path) -> None:
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.suffix.lower() == ".pkl":
        with dst.open("wb") as f:
            pickle.dump(graph.to_dict(), f)
        return
    dst.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")



def load_graph(path: str | Path) -> ChunkGraph:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"graph file not found: {src}")
    if src.suffix.lower() == ".pkl":
        with src.open("rb") as f:
            data = pickle.load(f)
        return ChunkGraph.from_dict(data)
    data = json.loads(src.read_text(encoding="utf-8"))
    return ChunkGraph.from_dict(data)



def run_graph_build(
    input_path: str | Path,
    output_path: str | Path,
    *,
    threshold: int = 1,
    top_m: int = 30,
    include_front_matter: bool = False,
    llm_max_concurrency: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> int:
    cfg = load_config()
    resolved_stage = load_resolved_llm_stage(stage="graph_entity")
    rows = load_chunk_rows(input_path)
    llm_entity_cfg = LLMEntityExtractionConfig(
        provider=str(getattr(cfg, "graph_entity_llm_provider", "siliconflow")) or resolved_stage.values.provider,
        base_url=str(getattr(cfg, "graph_entity_llm_base_url", "https://api.siliconflow.cn/v1")) or resolved_stage.values.api_base,
        api_key_env=str(getattr(cfg, "graph_entity_llm_api_key_env", "SILICONFLOW_API_KEY")) or resolved_stage.values.api_key_env,
        api_key=resolved_stage.api_key,
        model=str(getattr(cfg, "graph_entity_llm_model", "Pro/deepseek-ai/DeepSeek-V3.2")) or resolved_stage.values.model,
        timeout_ms=max(1000, int(getattr(cfg, "graph_entity_llm_timeout_ms", 12000))),
        max_concurrency=max(
            1,
            int(
                llm_max_concurrency
                if llm_max_concurrency is not None
                else getattr(cfg, "graph_entity_llm_max_concurrency", 4)
            ),
        ),
        max_retries=max(0, int(getattr(cfg, "graph_entity_llm_max_retries", 1))),
    )
    llm_failure_records: list[dict[str, Any]] = []
    graph = build_graph(
        rows,
        entity_overlap_threshold=max(1, threshold),
        entity_top_m=max(1, top_m),
        include_front_matter=include_front_matter,
        llm_entity_config=llm_entity_cfg,
        llm_failure_records_out=llm_failure_records,
        on_progress=on_progress,
    )
    if on_progress is not None:
        on_progress(
            {
                "stage": "persist_graph",
                "processed": 0,
                "total": 1,
                "elapsed_ms": int(graph.stats.llm_entity_elapsed_ms),
                "message": "正在写入图文件",
            }
        )
    save_graph(graph, output_path)
    if llm_failure_records:
        reason_counts: dict[str, int] = {}
        for row in llm_failure_records:
            reason = str(row.get("reason", "unknown"))
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        failure_report_path = Path(output_path).with_suffix(".llm_failures.json")
        payload = {
            "generated_at": int(time.time()),
            "graph_output_path": str(output_path),
            "summary": {
                "total_failures": len(llm_failure_records),
                "reason_counts": reason_counts,
            },
            "failures": llm_failure_records[:1000],
        }
        failure_report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if on_progress is not None:
        on_progress(
            {
                "stage": "done",
                "processed": 1,
                "total": 1,
                "elapsed_ms": int(graph.stats.llm_entity_elapsed_ms),
                "message": "图构建已完成",
            }
        )
    print(f"Graph built: nodes={graph.stats.kept_nodes}, adjacent_edges={graph.stats.adjacent_edges_undirected}, entity_edges_directed={graph.stats.entity_edges_directed}")
    print(f"Entity sparse chunks={graph.stats.entity_empty_chunks}, clipped_neighbors={graph.stats.entity_neighbors_clipped}")
    print(
        "LLM entity extraction: "
        f"calls={graph.stats.llm_entity_calls}, failures={graph.stats.llm_entity_failures}, "
        f"rate_limits={graph.stats.llm_entity_rate_limits}, retries={graph.stats.llm_entity_retries}, "
        f"fallback_empty={graph.stats.llm_entity_fallback_empty}, elapsed_ms={graph.stats.llm_entity_elapsed_ms}"
    )
    if llm_failure_records:
        print(f"LLM failure report: {Path(output_path).with_suffix('.llm_failures.json')}")
    print(f"Output: {output_path}")
    return 0



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build chunk adjacency/entity graph from cleaned chunks.")
    parser.add_argument("--input", default="data/processed/chunks_clean.jsonl", help="Input chunks_clean.jsonl path")
    parser.add_argument("--out", default="data/processed/graph.json", help="Output graph path (.json or .pkl)")
    parser.add_argument("--threshold", type=int, default=1, help="Minimum shared entity count to create entity edge")
    parser.add_argument("--top-m", type=int, default=30, help="Maximum entity neighbors kept per chunk")
    parser.add_argument(
        "--include-front-matter",
        action="store_true",
        help="Include front_matter chunks in graph construction",
    )
    return parser.parse_args(argv)



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_graph_build(
        args.input,
        args.out,
        threshold=args.threshold,
        top_m=args.top_m,
        include_front_matter=args.include_front_matter,
    )


if __name__ == "__main__":
    raise SystemExit(main())
