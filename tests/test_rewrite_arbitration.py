from __future__ import annotations

import unittest
from unittest.mock import patch

from app.config import PipelineConfig
from app.qa import _rewrite_candidate_metrics
from app.retrieve import RetrievalCandidate


class RewriteArbitrationTests(unittest.TestCase):
    def test_rewrite_candidate_metrics_contains_expected_signals(self) -> None:
        config = PipelineConfig()
        fake_candidates = [
            RetrievalCandidate(
                chunk_id='c1',
                score=0.9,
                content_type='body',
                payload={'score_retrieval': 0.9, 'score_rerank': 0.92, 'source': 'local', 'dense_backend': 'tfidf'},
                paper_id='p1',
                page_start=1,
                section='s1',
                text='alpha',
                clean_text='alpha',
            ),
            RetrievalCandidate(
                chunk_id='c2',
                score=0.7,
                content_type='body',
                payload={'score_retrieval': 0.7, 'score_rerank': 0.72, 'source': 'local', 'dense_backend': 'tfidf'},
                paper_id='p2',
                page_start=2,
                section='s2',
                text='beta',
                clean_text='beta',
            ),
        ]

        with (
            patch('app.qa.retrieve_candidates', return_value=fake_candidates),
            patch(
                'app.qa.rerank_candidates',
                return_value=type('RerankOutcome', (), {'candidates': fake_candidates})(),
            ),
        ):
            metrics = _rewrite_candidate_metrics(
                query='test query',
                mode='hybrid',
                top_k=8,
                bm25_index={},
                vec_index=None,
                embed_index=None,
                config=config,
            )

        self.assertIn('retrieval_quality', metrics)
        self.assertIn('rerank_margin', metrics)
        self.assertIn('citation_coverage', metrics)
        self.assertIn('final_score', metrics)
        self.assertGreater(metrics['final_score'], 0.0)


if __name__ == '__main__':
    unittest.main()
