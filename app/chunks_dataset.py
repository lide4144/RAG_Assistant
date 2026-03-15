from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class ChunkDoc:
    chunk_id: str
    paper_id: str
    page_start: int
    section: str | None
    text: str
    clean_text: str
    content_type: str
    block_type: str | None = None
    markdown_source: str | None = None
    structure_provenance: dict | None = None


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text or "")]


def load_chunks_clean(
    path: str | Path = "data/processed/chunks_clean.jsonl",
    *,
    filter_watermark: bool = True,
    filter_suppressed: bool = True,
) -> list[ChunkDoc]:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"chunks file not found: {src}")

    docs: list[ChunkDoc] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            suppressed = bool(row.get("suppressed", False))
            if filter_suppressed and suppressed:
                continue
            content_type = str(row.get("content_type", "body"))
            if filter_watermark and content_type == "watermark":
                continue
            docs.append(
                ChunkDoc(
                    chunk_id=str(row.get("chunk_id", "")),
                    paper_id=str(row.get("paper_id", "")),
                    page_start=int(row.get("page_start", 0)),
                    section=row.get("section"),
                    text=str(row.get("text", "")),
                    clean_text=str(row.get("clean_text", "")),
                    content_type=content_type,
                    block_type=(str(row.get("block_type", "")).strip() or None),
                    markdown_source=(str(row.get("markdown_source", "")).strip() or None),
                    structure_provenance=(row.get("structure_provenance") if isinstance(row.get("structure_provenance"), dict) else None),
                )
            )
    return docs
