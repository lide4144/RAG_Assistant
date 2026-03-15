from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.models import PageText

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None


def list_pdf_files(input_dir: str | Path | None) -> list[Path]:
    if input_dir is None:
        return []
    base = Path(input_dir)
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])


def make_paper_id(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()
    return digest[:12]


def pdf_content_fingerprint(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except Exception:
        payload = str(path.resolve()).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def stable_pdf_paper_id(path: Path) -> tuple[str, str]:
    fingerprint = pdf_content_fingerprint(path)
    return f"pdf_{fingerprint[:12]}", fingerprint


DEFAULT_TITLE_BLACKLIST_PATTERNS = [
    r"^\s*preprint\.?\s+under\s+review\.?\s*$",
    r"all rights reserved",
    r"copyright",
    r"arxiv preprint",
    r"provided proper attribution is provided",
    r"hereby grants permission to",
]


@dataclass
class TitleDecision:
    title: str
    source: str
    confidence: float
    adopted_layer: str = ""
    decision_trace: list[dict[str, str]] | None = None


def _normalize_structured_title_candidates(
    title_candidates: list[str] | list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in title_candidates or []:
        if isinstance(row, dict):
            text = _normalize_title_spaces(str(row.get("text", "")))
            if not text:
                continue
            normalized.append(
                {
                    "text": text[:300],
                    "source": str(row.get("source", "marker")).strip() or "marker",
                    "priority": int(row.get("priority", 99) or 99),
                    "page": int(row.get("page", 1) or 1),
                    "heading_level": row.get("heading_level"),
                    "from_markdown": bool(row.get("from_markdown")),
                }
            )
            continue
        text = _normalize_title_spaces(str(row or ""))
        if text:
            normalized.append(
                {
                    "text": text[:300],
                    "source": "marker",
                    "priority": 99,
                    "page": 1,
                    "heading_level": None,
                    "from_markdown": False,
                }
            )
    return normalized


def compile_title_blacklist_patterns(patterns: list[str] | None = None) -> list[re.Pattern[str]]:
    raw_patterns = list(patterns or DEFAULT_TITLE_BLACKLIST_PATTERNS)
    compiled: list[re.Pattern[str]] = []
    for pattern in raw_patterns:
        text = str(pattern or "").strip()
        if not text:
            continue
        try:
            compiled.append(re.compile(text, re.IGNORECASE))
        except re.error:
            continue
    if compiled:
        return compiled
    return [re.compile(p, re.IGNORECASE) for p in DEFAULT_TITLE_BLACKLIST_PATTERNS]


def _is_blacklisted_title(candidate: str, blacklist_patterns: list[re.Pattern[str]] | None = None) -> bool:
    text = str(candidate or "").strip()
    if not text:
        return True
    patterns = blacklist_patterns or compile_title_blacklist_patterns()
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False


def _normalize_title_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -:#\t\r\n")


def _expand_title_candidate_variants(candidate: str) -> list[str]:
    text = _normalize_title_spaces(candidate)
    if not text:
        return []

    variants: list[str] = []

    for line in re.split(r"[\r\n]+", candidate):
        normalized = _normalize_title_spaces(line)
        if len(normalized) >= 8:
            variants.append(normalized)

    without_tags = _normalize_title_spaces(re.sub(r"<[^>]+>", " ", text))
    if without_tags:
        variants.append(without_tags)

    heading_matches = re.findall(r"#\s+(.+?)(?=\s+#\s+|$)", without_tags)
    extracted_headings = [_normalize_title_spaces(match) for match in heading_matches if _normalize_title_spaces(match)]
    variants.extend(extracted_headings)
    if not extracted_headings and text:
        variants.append(text)

    cleaned_variants: list[str] = []
    seen: set[str] = set()
    for value in variants:
        normalized = _normalize_title_spaces(value)
        if not normalized:
            continue
        # Trim common author/affiliation tails after obvious separators.
        normalized = re.split(r"\babstract\b", normalized, maxsplit=1, flags=re.IGNORECASE)[0]
        normalized = re.split(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", normalized, maxsplit=1)[0]
        normalized = _normalize_title_spaces(normalized)
        if len(normalized) < 8:
            continue
        if _is_blacklisted_title(normalized):
            continue
        words = normalized.split()
        # Generate short prefixes so a good title can win over a long title+author blob.
        if len(words) >= 5:
            for size in range(5, min(len(words), 16) + 1):
                prefix = _normalize_title_spaces(" ".join(words[:size]))
                if len(prefix) >= 8 and not _is_blacklisted_title(prefix):
                    cleaned_variants.append(prefix)
        cleaned_variants.append(normalized)

    unique: list[str] = []
    for value in cleaned_variants:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value[:300])
    return unique


def score_title_candidate(candidate: str, blacklist_patterns: list[re.Pattern[str]] | None = None) -> float:
    text = str(candidate or "").strip()
    if not text:
        return 0.0
    if _is_blacklisted_title(text, blacklist_patterns=blacklist_patterns):
        return 0.0
    length = len(text)
    if length < 8:
        return 0.1
    if length > 260:
        return 0.2
    punctuation_penalty = 0.0
    if text.count(".") > 2:
        punctuation_penalty += 0.1
    if text.isupper():
        punctuation_penalty += 0.2
    words = text.split()
    if len(words) < 4:
        punctuation_penalty += 0.15
    if len(words) > 20:
        punctuation_penalty += 0.1
    if re.search(r"@[A-Za-z0-9.-]+\.", text):
        punctuation_penalty += 0.3
    if re.search(r"\b(google|university|brain|research|department)\b", text, re.IGNORECASE):
        punctuation_penalty += 0.15
    base = 0.85
    score = max(0.0, min(1.0, base - punctuation_penalty))
    return score


def choose_best_title(
    *,
    metadata_title: str | None,
    pages: list[PageText],
    title_candidates: list[str] | list[dict[str, object]] | None = None,
    confidence_threshold: float = 0.6,
    blacklist_patterns: list[str] | None = None,
) -> TitleDecision:
    compiled_blacklist = compile_title_blacklist_patterns(blacklist_patterns)
    structured_candidates = _normalize_structured_title_candidates(title_candidates)
    fallback_first_line = ""
    if pages:
        first_page = pages[0].text
        for line in first_page.splitlines():
            candidate = line.strip()
            if len(candidate) >= 8:
                fallback_first_line = candidate[:300]
                break

    layers: list[tuple[str, list[dict[str, object]]]] = [
        ("marker_h1", [row for row in structured_candidates if str(row.get("source")) == "marker_h1"]),
        ("marker_h2", [row for row in structured_candidates if str(row.get("source")) == "marker_h2"]),
        (
            "marker_markdown_first_line",
            [row for row in structured_candidates if str(row.get("source")) == "marker_markdown_first_line"],
        ),
        ("marker", [row for row in structured_candidates if str(row.get("source")) == "marker"]),
        (
            "metadata",
            [{"text": str(metadata_title).strip(), "source": "metadata", "priority": 4}] if metadata_title and str(metadata_title).strip() else [],
        ),
        (
            "fallback_first_line",
            [{"text": fallback_first_line, "source": "fallback_first_line", "priority": 5}] if fallback_first_line else [],
        ),
    ]

    trace: list[dict[str, str]] = []
    for layer_name, candidates in layers:
        if not candidates:
            trace.append({"layer": layer_name, "status": "missing", "reason": "no_candidates"})
            continue
        best_title = ""
        best_score = 0.0
        rejected_reasons: list[str] = []
        for candidate_row in candidates:
            candidate = str(candidate_row.get("text", "")).strip()
            for expanded_candidate in _expand_title_candidate_variants(candidate):
                score = score_title_candidate(expanded_candidate, blacklist_patterns=compiled_blacklist)
                if score <= 0.0:
                    rejected_reasons.append("quality_gate_rejected")
                    continue
                if score > best_score:
                    best_title = expanded_candidate[:300]
                    best_score = score
        if not best_title:
            trace.append({"layer": layer_name, "status": "rejected", "reason": rejected_reasons[-1] if rejected_reasons else "quality_gate_rejected"})
            continue
        if best_score < float(confidence_threshold):
            trace.append({"layer": layer_name, "status": "rejected", "reason": "below_confidence_threshold"})
            continue
        trace.append({"layer": layer_name, "status": "accepted", "reason": "selected"})
        return TitleDecision(
            title=best_title,
            source=layer_name,
            confidence=best_score,
            adopted_layer=layer_name,
            decision_trace=trace,
        )

        return TitleDecision(
            title="Untitled Paper",
            source="fallback_untitled",
            confidence=0.0,
            adopted_layer="fallback_untitled",
            decision_trace=trace,
        )
    return TitleDecision(
        title="Untitled Paper",
        source="fallback_untitled",
        confidence=0.0,
        adopted_layer="fallback_untitled",
        decision_trace=trace,
    )


def extract_title(metadata_title: str | None, pages: list[PageText]) -> str:
    decision = choose_best_title(
        metadata_title=metadata_title,
        pages=pages,
        title_candidates=None,
        confidence_threshold=0.0,
    )
    return decision.title


def parse_pdf_pages(pdf_path: str | Path) -> tuple[list[PageText], list[str], str | None]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is required. Please install package `pymupdf`.")

    path = Path(pdf_path)
    pages: list[PageText] = []
    page_errors: list[str] = []
    metadata_title: str | None = None

    doc = fitz.open(path)
    try:
        metadata_title = (doc.metadata or {}).get("title")
        for idx in range(len(doc)):
            page_num = idx + 1
            try:
                text = doc[idx].get_text("text")
                text = text.strip()
                if text:
                    pages.append(PageText(page_num=page_num, text=text))
            except Exception as exc:  # pragma: no cover
                page_errors.append(f"{path.name}: page {page_num} parse failed: {exc}")
                continue
    finally:
        doc.close()

    return pages, page_errors, metadata_title
