from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models import ChunkRecord, PageText


HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s+)?[A-Z][A-Za-z0-9 ,:()\-/]{2,}$"
)


@dataclass
class Segment:
    page_start: int
    text: str
    section: str | None = None
    section_id: str | None = None
    heading_path: list[str] | None = None
    block_type: str | None = None
    content_type: str = "body"
    markdown_source: str | None = None
    structure_provenance: dict[str, Any] | None = None


def _block_type_to_content_type(block_type: str | None) -> str:
    normalized = str(block_type or "").strip().lower()
    if normalized in {"table", "tablegroup", "tablecell", "tablerow", "table_row", "tablecolumn"}:
        return "table_block"
    if normalized in {"equation", "math", "formula", "formulablock"}:
        return "formula_block"
    return "body"


def estimate_tokens(text: str) -> int:
    words = text.split()
    if words:
        return len(words)
    return max(1, len(text) // 4)


def split_into_segments(pages: list[PageText]) -> list[Segment]:
    segments: list[Segment] = []
    current_page = 1
    buf: list[str] = []

    def flush():
        if buf:
            segment_text = "\n".join(buf).strip()
            if segment_text:
                segments.append(Segment(page_start=current_page, text=segment_text))

    for page in pages:
        lines = page.text.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if HEADING_RE.match(stripped) and buf:
                flush()
                buf = [stripped]
                current_page = page.page_num
            else:
                if not buf:
                    current_page = page.page_num
                buf.append(stripped)
        if buf and (not lines or lines[-1].strip() == ""):
            flush()
            buf = []
    if buf:
        flush()

    if not segments:
        for page in pages:
            if page.text.strip():
                segments.append(Segment(page_start=page.page_num, text=page.text.strip()))
    return segments


def split_structured_segments(blocks: list[dict[str, Any]] | None) -> list[Segment]:
    if not blocks:
        return []
    active_lines: list[str] = []
    active_page = 1
    active_heading_mode = False
    active_section: str | None = None
    active_section_id: str | None = None
    active_heading_path: list[str] | None = None

    def flush_active() -> None:
        nonlocal active_lines, active_page, active_heading_mode
        if not active_lines:
            return
        merged = "\n".join(active_lines).strip()
        if merged:
            segments.append(
                Segment(
                    page_start=active_page,
                    text=merged,
                    section=active_section,
                    section_id=active_section_id,
                    heading_path=list(active_heading_path or []) or None,
                    block_type="SectionHeader",
                    markdown_source="marker_markdown",
                    structure_provenance={
                        "source": "marker",
                        "block_type": "SectionHeader",
                        "heading_path": list(active_heading_path or []) or None,
                    },
                )
            )
        active_lines = []
        active_page = 1
        active_heading_mode = False

    segments: list[Segment] = []
    heading_stack: list[tuple[int, str, str]] = []
    section_counter = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        page_num_raw = block.get("page")
        try:
            page_num = int(page_num_raw)
        except Exception:
            page_num = 1
        page_num = max(1, page_num)
        heading_level_raw = block.get("heading_level")
        heading_level = heading_level_raw if isinstance(heading_level_raw, int) and heading_level_raw > 0 else None
        block_type = str(block.get("block_type", "")).strip() or None
        markdown_source = str(block.get("markdown_source", "")).strip() or None

        # Prefer heading levels as section boundaries when present.
        if heading_level is not None:
            flush_active()
            while heading_stack and heading_stack[-1][0] >= heading_level:
                heading_stack.pop()
            section_counter += 1
            section_id = f"sec-{section_counter:04d}"
            heading_stack.append((heading_level, text, section_id))
            active_section = text
            active_section_id = section_id
            active_heading_path = [row[1] for row in heading_stack]
            active_lines = [text]
            active_page = page_num
            active_heading_mode = True
            continue

        if active_heading_mode:
            active_lines.append(text)
            continue

        # For non-heading blocks, preserve block boundary behavior.
        segments.append(
            Segment(
                page_start=page_num,
                text=text,
                section=active_section,
                section_id=active_section_id,
                heading_path=list(active_heading_path or []) or None,
                block_type=block_type,
                content_type=_block_type_to_content_type(block_type),
                markdown_source=markdown_source,
                structure_provenance={
                    "source": "marker",
                    "block_type": block_type or "Text",
                    "markdown_source": markdown_source,
                    "heading_path": list(active_heading_path or []) or None,
                },
            )
        )

    flush_active()
    return segments


def sliding_window_chunk(
    paper_id: str,
    segments: list[Segment],
    chunk_size: int,
    overlap: int,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    chunk_index = 0
    step = max(1, chunk_size - overlap)

    for segment in segments:
        words = segment.text.split()
        if not words:
            continue
        if estimate_tokens(segment.text) <= chunk_size:
            chunk_index += 1
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{paper_id}:{chunk_index:05d}",
                    paper_id=paper_id,
                    page_start=segment.page_start,
                    text=segment.text,
                    section=segment.section,
                    section_id=segment.section_id,
                    heading_path=list(segment.heading_path or []) or None,
                    block_type=segment.block_type,
                    content_type=segment.content_type,
                    markdown_source=segment.markdown_source,
                    structure_provenance=dict(segment.structure_provenance or {}) or None,
                )
            )
            continue

        start = 0
        while start < len(words):
            end = min(len(words), start + chunk_size)
            text = " ".join(words[start:end]).strip()
            if text:
                chunk_index += 1
                chunks.append(
                    ChunkRecord(
                        chunk_id=f"{paper_id}:{chunk_index:05d}",
                        paper_id=paper_id,
                        page_start=segment.page_start,
                        text=text,
                        section=segment.section,
                        section_id=segment.section_id,
                        heading_path=list(segment.heading_path or []) or None,
                        block_type=segment.block_type,
                        content_type=segment.content_type,
                        markdown_source=segment.markdown_source,
                        structure_provenance=dict(segment.structure_provenance or {}) or None,
                    )
                )
            if end >= len(words):
                break
            start += step
    return chunks


def build_chunks(
    paper_id: str,
    pages: list[PageText],
    chunk_size: int,
    overlap: int,
    structured_segments: list[dict[str, Any]] | None = None,
) -> list[ChunkRecord]:
    segments = split_structured_segments(structured_segments) or split_into_segments(pages)
    return sliding_window_chunk(
        paper_id=paper_id,
        segments=segments,
        chunk_size=chunk_size,
        overlap=overlap,
    )
