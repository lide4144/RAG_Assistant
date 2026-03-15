from __future__ import annotations

import unittest

from app.qa import _normalize_citations
from app.retrieve import RetrievalCandidate, apply_content_type_weights


class StructuredCitationContractTests(unittest.TestCase):
    def test_table_and_formula_blocks_receive_query_aware_weighting(self) -> None:
        weighted = apply_content_type_weights(
            [
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=1.0,
                    content_type="table_block",
                    block_type="Table",
                    structure_provenance={"source": "marker", "block_type": "Table"},
                ),
                RetrievalCandidate(
                    chunk_id="p1:2",
                    score=1.0,
                    content_type="formula_block",
                    block_type="Formula",
                    structure_provenance={"source": "marker", "block_type": "Formula"},
                ),
            ],
            query="请给我表格和公式证据",
            table_list_downweight=0.5,
        )

        self.assertTrue(all(row.score > 1.0 for row in weighted))

    def test_normalize_citations_preserves_structure_provenance(self) -> None:
        citations = [
            {
                "chunk_id": "p1:1",
                "paper_id": "p1",
                "section_page": "p.3",
                "block_type": "table_block",
                "structure_provenance": {"source": "marker", "block_type": "Table", "locator": "p.3"},
            }
        ]
        evidence_lookup = {
            "p1:1": {
                "paper_id": "p1",
                "section_page": "p.3",
                "block_type": "table_block",
                "structure_provenance": {"source": "marker", "block_type": "Table", "locator": "p.3"},
            }
        }

        normalized = _normalize_citations(citations, evidence_lookup)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["block_type"], "table_block")
        self.assertEqual(normalized[0]["structure_provenance"]["block_type"], "Table")


if __name__ == "__main__":
    unittest.main()
