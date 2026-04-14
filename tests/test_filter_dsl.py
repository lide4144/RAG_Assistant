"""Tests for filter DSL conversion."""

import pytest
from app.vector_store.memory_store import MemoryVectorStore
from app.vector_store.base import Document


class TestFilterDSL:
    """Test filter DSL implementation."""

    @pytest.fixture
    def store(self):
        return MemoryVectorStore(config={})

    @pytest.fixture
    def sample_docs(self):
        return [
            Document(
                doc_id="doc-001",
                paper_id="paper-001",
                content_type="body",
                page_start=1,
                text="First",
                clean_text="First",
                embedding=[1.0, 0.0],
                metadata={"year": 2023, "category": "ai"},
            ),
            Document(
                doc_id="doc-002",
                paper_id="paper-001",
                content_type="abstract",
                page_start=2,
                text="Second",
                clean_text="Second",
                embedding=[0.0, 1.0],
                metadata={"year": 2023, "category": "ml"},
            ),
            Document(
                doc_id="doc-003",
                paper_id="paper-002",
                content_type="body",
                page_start=5,
                text="Third",
                clean_text="Third",
                embedding=[0.5, 0.5],
                metadata={"year": 2024, "category": "ai"},
            ),
        ]

    def test_exact_match_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        results = store.search([1.0, 1.0], top_k=10, filters={"paper_id": "paper-001"})
        assert len(results) == 2
        for doc, _ in results:
            assert doc.paper_id == "paper-001"

    def test_multi_value_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        results = store.search(
            [1.0, 1.0], top_k=10, filters={"content_type": ["body", "title"]}
        )
        assert len(results) == 2
        for doc, _ in results:
            assert doc.content_type in ["body", "title"]

    def test_gte_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        results = store.search([1.0, 1.0], top_k=10, filters={"page_start": {"gte": 2}})
        assert len(results) == 2
        for doc, _ in results:
            assert doc.page_start >= 2

    def test_lte_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        results = store.search([1.0, 1.0], top_k=10, filters={"page_start": {"lte": 2}})
        assert len(results) == 2
        for doc, _ in results:
            assert doc.page_start <= 2

    def test_range_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        results = store.search(
            [1.0, 1.0], top_k=10, filters={"page_start": {"gte": 1, "lte": 3}}
        )
        assert len(results) == 2
        for doc, _ in results:
            assert 1 <= doc.page_start <= 3

    def test_combined_filters(self, store, sample_docs):
        store.add_documents(sample_docs)
        results = store.search(
            [1.0, 1.0],
            top_k=10,
            filters={
                "paper_id": "paper-001",
                "content_type": "body",
            },
        )
        assert len(results) == 1
        assert results[0][0].doc_id == "doc-001"

    def test_metadata_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        # This tests the metadata filtering through the metadata field
        # Note: In real implementation, metadata fields need special handling
        results = store.search(
            [1.0, 1.0], top_k=10, filters={"metadata": {"year": 2023}}
        )
        # Memory store doesn't support nested metadata filtering yet
        # This is a placeholder for when it's implemented
