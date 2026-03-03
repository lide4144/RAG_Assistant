from __future__ import annotations

import hashlib
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


def extract_title(metadata_title: str | None, pages: list[PageText]) -> str:
    if metadata_title and metadata_title.strip():
        return metadata_title.strip()

    if not pages:
        return "Untitled Paper"
    first_page = pages[0].text
    for line in first_page.splitlines():
        candidate = line.strip()
        if len(candidate) >= 8:
            return candidate[:300]
    return "Untitled Paper"


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
