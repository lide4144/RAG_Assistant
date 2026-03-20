from __future__ import annotations

import unittest

from app.qa import _apply_evidence_policy_gate, _extract_key_claims


class M7EvidencePolicyTests(unittest.TestCase):
    def test_extract_key_claims_detects_numeric_experiment_and_definition(self) -> None:
        answer = (
            "The experiment shows accuracy reaches 92.1 on this benchmark. "
            "Retrieval calibration is defined as adapting query intent to evidence."
        )
        claims = _extract_key_claims(answer)
        self.assertEqual(len(claims), 2)
        all_types = {t for c in claims for t in c["types"]}
        self.assertIn("numeric", all_types)
        self.assertIn("experiment", all_types)
        self.assertIn("definition", all_types)

    def test_gate_passes_when_claim_supported_and_normalizes_citation(self) -> None:
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "c:1",
                        "section_page": "p.2",
                        "quote": "The experiment reports 92.1 accuracy on the benchmark set.",
                    }
                ],
            }
        ]
        answer = "The experiment reports 92.1 accuracy under the benchmark setting."
        warnings: list[str] = []
        gated_answer, citations, gate_report = _apply_evidence_policy_gate(
            question="What is the accuracy?",
            answer=answer,
            answer_citations=[{"chunk_id": "c:1", "paper_id": "p1", "section_page": ""}],
            evidence_grouped=evidence_grouped,
            output_warnings=warnings,
            policy_enforced=True,
        )

        self.assertEqual(gated_answer, answer)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["section_page"], "p.2")
        self.assertFalse(gate_report.get("triggered"))
        self.assertEqual(warnings, [])

    def test_gate_triggers_m8_when_claim_not_supported(self) -> None:
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "c:1",
                        "section_page": "p.2",
                        "quote": "The paper discusses limitations and future work.",
                    }
                ],
            }
        ]
        answer = "The experiment reports 95.0 accuracy on this task."
        warnings: list[str] = []
        gated_answer, citations, gate_report = _apply_evidence_policy_gate(
            question="What is the accuracy?",
            answer=answer,
            answer_citations=[{"chunk_id": "c:1", "paper_id": "p1", "section_page": "p.2"}],
            evidence_grouped=evidence_grouped,
            output_warnings=warnings,
            policy_enforced=True,
        )

        self.assertEqual(gated_answer, answer)
        self.assertEqual(citations, [])
        self.assertTrue(gate_report.get("triggered"))
        self.assertEqual(gate_report.get("constraints_envelope", {}).get("reason_code"), "evidence_policy_gate_claim_not_supported")
        self.assertTrue(gate_report.get("constraints_envelope", {}).get("guardrail_blocked"))
        self.assertIn("insufficient_evidence_for_answer", warnings)

    def test_gate_can_be_disabled(self) -> None:
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "c:1",
                        "section_page": "p.2",
                        "quote": "unrelated quote",
                    }
                ],
            }
        ]
        answer = "The experiment reports 95.0 accuracy on this task."
        warnings: list[str] = []
        gated_answer, citations, gate_report = _apply_evidence_policy_gate(
            question="What is the accuracy?",
            answer=answer,
            answer_citations=[{"chunk_id": "c:1", "paper_id": "p1", "section_page": "p.2"}],
            evidence_grouped=evidence_grouped,
            output_warnings=warnings,
            policy_enforced=False,
        )

        self.assertEqual(gated_answer, answer)
        self.assertEqual(len(citations), 1)
        self.assertFalse(gate_report.get("enabled"))
        self.assertEqual(gate_report.get("failed_claims"), [])
        self.assertEqual(warnings, [])

    def test_gate_triggers_when_citation_not_in_evidence_grouped(self) -> None:
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "c:1",
                        "section_page": "p.2",
                        "quote": "The experiment reports 92.1 accuracy on benchmark.",
                    }
                ],
            }
        ]
        warnings: list[str] = []
        gated_answer, citations, gate_report = _apply_evidence_policy_gate(
            question="What is the accuracy?",
            answer="The experiment reports 92.1 accuracy on benchmark.",
            answer_citations=[{"chunk_id": "c:404", "paper_id": "p9", "section_page": "p.9"}],
            evidence_grouped=evidence_grouped,
            output_warnings=warnings,
            policy_enforced=True,
        )
        self.assertEqual(gated_answer, "The experiment reports 92.1 accuracy on benchmark.")
        self.assertEqual(citations, [])
        self.assertTrue(gate_report.get("triggered"))
        self.assertEqual(gate_report.get("constraints_envelope", {}).get("citation_status"), "claim_not_supported")
        self.assertIn("insufficient_evidence_for_answer", warnings)

    def test_extract_key_claims_ignores_uncertainty_disclaimer(self) -> None:
        answer = (
            "Transformer is defined as a self-attention based architecture. "
            "然而，证据中没有明确说明 Transformer 的具体用途，因此信息不足。"
        )
        claims = _extract_key_claims(answer)
        self.assertEqual(len(claims), 1)
        self.assertIn("definition", claims[0]["types"])
        self.assertNotIn("没有明确说明", claims[0]["text"])

    def test_gate_does_not_trigger_on_uncertainty_only_sentence(self) -> None:
        evidence_grouped = [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "c:1",
                        "section_page": "p.2",
                        "quote": "The paper introduces Transformer with self-attention.",
                    }
                ],
            }
        ]
        answer = "然而，证据中没有明确说明 Transformer 的具体用途，因此信息不足。"
        warnings: list[str] = []
        gated_answer, citations, gate_report = _apply_evidence_policy_gate(
            question="Transformer有什么用？",
            answer=answer,
            answer_citations=[{"chunk_id": "c:1", "paper_id": "p1", "section_page": "p.2"}],
            evidence_grouped=evidence_grouped,
            output_warnings=warnings,
            policy_enforced=True,
        )

        self.assertEqual(gated_answer, answer)
        self.assertEqual(len(citations), 1)
        self.assertFalse(gate_report.get("triggered"))
        self.assertEqual(gate_report.get("claim_count"), 0)
        self.assertEqual(gate_report.get("failed_claims"), [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
