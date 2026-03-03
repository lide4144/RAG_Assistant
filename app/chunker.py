from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import ChunkRecord, PageText


HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\s+)?[A-Z][A-Za-z0-9 ,:()\-/]{2,}$"
)


@dataclass
class Segment:
    page_start: int
    text: str


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
) -> list[ChunkRecord]:
    segments = split_into_segments(pages)
    return sliding_window_chunk(
        paper_id=paper_id,
        segments=segments,
        chunk_size=chunk_size,
        overlap=overlap,
    )

