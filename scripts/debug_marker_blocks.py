from __future__ import annotations

import argparse
from pathlib import Path

from app.marker_parser import parse_pdf_with_marker


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect raw Marker block objects for a PDF.")
    parser.add_argument(
        "--pdf",
        default="data/papers/Attention Is All You Need.pdf",
        help="Path to the PDF to inspect.",
    )
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        raise SystemExit(f"pdf not found: {pdf}")

    print("pdf:", pdf)
    result = parse_pdf_with_marker(pdf, timeout_sec=300)
    print("pages:", len(result.pages))
    print("blocks:", len(result.blocks))
    print("unique page nums:", sorted({block.page_num for block in result.blocks})[:50])
    print("title candidates:", result.title_candidates[:10])
    if result.blocks:
        first = result.blocks[0]
        print("first normalized block:", first)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
