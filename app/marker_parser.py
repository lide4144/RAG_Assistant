from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import inspect
import signal
from pathlib import Path
import threading
import time
from types import FrameType
from typing import Any

from bs4 import BeautifulSoup
from app.models import PageText


class MarkerParseError(RuntimeError):
    """Raised when marker parsing fails."""

    def __init__(self, message: str, *, stage: str = "unknown") -> None:
        super().__init__(message)
        self.stage = str(stage or "unknown")


class _ParseTimeoutError(TimeoutError):
    pass


@dataclass
class StructuredBlock:
    page_num: int
    text: str
    heading_level: int | None = None


@dataclass
class MarkerParseResult:
    pages: list[PageText]
    blocks: list[StructuredBlock]
    title_candidates: list[str]
    stage_timings: dict[str, float] = field(default_factory=dict)


_ARTIFACTS_LOCK = threading.Lock()
_CACHED_ARTIFACTS: dict[str, Any] | None = None


class _TimeoutGuard:
    def __init__(self, timeout_sec: float) -> None:
        self._timeout_sec = max(0.0, float(timeout_sec))
        self._enabled = hasattr(signal, "setitimer") and self._timeout_sec > 0
        self._prev_handler: Any = None

    def _on_timeout(self, signum: int, frame: FrameType | None) -> None:
        raise _ParseTimeoutError(f"marker parse timeout after {self._timeout_sec:.1f}s")

    def __enter__(self) -> None:
        if not self._enabled:
            return
        self._prev_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._on_timeout)
        signal.setitimer(signal.ITIMER_REAL, self._timeout_sec)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self._enabled:
            return
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self._prev_handler)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _load_marker_artifacts() -> dict[str, Any]:
    global _CACHED_ARTIFACTS
    if _CACHED_ARTIFACTS is not None:
        return _CACHED_ARTIFACTS
    with _ARTIFACTS_LOCK:
        if _CACHED_ARTIFACTS is not None:
            return _CACHED_ARTIFACTS
        models_module = importlib.import_module("marker.models")
        create_model_dict = getattr(models_module, "create_model_dict")
        artifacts = create_model_dict()
        if not isinstance(artifacts, dict):
            raise MarkerParseError("marker model loader returned invalid artifact_dict", stage="model_loader")
        _CACHED_ARTIFACTS = artifacts
        return _CACHED_ARTIFACTS


def _create_pdf_converter(converter_cls: Any) -> Any:
    def _supports_artifact_dict_argument(target: Any) -> bool:
        for candidate in (target, getattr(target, "__init__", None), getattr(target, "__new__", None)):
            if candidate is None:
                continue
            try:
                signature = inspect.signature(candidate)
            except (TypeError, ValueError):
                continue
            if "artifact_dict" in signature.parameters:
                return True
        return False

    def _build_with_kwargs() -> Any:
        return converter_cls(artifact_dict=_load_marker_artifacts())

    def _build_with_positional() -> Any:
        return converter_cls(_load_marker_artifacts())

    attempts: list[Any]
    if _supports_artifact_dict_argument(converter_cls):
        attempts = [_build_with_kwargs, _build_with_positional, converter_cls]
    else:
        attempts = [converter_cls, _build_with_kwargs, _build_with_positional]

    last_type_error: TypeError | None = None
    for builder in attempts:
        try:
            return builder()
        except TypeError as exc:
            last_type_error = exc
            continue

    if last_type_error is not None:
        raise last_type_error
    return converter_cls()


def _normalize_blocks(raw_blocks: list[dict[str, Any]]) -> list[StructuredBlock]:
    blocks: list[StructuredBlock] = []
    for row in raw_blocks:
        text = _safe_text(row.get("text"))
        if not text:
            continue
        page_num_raw = row.get("page")
        try:
            page_num = int(page_num_raw)
        except Exception:
            page_num = 1
        heading_level_raw = row.get("heading_level")
        heading_level: int | None = None
        if isinstance(heading_level_raw, int) and heading_level_raw > 0:
            heading_level = heading_level_raw
        blocks.append(StructuredBlock(page_num=max(1, page_num), text=text, heading_level=heading_level))
    return blocks


def _extract_fields(raw_result: Any) -> tuple[str, list[dict[str, Any]]]:
    markdown_obj = getattr(raw_result, "markdown", None)
    if markdown_obj is None and isinstance(raw_result, dict):
        markdown_obj = raw_result.get("markdown")
    markdown = _safe_text(markdown_obj)
    blocks = getattr(raw_result, "blocks", None)
    if blocks is None and isinstance(raw_result, dict):
        blocks = raw_result.get("blocks")
    if not isinstance(blocks, list):
        blocks = []
    normalized: list[dict[str, Any]] = []
    for item in blocks:
        if not isinstance(item, dict):
            continue
        normalized.append(item)
    return markdown, normalized


def _extract_text_from_html(html: str) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)
    return _safe_text(text)


