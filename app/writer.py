from __future__ import annotations

import json as std_json
from pathlib import Path
from typing import Iterable

from app.fs_utils import atomic_text_writer
from app.models import ChunkRecord, PaperRecord
from app.paper_summary import PaperSummaryRecord

try:
    import orjson
except ModuleNotFoundError:  # pragma: no cover - optional optimization
    orjson = None


def ensure_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _json_dumps(payload: object, *, indent: bool = False) -> str:
    if orjson is not None:
        option = orjson.OPT_INDENT_2 if indent else 0
        return orjson.dumps(payload, option=option).decode("utf-8")
    if indent:
        return std_json.dumps(payload, ensure_ascii=False, indent=2)
    return std_json.dumps(payload, ensure_ascii=False)


def write_chunks_jsonl(chunks: Iterable[ChunkRecord], output_file: str | Path) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(output_path) as f:
        for idx, chunk in enumerate(chunks, start=1):
            try:
                f.write(_json_dumps(chunk.to_dict()) + "\n")
            except Exception as exc:
                raise RuntimeError(f"failed to serialize chunk at row {idx}") from exc


def write_papers_json(papers: Iterable[PaperRecord], output_file: str | Path) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(output_path) as f:
        f.write("[\n")
        first = True
        for idx, paper in enumerate(papers, start=1):
            try:
                row = _json_dumps(paper.to_dict(), indent=True)
            except Exception as exc:
                raise RuntimeError(f"failed to serialize paper at row {idx}") from exc
            if not first:
                f.write(",\n")
            f.write(row)
            first = False
        f.write("\n]\n")


def write_paper_summaries_json(
    summaries: Iterable[PaperSummaryRecord],
    output_file: str | Path,
) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(output_path) as f:
        f.write("[\n")
        first = True
        for idx, row in enumerate(summaries, start=1):
            try:
                serialized = _json_dumps(row.to_dict(), indent=True)
            except Exception as exc:
                raise RuntimeError(f"failed to serialize paper summary at row {idx}") from exc
            if not first:
                f.write(",\n")
            f.write(serialized)
            first = False
        f.write("\n]\n")


def validate_chunks_jsonl(chunks_file: str | Path, *, max_errors: int = 100) -> tuple[bool, list[str]]:
    required = {"chunk_id", "paper_id", "page_start", "text"}
    errors: list[str] = []
    path = Path(chunks_file)
    if not path.exists():
        return False, [f"missing output file: {path}"]

    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = std_json.loads(line)
            except std_json.JSONDecodeError as exc:
                errors.append(f"line {idx}: invalid JSON: {exc}")
                continue
            missing = required - set(obj.keys())
            if missing:
                errors.append(f"line {idx}: missing fields: {sorted(missing)}")
                continue
            if not isinstance(obj.get("chunk_id"), str) or not str(obj.get("chunk_id", "")).strip():
                errors.append(f"line {idx}: chunk_id must be non-empty string")
            if not isinstance(obj.get("paper_id"), str) or not str(obj.get("paper_id", "")).strip():
                errors.append(f"line {idx}: paper_id must be non-empty string")
            if not isinstance(obj.get("page_start"), int) or obj.get("page_start") <= 0:
                errors.append(f"line {idx}: page_start must be positive integer")
            if not isinstance(obj.get("text"), str) or not str(obj.get("text", "")).strip():
                errors.append(f"line {idx}: empty text")
            if len(errors) >= max_errors:
                errors.append(f"... stopping after {max_errors} errors ...")
                break
    return len(errors) == 0, errors
