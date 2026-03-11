from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


WATERMARK_KEYWORDS = [
    "authorized licensed use limited to",
    "downloaded on",
    "ieee xplore",
    "restrictions apply",
]

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
SPACE_RE = re.compile(r"[ \t\r\f\v]+")
NON_ALNUM_RE = re.compile(r"[^\w\s]", re.UNICODE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
REFERENCE_RE = re.compile(r"\b(journal|vol\.?|volume|no\.?|pp\.?|pages?)\b", re.IGNORECASE)
YEAR_VOLUME_PAGE_RE = re.compile(r"\b(19|20)\d{2}\s*;?\s*\d+\s*\(\d+\)\s*:\s*\d+", re.IGNORECASE)
EQ_RE = re.compile(r"\bEq\.", re.IGNORECASE)
INDEXED_EQ_RE = re.compile(r"\(\d+\)")


@dataclass
class CleanChunkRecord:
    chunk_id: str
    paper_id: str
    page_start: int
    text: str
    clean_text: str
    content_type: str
    quality_flags: list[str]
    section: str | None = None
    section_id: str | None = None
    heading_path: list[str] | None = None
    merged_from: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.merged_from is None:
            data.pop("merged_from", None)
        if self.section is None:
            data.pop("section", None)
        if self.section_id is None:
            data.pop("section_id", None)
        if self.heading_path is None:
            data.pop("heading_path", None)
        return data


def _chunk_sort_key(chunk_id: str) -> tuple[str, int]:
    if ":" not in chunk_id:
        return chunk_id, 0
    prefix, suffix = chunk_id.rsplit(":", 1)
    try:
        idx = int(suffix)
    except ValueError:
        idx = 0
    return prefix, idx


def _contains_watermark(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in WATERMARK_KEYWORDS)


def remove_watermark_lines(text: str) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(keyword in lowered for keyword in WATERMARK_KEYWORDS):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def normalize_urls(text: str) -> tuple[str, bool]:
    replaced, count = URL_RE.subn("<URL>", text)
    return replaced, count > 0


def normalize_whitespace_and_controls(text: str) -> str:
    text = CONTROL_CHAR_RE.sub(" ", text)
    lines = [SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()


def weird_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    candidate = [ch for ch in text if not ch.isspace()]
    if not candidate:
        return 0.0
    allowed_punct = set(".,;:!?()[]{}<>\"'`+-=*/\\|_#@&%$^~")
    weird = 0
    for ch in candidate:
        if ch.isalnum():
            continue
        if ch in allowed_punct:
            continue
        weird += 1
    return weird / len(candidate)


def classify_content_type(original_text: str, clean_text: str) -> str:
    merged = f"{original_text}\n{clean_text}"
    lowered = merged.lower()

    if _contains_watermark(merged):
        return "watermark"
    if (
        "player choices" in lowered
        or "if the player chooses" in lowered
        or "character:" in lowered
    ):
        return "dialogue_script"
    if REFERENCE_RE.search(merged) and YEAR_VOLUME_PAGE_RE.search(merged):
        return "reference"
    if EMAIL_RE.search(merged) or any(
        token in lowered
        for token in ("university", "institute", "school", "department", "laboratory", "college")
    ):
        return "front_matter"
    if "appendix" in lowered:
        return "appendix"
    indexed_eq_count = len(INDEXED_EQ_RE.findall(merged))
    symbol_ratio = 0.0
    if merged:
        symbol_ratio = len(NON_ALNUM_RE.findall(merged)) / max(1, len(merged))
    if EQ_RE.search(merged) or indexed_eq_count >= 3 or symbol_ratio > 0.25:
        return "formula_block"
    return "body"


def clean_chunk_record(record: dict[str, Any]) -> CleanChunkRecord:
    chunk_id = str(record.get("chunk_id", ""))
    paper_id = str(record.get("paper_id", ""))
    page_start = int(record.get("page_start", 0))
    text = str(record.get("text", ""))

    without_watermark = remove_watermark_lines(text)
    normalized_url_text, has_url = normalize_urls(without_watermark)
    clean_text = normalize_whitespace_and_controls(normalized_url_text)

    flags: list[str] = []
    if has_url:
        flags.append("has_url")
    if weird_char_ratio(clean_text) > 0.35:
        flags.append("garbled")

    content_type = classify_content_type(text, clean_text)
    return CleanChunkRecord(
        chunk_id=chunk_id,
        paper_id=paper_id,
        page_start=page_start,
        text=text,
        clean_text=clean_text,
        content_type=content_type,
        quality_flags=flags,
        section=(str(record.get("section", "")).strip() or None),
        section_id=(str(record.get("section_id", "")).strip() or None),
        heading_path=[str(x).strip() for x in record.get("heading_path", []) if str(x).strip()] or None,
    )


def merge_short_fragments(records: list[CleanChunkRecord]) -> list[CleanChunkRecord]:
    grouped: dict[tuple[str, int], list[CleanChunkRecord]] = {}
    for rec in records:
        grouped.setdefault((rec.paper_id, rec.page_start), []).append(rec)

    merged_records: list[CleanChunkRecord] = []
    for _, group in grouped.items():
        group.sort(key=lambda rec: _chunk_sort_key(rec.chunk_id))
        i = 0
        while i < len(group):
            if len(group[i].text.strip()) > 40:
                merged_records.append(group[i])
                i += 1
                continue
            j = i
            while j < len(group) and len(group[j].text.strip()) <= 40:
                j += 1
            run_len = j - i
            if run_len >= 6:
                chunk_block = group[i:j]
                flags: list[str] = []
                for item in chunk_block:
                    for flag in item.quality_flags:
                        if flag not in flags:
                            flags.append(flag)
                if "short_fragment_merged" not in flags:
                    flags.append("short_fragment_merged")
                merged_records.append(
                    CleanChunkRecord(
                        chunk_id=chunk_block[0].chunk_id,
                        paper_id=chunk_block[0].paper_id,
                        page_start=chunk_block[0].page_start,
                        text="\n".join(item.text for item in chunk_block),
                        clean_text="\n".join(item.clean_text for item in chunk_block if item.clean_text),
                        content_type="table_list",
                        quality_flags=flags,
                        section=chunk_block[0].section,
                        section_id=chunk_block[0].section_id,
                        heading_path=list(chunk_block[0].heading_path or []) or None,
                        merged_from=[item.chunk_id for item in chunk_block],
                    )
                )
            else:
                merged_records.extend(group[i:j])
            i = j
    merged_records.sort(key=lambda rec: (rec.paper_id, rec.page_start, _chunk_sort_key(rec.chunk_id)))
    return merged_records


def load_chunks(path: str | Path) -> list[dict[str, Any]]:
    src = Path(path)
    items: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def write_clean_chunks(records: list[CleanChunkRecord], path: str | Path) -> None:
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as f:
        for item in records:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")


def run_clean_chunks(input_path: str | Path, output_path: str | Path) -> int:
    raw_records = load_chunks(input_path)
    cleaned = [clean_chunk_record(item) for item in raw_records]
    merged = merge_short_fragments(cleaned)
    write_clean_chunks(merged, output_path)
    print(f"Cleaned {len(raw_records)} chunks -> {len(merged)} chunks")
    print(f"Output: {output_path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean and label chunk records.")
    parser.add_argument("--input", required=True, help="Input chunks.jsonl path")
    parser.add_argument("--out", required=True, help="Output chunks_clean.jsonl path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_clean_chunks(args.input, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
