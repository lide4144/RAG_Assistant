from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PaperRecord:
    paper_id: str
    title: str
    path: str
    source_type: str = "pdf"
    source_uri: str = ""
    parser_engine: str = "legacy"
    title_source: str = ""
    title_confidence: float = 0.0
    imported_at: str = ""
    status: str = "active"
    fingerprint: str = ""
    ingest_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload.get("ingest_metadata") is None:
            payload.pop("ingest_metadata", None)
        return payload


@dataclass
class PageText:
    page_num: int
    text: str


@dataclass
class ChunkRecord:
    chunk_id: str
    paper_id: str
    page_start: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
