from __future__ import annotations

import unittest

from app.chunker import build_chunks
from app.models import PageText


class ChunkerStructuredSegmentsTests(unittest.TestCase):
    def test_structured_segments_are_prioritized_over_page_text(self) -> None:
        pages = [PageText(page_num=1, text="fallback text should not be used")]
        structured_segments = [
            {"page": 1, "text": "section one body"},
            {"page": 2, "text": "section two body"},
        ]

        chunks = build_chunks(
            paper_id="p1",
            pages=pages,
            chunk_size=50,
            overlap=5,
            structured_segments=structured_segments,
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].text, "section one body")
        self.assertEqual(chunks[1].text, "section two body")

    def test_empty_structured_segments_falls_back_and_preserves_overlap(self) -> None:
        pages = [PageText(page_num=1, text="w1 w2 w3 w4 w5 w6 w7")]

        chunks = build_chunks(
            paper_id="p2",
            pages=pages,
            chunk_size=4,
            overlap=1,
            structured_segments=[],
        )

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].text.split(), ["w1", "w2", "w3", "w4"])
        self.assertEqual(chunks[1].text.split(), ["w4", "w5", "w6", "w7"])

    def test_heading_level_drives_structured_section_grouping(self) -> None:
        pages = [PageText(page_num=1, text="fallback")]
        structured_segments = [
            {"page": 1, "text": "1 Introduction", "heading_level": 1},
            {"page": 1, "text": "intro body"},
            {"page": 2, "text": "2 Method", "heading_level": 1},
            {"page": 2, "text": "method body"},
        ]

        chunks = build_chunks(
            paper_id="p3",
            pages=pages,
            chunk_size=200,
            overlap=10,
            structured_segments=structured_segments,
        )

        self.assertEqual(len(chunks), 2)
        self.assertIn("1 Introduction", chunks[0].text)
        self.assertIn("intro body", chunks[0].text)
        self.assertIn("2 Method", chunks[1].text)
        self.assertIn("method body", chunks[1].text)


if __name__ == "__main__":
    unittest.main()
