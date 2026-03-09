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
    base = 0.85
    score = max(0.0, min(1.0, base - punctuation_penalty))
    return score


def choose_best_title(
    *,
    metadata_title: str | None,
    pages: list[PageText],
    title_candidates: list[str] | None = None,
    confidence_threshold: float = 0.6,
    blacklist_patterns: list[str] | None = None,
) -> TitleDecision:
    compiled_blacklist = compile_title_blacklist_patterns(blacklist_patterns)
    candidates: list[tuple[str, str]] = []
    if metadata_title and str(metadata_title).strip():
        candidates.append((str(metadata_title).strip(), "metadata"))
    if title_candidates:
        for row in title_candidates:
            candidate = str(row or "").strip()
            if candidate:
                candidates.append((candidate, "marker"))
    if pages:
        first_page = pages[0].text
        for line in first_page.splitlines():
            candidate = line.strip()
            if len(candidate) >= 8:
                candidates.append((candidate[:300], "fallback_first_line"))
                break

    best_title = "Untitled Paper"
    best_source = "fallback_untitled"
    best_score = 0.0
    for candidate, source in candidates:
        score = score_title_candidate(candidate, blacklist_patterns=compiled_blacklist)
        if score <= 0.0:
            continue
        if score > best_score:
            best_title = candidate[:300]
            best_source = source
            best_score = score

    if best_score < float(confidence_threshold):
        return TitleDecision(
            title="Untitled Paper",
            source="fallback_untitled",
            confidence=best_score,
        )

    return TitleDecision(title=best_title, source=best_source, confidence=best_score)


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
