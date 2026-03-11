from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STRUCTURE_READY = "ready"
STRUCTURE_DEGRADED = "degraded"
STRUCTURE_UNAVAILABLE = "unavailable"

_STRUCTURE_QUERY_PATTERNS = [
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\b(section|sections|chapter|chapters|outline|structure|table of contents|contents)\b",
        r"\bsec(?:tion)?\s*\d+(?:\.\d+)*\b",
        r"\bchapter\s*\d+\b",
        r"(第\s*\d+(?:\.\d+)?\s*[章节节])|(目录)|(结构)",
    )
]


@dataclass
class SectionMatch:
    paper_id: str
    section_id: str
    score: float
    section_title: str
    heading_path: list[str]
    child_chunk_ids: list[str]
    start_page: int
    end_page: int
    coverage: str


def is_structure_question(query: str) -> bool:
    raw = str(query or "").strip()
    if not raw:
        return False
    return any(pattern.search(raw) for pattern in _STRUCTURE_QUERY_PATTERNS)


def load_structure_index(chunks_path: str | Path) -> dict[str, Any]:
    path = Path(chunks_path).parent / "structure_index.json"
    if not path.exists():
        return {"papers": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"papers": []}
    if not isinstance(payload, dict):
        return {"papers": []}
    papers = payload.get("papers")
    if not isinstance(papers, list):
        payload["papers"] = []
    return payload


def save_structure_index(index_payload: dict[str, Any], chunks_path: str | Path) -> None:
    path = Path(chunks_path).parent / "structure_index.json"
    path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_structure_entries(
    existing_payload: dict[str, Any],
    new_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = existing_payload.get("papers")
    merged: dict[str, dict[str, Any]] = {}
    if isinstance(existing, list):
        for row in existing:
            if not isinstance(row, dict):
                continue
            paper_id = str(row.get("paper_id", "")).strip()
            if paper_id:
                merged[paper_id] = row
    for row in new_entries:
        paper_id = str(row.get("paper_id", "")).strip()
        if paper_id:
            merged[paper_id] = row
    return {"papers": [merged[key] for key in sorted(merged.keys())]}


def summarize_structure_status(
    structure_index: dict[str, Any],
    *,
    paper_ids: set[str] | None = None,
) -> tuple[str, list[str]]:
    papers = structure_index.get("papers")
    if not isinstance(papers, list) or not papers:
        return STRUCTURE_UNAVAILABLE, ["structure_index_missing"]
    statuses: list[str] = []
    reasons: list[str] = []
    for row in papers:
        if not isinstance(row, dict):
            continue
        paper_id = str(row.get("paper_id", "")).strip()
        if paper_ids and paper_id not in paper_ids:
            continue
        statuses.append(str(row.get("structure_parse_status", STRUCTURE_UNAVAILABLE)).strip() or STRUCTURE_UNAVAILABLE)
        reason = str(row.get("structure_parse_reason", "")).strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    if not statuses:
        return STRUCTURE_UNAVAILABLE, ["structure_index_missing_for_scope"]
    if any(status == STRUCTURE_READY for status in statuses):
        return STRUCTURE_READY, reasons
    if any(status == STRUCTURE_DEGRADED for status in statuses):
        return STRUCTURE_DEGRADED, reasons
    return STRUCTURE_UNAVAILABLE, reasons


def retrieve_sections(
    *,
    query: str,
    structure_index: dict[str, Any],
    allowed_paper_ids: set[str] | None = None,
    top_k: int = 5,
) -> list[SectionMatch]:
    q_tokens = _tokenize_structure_query(query)
    if not q_tokens:
        return []
    out: list[SectionMatch] = []
    for paper in structure_index.get("papers", []) or []:
        if not isinstance(paper, dict):
            continue
        paper_id = str(paper.get("paper_id", "")).strip()
        if not paper_id:
            continue
        if allowed_paper_ids and paper_id not in allowed_paper_ids:
            continue
        if str(paper.get("structure_parse_status", "")).strip() != STRUCTURE_READY:
            continue
        for row in paper.get("sections", []) or []:
            if not isinstance(row, dict):
                continue
            child_chunk_ids = [str(x).strip() for x in row.get("child_chunk_ids", []) if str(x).strip()]
            if not child_chunk_ids:
                continue
            title = str(row.get("section_title", "")).strip()
            heading_path = [str(x).strip() for x in row.get("heading_path", []) if str(x).strip()]
            haystack = " ".join([title] + heading_path).lower()
            score = _score_tokens(q_tokens, haystack)
            if score <= 0:
                continue
            coverage = "partial"
            if any(token in {"目录", "contents", "table", "structure", "outline"} for token in q_tokens):
                coverage = "full" if int(row.get("section_level", 0) or 0) == 1 else "partial"
            out.append(
                SectionMatch(
                    paper_id=paper_id,
                    section_id=str(row.get("section_id", "")).strip(),
                    score=score,
                    section_title=title,
                    heading_path=heading_path,
                    child_chunk_ids=child_chunk_ids,
                    start_page=max(1, int(row.get("start_page", 1) or 1)),
                    end_page=max(1, int(row.get("end_page", row.get("start_page", 1)) or 1)),
                    coverage=coverage,
                )
            )
    out.sort(key=lambda item: item.score, reverse=True)
    return out[:top_k]


def _tokenize_structure_query(text: str) -> list[str]:
    lowered = str(text or "").lower()
    hits = re.findall(r"[a-z]+|\d+(?:\.\d+)?|[\u4e00-\u9fff]{1,}", lowered)
    return [token for token in hits if token.strip()]


def _score_tokens(tokens: list[str], haystack: str) -> float:
    score = 0.0
    for token in tokens:
        if token in haystack:
            score += 1.0
    return score / max(1, len(tokens))
