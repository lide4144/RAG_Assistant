"""Tests for vector store base interface."""

import pytest
from app.vector_store.base import BaseVectorStore, Document


class TestDocument:
    """Test Document dataclass."""

    def test_document_creation(self):
        doc = Document(
            doc_id="test-001",
            paper_id="paper-001",
            content_type="body",
            page_start=1,
            text="Sample text",
            clean_text="Sample clean text",
        )
        assert doc.doc_id == "test-001"
        assert doc.paper_id == "paper-001"
        assert doc.content_type == "body"
        assert doc.page_start == 1
        assert doc.text == "Sample text"
        assert doc.clean_text == "Sample clean text"

    def test_document_to_dict(self):
        doc = Document(
            doc_id="test-001",
            paper_id="paper-001",
            content_type="body",
            page_start=1,
            text="Sample text",
            clean_text="Sample clean text",
            embedding=[0.1, 0.2, 0.3],
        )
        data = doc.to_dict()
        assert data["doc_id"] == "test-001"
        assert data["embedding"] == [0.1, 0.2, 0.3]

    def test_document_from_dict(self):
        data = {
            "doc_id": "test-001",
            "paper_id": "paper-001",
            "content_type": "body",
            "page_start": 1,
            "section": "Introduction",
            "text": "Sample text",
            "clean_text": "Sample clean text",
            "embedding": [0.1, 0.2, 0.3],
            "metadata": {"key": "value"},
        }
        doc = Document.from_dict(data)
        assert doc.doc_id == "test-001"
        assert doc.section == "Introduction"
        assert doc.embedding == [0.1, 0.2, 0.3]
        assert doc.metadata == {"key": "value"}


class TestBaseVectorStore:
    """Test BaseVectorStore abstract class."""

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseVectorStore()

    def test_chunk_list(self):
        # Create a concrete implementation for testing
        class MockStore(BaseVectorStore):
            def add_documents(self, documents):
                return []

            def delete_documents(self, doc_ids):
                return 0

            def update_document(self, doc_id, document):
                return True

            def get_document(self, doc_id):
                return None

            def search(self, query_vector, top_k=10, filters=None):
                return []

            def get_collection_stats(self):
                return {}

            def health_check(self):
                return True

        store = MockStore()
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        chunks = store._chunk_list(items, chunk_size=3)
        assert len(chunks) == 4
        assert chunks[0] == [1, 2, 3]
        assert chunks[1] == [4, 5, 6]
        assert chunks[2] == [7, 8, 9]
        assert chunks[3] == [10]