def _flatten_json_children(
    nodes: list[Any] | None,
    *,
    page_num: int,
    output: list[dict[str, Any]],
) -> None:
    if not nodes:
        return

    for node in nodes:
        if node is None:
            continue

        block_type = str(getattr(node, "block_type", "") or "")
        children = getattr(node, "children", None)
        html = str(getattr(node, "html", "") or "")
        text = _extract_text_from_html(html)
        heading_level = None

        section_hierarchy = getattr(node, "section_hierarchy", None)
        if block_type == "SectionHeader" and isinstance(section_hierarchy, dict) and section_hierarchy:
            try:
                heading_level = max(int(key) for key in section_hierarchy.keys())
            except Exception:
                heading_level = 1
        elif block_type == "SectionHeader":
            heading_level = 1

        if text:
            output.append(
                {
                    "page": page_num,
                    "text": text,
                    "heading_level": heading_level,
                    "block_type": block_type,
                }
            )

        if children:
            _flatten_json_children(children, page_num=page_num, output=output)


def _extract_markdown_and_blocks(document: Any, converter: Any) -> tuple[str, list[dict[str, Any]]]:
    markdown_renderer_module = importlib.import_module("marker.renderers.markdown")
    json_renderer_module = importlib.import_module("marker.renderers.json")
    markdown_renderer_cls = getattr(markdown_renderer_module, "MarkdownRenderer")
    json_renderer_cls = getattr(json_renderer_module, "JSONRenderer")

    markdown_renderer = converter.resolve_dependencies(markdown_renderer_cls)
    json_renderer = converter.resolve_dependencies(json_renderer_cls)

    markdown_output = markdown_renderer(document)
    json_output = json_renderer(document)

    markdown = _safe_text(getattr(markdown_output, "markdown", ""))
    raw_blocks: list[dict[str, Any]] = []
    for page_idx, page_node in enumerate(getattr(json_output, "children", []) or [], start=1):
        _flatten_json_children(getattr(page_node, "children", None), page_num=page_idx, output=raw_blocks)
    return markdown, raw_blocks


def _marker_to_intermediate(markdown: str, raw_blocks: list[dict[str, Any]]) -> MarkerParseResult:
    blocks = _normalize_blocks(raw_blocks)
    pages_map: dict[int, list[str]] = {}
    for block in blocks:
        pages_map.setdefault(block.page_num, []).append(block.text)

    if not pages_map:
        content = _safe_text(markdown)
        if content:
            pages_map[1] = [content]

    pages = [
        PageText(page_num=page_num, text="\n\n".join(rows).strip())
        for page_num, rows in sorted(pages_map.items())
        if "\n\n".join(rows).strip()
    ]

    title_candidates: list[str] = []
    for block in blocks[:20]:
        if block.heading_level in {1, 2}:
            title_candidates.append(block.text)
    if markdown:
        first_line = _safe_text(markdown.splitlines()[0] if markdown.splitlines() else "")
        if first_line:
            title_candidates.append(first_line)

    dedup: list[str] = []
    seen: set[str] = set()
    for candidate in title_candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(candidate[:300])

    return MarkerParseResult(pages=pages, blocks=blocks, title_candidates=dedup)


def parse_pdf_with_marker(pdf_path: str | Path, timeout_sec: float = 30.0) -> MarkerParseResult:
    path = Path(pdf_path)
    if not path.exists():
        raise MarkerParseError(f"pdf not found: {path}", stage="input_validation")

    try:
        converter_module = importlib.import_module("marker.converters.pdf")
        PdfConverter = getattr(converter_module, "PdfConverter")
    except Exception as exc:
        raise MarkerParseError(
            "marker unavailable: install marker-pdf to enable marker parser",
            stage="import_converter",
        ) from exc

    stage_timings: dict[str, float] = {}
    try:
        with _TimeoutGuard(timeout_sec):
            converter_started = time.perf_counter()
            converter = _create_pdf_converter(PdfConverter)
            stage_timings["converter_init_sec"] = round(time.perf_counter() - converter_started, 3)
            document_started = time.perf_counter()
            document = converter.build_document(str(path))
            stage_timings["convert_sec"] = round(time.perf_counter() - document_started, 3)
    except _ParseTimeoutError as exc:
        raise MarkerParseError(str(exc), stage="parse_timeout") from exc
    except Exception as exc:
        message = str(exc)
        stage = "parse_execute"
        if "artifact_dict" in message and ("required positional argument" in message or "missing" in message):
            stage = "converter_init"
        elif "Permission denied" in message and "cache" in message.lower():
            stage = "model_cache_access"
        raise MarkerParseError(f"marker parse failed: {message}", stage=stage) from exc

    try:
        normalize_started = time.perf_counter()
        markdown, raw_blocks = _extract_markdown_and_blocks(document, converter)
        result = _marker_to_intermediate(markdown, raw_blocks)
        stage_timings["output_conversion_sec"] = round(time.perf_counter() - normalize_started, 3)
    except Exception as exc:
        raise MarkerParseError(f"marker output conversion failed: {exc}", stage="output_conversion") from exc

    if not result.pages:
        raise MarkerParseError("marker parse produced empty pages", stage="empty_output")

    stage_timings["total_sec"] = round(sum(value for value in stage_timings.values()), 3)
    return MarkerParseResult(
        pages=result.pages,
        blocks=result.blocks,
        title_candidates=result.title_candidates,
        stage_timings=stage_timings,
    )
