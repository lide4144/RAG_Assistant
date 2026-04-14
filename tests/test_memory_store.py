"""Tests for memory vector store implementation."""

import pytest
import numpy as np
from app.vector_store.memory_store import MemoryVectorStore
from app.vector_store.base import Document


class TestMemoryVectorStore:
    """Test MemoryVectorStore."""

    @pytest.fixture
    def store(self):
        return MemoryVectorStore(config={"index_dir": "data/indexes"})

    @pytest.fixture
    def sample_docs(self):
        return [
            Document(
                doc_id="doc-001",
                paper_id="paper-001",
                content_type="body",
                page_start=1,
                text="First document",
                clean_text="First document",
                embedding=[1.0, 0.0, 0.0],
            ),
            Document(
                doc_id="doc-002",
                paper_id="paper-001",
                content_type="body",
                page_start=2,
                text="Second document",
                clean_text="Second document",
                embedding=[0.0, 1.0, 0.0],
            ),
            Document(
                doc_id="doc-003",
                paper_id="paper-002",
                content_type="abstract",
                page_start=1,
                text="Third document",
                clean_text="Third document",
                embedding=[0.0, 0.0, 1.0],
            ),
        ]

    def test_add_documents(self, store, sample_docs):
        doc_ids = store.add_documents(sample_docs)
        assert len(doc_ids) == 3
        assert doc_ids == ["doc-001", "doc-002", "doc-003"]

    def test_get_document(self, store, sample_docs):
        store.add_documents(sample_docs)
        doc = store.get_document("doc-001")
        assert doc is not None
        assert doc.doc_id == "doc-001"
        assert doc.text == "First document"

    def test_get_document_not_found(self, store):
        doc = store.get_document("non-existent")
        assert doc is None

    def test_delete_documents(self, store, sample_docs):
        store.add_documents(sample_docs)
        count = store.delete_documents(["doc-001", "doc-002"])
        assert count == 2
        assert store.get_document("doc-001") is None
        assert store.get_document("doc-002") is None
        assert store.get_document("doc-003") is not None

    def test_update_document(self, store, sample_docs):
        store.add_documents(sample_docs)
        updated_doc = Document(
            doc_id="doc-001",
            paper_id="paper-001",
            content_type="body",
            page_start=1,
            text="Updated document",
            clean_text="Updated document",
            embedding=[1.0, 0.0, 0.0],
        )
        result = store.update_document("doc-001", updated_doc)
        assert result is True
        doc = store.get_document("doc-001")
        assert doc.text == "Updated document"

    def test_search(self, store, sample_docs):
        store.add_documents(sample_docs)
        # Search with vector similar to doc-001
        results = store.search([1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        # doc-001 should be first (exact match)
        assert results[0][0].doc_id == "doc-001"
        assert results[0][1] == pytest.approx(1.0, abs=0.01)

    def test_search_with_filters(self, store, sample_docs):
        store.add_documents(sample_docs)
        # Filter by paper_id
        results = store.search(
            [1.0, 0.0, 0.0], top_k=10, filters={"paper_id": "paper-001"}
        )
        assert len(results) == 2
        for doc, _ in results:
            assert doc.paper_id == "paper-001"

    def test_search_with_range_filter(self, store, sample_docs):
        store.add_documents(sample_docs)
        # Filter by page_start range
        results = store.search(
            [1.0, 1.0, 1.0], top_k=10, filters={"page_start": {"gte": 1, "lte": 1}}
        )
        assert len(results) == 2  # doc-001 and doc-003 have page_start=1

    def test_health_check(self, store):
        assert store.health_check() is True

    def test_get_collection_stats(self, store, sample_docs):
        store.add_documents(sample_docs)
        stats = store.get_collection_stats()
        assert stats["document_count"] == 3
        assert stats["vector_count"] == 3
        assert stats["vector_dimension"] == 3
        assert stats["backend"] == "memory"

    def test_save_and_load(self, store, sample_docs, tmp_path):
        store.add_documents(sample_docs)
        filepath = tmp_path / "test_index.json"
        store.save_to_file(str(filepath))

        # Load into new store
        new_store = MemoryVectorStore(config={})
        new_store.load_from_file(str(filepath))

        assert new_store.get_collection_stats()["document_count"] == 3
        doc = new_store.get_document("doc-001")
        assert doc is not None
        assert doc.text == "First document"
