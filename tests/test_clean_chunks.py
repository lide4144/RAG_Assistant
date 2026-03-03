from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.clean_chunks import (
    clean_chunk_record,
    merge_short_fragments,
    run_clean_chunks,
)
from app.retrieve import RetrievalCandidate, apply_content_type_weights


class CleanRulesTests(unittest.TestCase):
    def test_watermark_url_controls_and_flags(self) -> None:
        record = {
            "chunk_id": "paper:00001",
            "paper_id": "paper",
            "page_start": 1,
            "text": (
                "Hello\x00 World\n"
                "Authorized licensed use limited to test\n"
                "See https://example.com/path?q=1 now"
            ),
        }
        cleaned = clean_chunk_record(record)
        self.assertNotIn("Authorized licensed use limited to", cleaned.clean_text)
        self.assertIn("<URL>", cleaned.clean_text)
        self.assertIn("has_url", cleaned.quality_flags)
        self.assertNotIn("\x00", cleaned.clean_text)

    def test_content_type_classification(self) -> None:
        self.assertEqual(
            clean_chunk_record(
                {
                    "chunk_id": "p:1",
                    "paper_id": "p",
                    "page_start": 1,
                    "text": "Journal of Usability Studies. 2020;16(1):49.",
                }
            ).content_type,
            "reference",
        )
        self.assertEqual(
            clean_chunk_record(
                {
                    "chunk_id": "p:2",
                    "paper_id": "p",
                    "page_start": 1,
                    "text": "Character: [Greet the player]",
                }
            ).content_type,
            "dialogue_script",
        )
        self.assertEqual(
            clean_chunk_record(
                {
                    "chunk_id": "p:3",
                    "paper_id": "p",
                    "page_start": 1,
                    "text": "amgrow@calpoly.edu",
                }
            ).content_type,
            "front_matter",
        )
        self.assertEqual(
            clean_chunk_record(
                {
                    "chunk_id": "p:4",
                    "paper_id": "p",
                    "page_start": 1,
                    "text": "APPENDIX\nCharacter: [Greet the player]",
                }
            ).content_type,
            "dialogue_script",
        )

    def test_merge_short_fragments_same_page(self) -> None:
        records = []
        for i in range(1, 7):
            records.append(
                clean_chunk_record(
                    {
                        "chunk_id": f"paper:0000{i}",
                        "paper_id": "paper",
                        "page_start": 1,
                        "text": f"ChatGPT item {i}",
                    }
                )
            )
        merged = merge_short_fragments(records)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].content_type, "table_list")
        self.assertIn("short_fragment_merged", merged[0].quality_flags)
        self.assertEqual(len(merged[0].merged_from or []), 6)

    def test_merge_short_fragments_not_cross_page(self) -> None:
        records = []
        for i in range(1, 4):
            records.append(
                clean_chunk_record(
                    {
                        "chunk_id": f"paper:0000{i}",
                        "paper_id": "paper",
                        "page_start": 1,
                        "text": f"a{i}",
                    }
                )
            )
        for i in range(4, 7):
            records.append(
                clean_chunk_record(
                    {
                        "chunk_id": f"paper:0000{i}",
                        "paper_id": "paper",
                        "page_start": 2,
                        "text": f"b{i}",
                    }
                )
            )
        merged = merge_short_fragments(records)
        self.assertEqual(len(merged), 6)


class AcceptanceSampleTests(unittest.TestCase):
    def test_required_samples(self) -> None:
        src = Path("data/processed/chunks.jsonl")
        if not src.exists():
            self.skipTest("data/processed/chunks.jsonl is missing")

        target_ids = {
            "eff6f9d4b754:00109",
            "eff6f9d4b754:00094",
            "eff6f9d4b754:00093",
            "eff6f9d4b754:00095",
            "67978670bdb6:00004",
        }
        mapping: dict[str, dict] = {}
        with src.open("r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                cid = item.get("chunk_id")
                if cid in target_ids:
                    mapping[cid] = item
        if set(mapping.keys()) != target_ids:
            self.skipTest("required acceptance chunk ids are not all present in local data")

        c00109 = clean_chunk_record(mapping["eff6f9d4b754:00109"])
        self.assertNotIn("Authorized licensed use limited to", c00109.clean_text)

        c00094 = clean_chunk_record(mapping["eff6f9d4b754:00094"])
        self.assertIn("<URL>", c00094.clean_text)
        self.assertIn("has_url", c00094.quality_flags)

        c00093 = clean_chunk_record(mapping["eff6f9d4b754:00093"])
        self.assertEqual(c00093.content_type, "reference")

        c00095 = clean_chunk_record(mapping["eff6f9d4b754:00095"])
        self.assertEqual(c00095.content_type, "dialogue_script")

        cfront = clean_chunk_record(mapping["67978670bdb6:00004"])
        self.assertEqual(cfront.content_type, "front_matter")

    def test_cli_produces_clean_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "chunks.jsonl"
            out = Path(tmp) / "chunks_clean.jsonl"
            src.write_text(
                json.dumps(
                    {
                        "chunk_id": "a:00001",
                        "paper_id": "a",
                        "page_start": 1,
                        "text": "APPENDIX\nDownloaded on now\nhttps://example.com",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            code = run_clean_chunks(src, out)
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            line = json.loads(out.read_text(encoding="utf-8").strip())
            self.assertIn("clean_text", line)
            self.assertIn("content_type", line)
            self.assertIn("quality_flags", line)


class RetrievalWeightingTests(unittest.TestCase):
    def test_table_list_is_downweighted_but_kept(self) -> None:
        candidates = [
            RetrievalCandidate(chunk_id="a", score=1.0, content_type="table_list"),
            RetrievalCandidate(chunk_id="b", score=1.0, content_type="body"),
        ]
        weighted = apply_content_type_weights(candidates, table_list_downweight=0.5)
        self.assertEqual(len(weighted), 2)
        self.assertAlmostEqual(weighted[0].score, 0.5)
        self.assertAlmostEqual(weighted[1].score, 1.0)


if __name__ == "__main__":
    unittest.main()
