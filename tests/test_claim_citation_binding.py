from __future__ import annotations

import unittest

from app.qa import _bind_claim_plan_to_citations


class ClaimCitationBindingTests(unittest.TestCase):
    def test_binding_keeps_llm_answer_when_claims_are_bound(self) -> None:
        claim_plan = [
            {
                "claim": "A improves B",
                "chunk_id": "c1",
                "paper_id": "p1",
                "section_page": "p.1",
            },
            {
                "claim": "C outperforms D",
                "chunk_id": "c2",
                "paper_id": "p2",
                "section_page": "p.2",
            },
        ]
        answer = "Result A [1] and C [2]."
        answer_citations = [
            {"chunk_id": "c1", "paper_id": "p1", "section_page": "p.1"},
            {"chunk_id": "c2", "paper_id": "p2", "section_page": "p.2"},
        ]
        evidence_grouped = [
            {
                "paper_id": "p1",
                "evidence": [
                    {"chunk_id": "c1", "section_page": "p.1", "quote": "A improves B"}
                ],
            },
            {
                "paper_id": "p2",
                "evidence": [
                    {
                        "chunk_id": "c2",
                        "section_page": "p.2",
                        "quote": "C outperforms D",
                    }
                ],
            },
        ]

        bound_answer, bound_citations, report = _bind_claim_plan_to_citations(
            claim_plan=claim_plan,
            answer=answer,
            answer_citations=answer_citations,
            evidence_grouped=evidence_grouped,
        )

        self.assertEqual(bound_answer, answer)
        self.assertEqual(len(bound_citations), 2)
        self.assertFalse(report["fallback_to_staged"])
        self.assertEqual(report["binding_ratio"], 1.0)

    def test_binding_falls_back_to_staged_when_claims_not_bound(self) -> None:
        """Test that when claim binding is insufficient, system marks fallback
        and returns empty answer (letting caller retry with LLM).

        Previously this would return hardcoded "claim -> citation" answer.
        Now it returns empty string to trigger LLM regeneration.
        """
        claim_plan = [
            {
                "claim": "A improves B",
                "chunk_id": "c1",
                "paper_id": "p1",
                "section_page": "p.1",
            },
            {
                "claim": "C outperforms D",
                "chunk_id": "c2",
                "paper_id": "p2",
                "section_page": "p.2",
            },
        ]
        answer = "Only one cited [1]."
        answer_citations = [{"chunk_id": "c1", "paper_id": "p1", "section_page": "p.1"}]
        evidence_grouped = [
            {
                "paper_id": "p1",
                "evidence": [
                    {"chunk_id": "c1", "section_page": "p.1", "quote": "A improves B"}
                ],
            },
            {
                "paper_id": "p2",
                "evidence": [
                    {
                        "chunk_id": "c2",
                        "section_page": "p.2",
                        "quote": "C outperforms D",
                    }
                ],
            },
        ]

        bound_answer, bound_citations, report = _bind_claim_plan_to_citations(
            claim_plan=claim_plan,
            answer=answer,
            answer_citations=answer_citations,
            evidence_grouped=evidence_grouped,
        )

        self.assertTrue(report["fallback_to_staged"])
        self.assertEqual(report["fallback_reason"], "claim_binding_insufficient")
        self.assertEqual(report["bound_claim_count"], 1)
        self.assertEqual(report["missing_claim_chunk_ids"], ["c2"])
        # New behavior: return empty string to trigger LLM regeneration
        # instead of hardcoded "claim -> citation" answer
        self.assertEqual(bound_answer, "")
        self.assertEqual(len(bound_citations), 0)


if __name__ == "__main__":
    unittest.main()
