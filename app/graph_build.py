from __future__ import annotations

import argparse
import json
import pickle
import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ACRONYM_RE = re.compile(r"\b[A-Z]{2,10}(?:/[A-Z]{2,10})?\b")
HYPHEN_NUM_RE = re.compile(r"\b[A-Za-z]+-\d+[A-Za-z0-9-]*\b")
CAMEL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")


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



def _chunk_sort_key(chunk_id: str) -> tuple[str, int]:
    if ":" not in chunk_id:
        return chunk_id, 0
    prefix, suffix = chunk_id.rsplit(":", 1)
    try:
        idx = int(suffix)
    except ValueError:
        idx = 0
    return prefix, idx



def extract_entities_from_text(clean_text: str) -> list[str]:
    """从 clean_text 规则抽取实体。"""
    found: list[str] = []
    for pattern in (ACRONYM_RE, HYPHEN_NUM_RE, CAMEL_RE):
        for match in pattern.finditer(clean_text or ""):
            token = match.group(0).strip()
            if token and token not in found:
                found.append(token)
    return found



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
) -> ChunkGraph:
    stats = GraphBuildStats(input_total=len(rows))

    nodes: dict[str, GraphNode] = {}
    by_paper: dict[str, list[GraphNode]] = defaultdict(list)

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
        if isinstance(entities_raw, list) and entities_raw:
            entities = [str(v).strip() for v in entities_raw if str(v).strip()]
        else:
            entities = extract_entities_from_text(clean_text)

        if not entities:
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
) -> int:
    rows = load_chunk_rows(input_path)
    graph = build_graph(
        rows,
        entity_overlap_threshold=max(1, threshold),
        entity_top_m=max(1, top_m),
        include_front_matter=include_front_matter,
    )
    save_graph(graph, output_path)
    print(f"Graph built: nodes={graph.stats.kept_nodes}, adjacent_edges={graph.stats.adjacent_edges_undirected}, entity_edges_directed={graph.stats.entity_edges_directed}")
    print(f"Entity sparse chunks={graph.stats.entity_empty_chunks}, clipped_neighbors={graph.stats.entity_neighbors_clipped}")
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
