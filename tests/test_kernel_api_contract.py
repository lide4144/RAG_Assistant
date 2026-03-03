from __future__ import annotations

import unittest
from unittest.mock import patch

from app.kernel_api import (
    KernelChatRequest,
    KernelChatResponse,
    SourceItem,
    _build_sources_from_qa_report,
    _run_qa_once,
    qa_stream,
)


class KernelApiContractTests(unittest.TestCase):
    def test_source_contract_isomorphic_fields(self) -> None:
        qa_report = {
            'evidence_grouped': [
                {
                    'paper_id': 'p1',
                    'paper_title': 'Paper A',
                    'evidence': [
                        {
                            'chunk_id': 'chunk-1',
                            'quote': 'alpha',
                            'section_page': 'p.1',
                            'source': 'graph_expand',
                            'score_rerank': 0.88,
                        }
                    ],
                }
            ]
        }
        sources = _build_sources_from_qa_report(qa_report)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].source_type, 'graph')
        self.assertEqual(sources[0].source_id, 'chunk-1')
        self.assertEqual(sources[0].title, 'Paper A')
        self.assertEqual(sources[0].snippet, 'alpha')
        self.assertEqual(sources[0].locator, 'p.1')

    def test_run_qa_once_contract(self) -> None:
        payload = KernelChatRequest(sessionId='s1', mode='local', query='q1', traceId='trace-1')

        with (
            patch('app.kernel_api.run_qa', return_value=0),
            patch(
                'app.kernel_api._load_qa_report',
                return_value={
                    'answer': 'hello [1]',
                    'evidence_grouped': [
                        {
                            'paper_id': 'p1',
                            'paper_title': 'Paper A',
                            'evidence': [
                                {
                                    'chunk_id': 'chunk-1',
                                    'quote': 'snippet',
                                    'section_page': 'p.1',
                                    'source': 'local',
                                    'score_rerank': 0.91,
                                }
                            ],
                        }
                    ],
                },
            ),
        ):
            response = _run_qa_once(payload)

        self.assertIsInstance(response, KernelChatResponse)
        self.assertEqual(response.traceId, 'trace-1')
        self.assertEqual(response.answer, 'hello [1]')
        self.assertEqual(len(response.sources), 1)
        self.assertIsInstance(response.sources[0], SourceItem)

    def test_stream_contract_mode_consistency_and_message_end(self) -> None:
        modes = ("local", "web", "hybrid")

        for mode in modes:
            with self.subTest(mode=mode):
                mocked_response = KernelChatResponse(
                    traceId=f"trace-{mode}",
                    answer="stream answer [1]",
                    sources=[
                        SourceItem(
                            source_type="local",
                            source_id="chunk-1",
                            title="Paper A",
                            snippet="snippet",
                            locator="p.1",
                            score=0.9,
                        )
                    ],
                )
                with patch("app.kernel_api._run_qa_once", return_value=mocked_response):
                    response = qa_stream(
                        KernelChatRequest(sessionId="s1", mode=mode, query="q1", history=[], traceId=f"trace-{mode}")
                    )
                    self.assertTrue((response.media_type or "").startswith("text/event-stream"))
                    self.assertIsNotNone(response.body_iterator)


if __name__ == '__main__':
    unittest.main()
