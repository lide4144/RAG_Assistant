from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from app.models import ChunkRecord, PaperRecord


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
    "论文",
    "研究",
    "方法",
    "结果",
    "以及",
}


@dataclass
class PaperSummaryRecord:
    paper_id: str
    title: str
    one_paragraph_summary: str
    key_points: list[str]
    keywords: list[str]
    source_uri: str
    summary_version: str
    chunk_snapshot_hash: str
    is_stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip(text: str, limit: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def _keywords(text: str, *, top_k: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for tok in TOKEN_RE.findall(text or ""):
        lowered = tok.lower()
        if lowered in STOPWORDS:
            continue
        counts[lowered] = counts.get(lowered, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [k for k, _ in ranked[:top_k]]


def chunk_snapshot_hash(chunks: list[ChunkRecord]) -> str:
    hasher = hashlib.sha1()
    for row in sorted(chunks, key=lambda c: c.chunk_id):
        hasher.update(row.chunk_id.encode("utf-8"))
        hasher.update(b"\n")
        hasher.update(row.text.encode("utf-8", errors="ignore"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def build_paper_summaries(
    papers: list[PaperRecord],
    chunks: list[ChunkRecord],
    *,
    previous_hashes: dict[str, str] | None = None,
    summary_version: str = "v1",
) -> tuple[list[PaperSummaryRecord], list[str]]:
    grouped_chunks: dict[str, list[ChunkRecord]] = {}
    for chunk in chunks:
        grouped_chunks.setdefault(chunk.paper_id, []).append(chunk)

    previous = previous_hashes or {}
    rebuilt_ids: list[str] = []
    out: list[PaperSummaryRecord] = []
    for paper in papers:
        paper_chunks = grouped_chunks.get(paper.paper_id, [])
        joined = " ".join(c.text for c in paper_chunks)
        snap_hash = chunk_snapshot_hash(paper_chunks)
        old_hash = previous.get(paper.paper_id)
        if old_hash and old_hash != snap_hash:
            rebuilt_ids.append(paper.paper_id)
        summary_text = _clip(joined, 600) if joined else f"{paper.title} source ingest summary unavailable."
        key_points: list[str] = []
        for chunk in paper_chunks[:3]:
            clipped = _clip(chunk.text, 140)
            if clipped:
                key_points.append(clipped)
        if not key_points:
            key_points = [_clip(summary_text, 140)] if summary_text else []

        out.append(
            PaperSummaryRecord(
                paper_id=paper.paper_id,
                title=paper.title,
                one_paragraph_summary=summary_text,
                key_points=key_points[:5],
                keywords=_keywords(" ".join([paper.title, summary_text] + key_points)),
                source_uri=paper.source_uri or paper.path,
                summary_version=summary_version,
                chunk_snapshot_hash=snap_hash,
                is_stale=False,
            )
        )
    return out, rebuilt_ids
