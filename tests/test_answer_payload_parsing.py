from __future__ import annotations

import unittest

from app.qa import _parse_answer_payload


class AnswerPayloadParsingTests(unittest.TestCase):
    def test_parse_json_fenced_payload(self) -> None:
        content = """```json
{
  "answer": "hello",
  "answer_citations": [{"chunk_id":"c1","paper_id":"p1","section_page":"p.1"}]
}
```"""
        answer, citations, warning = _parse_answer_payload(content=content)
        self.assertEqual(warning, None)
        self.assertEqual(answer, "hello")
        self.assertEqual(citations, [{"chunk_id": "c1", "paper_id": "p1", "section_page": "p.1"}])

    def test_parse_yaml_payload(self) -> None:
        content = """```yaml
answer: "yaml answer"
answer_citations:
  - chunk_id: c1
    paper_id: p1
    section_page: p.2
```"""
        answer, citations, warning = _parse_answer_payload(content=content)
        self.assertEqual(warning, None)
        self.assertEqual(answer, "yaml answer")
        self.assertEqual(citations, [{"chunk_id": "c1", "paper_id": "p1", "section_page": "p.2"}])

    def test_parse_markdown_unstructured_payload(self) -> None:
        content = """```markdown
## Conclusion
Transformer is a model architecture.

## Evidence
- [1] from paper A.
```"""
        answer, citations, warning = _parse_answer_payload(content=content)
        self.assertEqual(warning, None)
        self.assertIn("Conclusion", answer or "")
        self.assertEqual(citations, [])

    def test_parse_html_unstructured_payload(self) -> None:
        content = "<p><strong>Conclusion:</strong> Transformer works.</p><p>Evidence: paper A.</p>"
        answer, citations, warning = _parse_answer_payload(content=content)
        self.assertEqual(warning, None)
        self.assertIn("Conclusion:", answer or "")
        self.assertIn("Evidence:", answer or "")
        self.assertEqual(citations, [])


if __name__ == "__main__":
    unittest.main()

