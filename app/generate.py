from __future__ import annotations

from app.retrieve import RetrievalCandidate


def build_quote(text: str, max_len: int = 120) -> str:
    raw = " ".join((text or "").split())
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 3].rstrip() + "..."


def format_evidence(
    candidates: list[RetrievalCandidate], top_n: int = 5
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for c in candidates[:top_n]:
        section_or_page = c.section if c.section else f"p.{c.page_start}"
        evidence.append(
            {
                "chunk_id": c.chunk_id,
                "section_page": section_or_page,
                "quote": build_quote(c.text),
            }
        )
    return evidence


def main() -> int:
    return 0
