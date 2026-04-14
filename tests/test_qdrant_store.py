"""Tests for Qdrant vector store implementation.

These tests use mocks to avoid requiring a running Qdrant instance.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from app.vector_store.qdrant_store import QdrantVectorStore
from app.vector_store.base import Document
from app.vector_store.exceptions import (
    VectorStoreConnectionError,
    VectorStoreTimeoutError,
)


class TestQdrantVectorStore:
    """Test QdrantVectorStore with mocked Qdrant client."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create a mocked Qdrant client."""
        with patch("app.vector_store.qdrant_store.QdrantClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock get_collections to return empty list
            mock_collections = MagicMock()
            mock_collections.collections = []
            mock_client.get_collections.return_value = mock_collections

            yield mock_client

    @pytest.fixture
    def store(self, mock_qdrant_client):
        """Create Qdrant store with mocked client."""
        config = {
            "host": "localhost",
            "port": 6333,
            "collection_name": "test_collection",
            "vector_size": 768,
        }
        return QdrantVectorStore(config)

    @pytest.fixture
    def sample_docs(self):
        """Create sample documents for testing."""
        return [
            Document(
                doc_id="doc-001",
                paper_id="paper-001",
                content_type="body",
                page_start=1,
                text="First document",
                clean_text="First document",
                embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ),
            Document(
                doc_id="doc-002",
                paper_id="paper-001",
                content_type="abstract",
                page_start=2,
                text="Second document",
                clean_text="Second document",
                embedding=[0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ),
        ]

    def test_init_with_host_port(self, mock_qdrant_client):
        """Test initialization with host and port."""
        config = {
            "host": "test-host",
            "port": 9999,
            "collection_name": "test_collection",
        }
        store = QdrantVectorStore(config)

        assert store.host == "test-host"
        assert store.port == 9999
        assert store.collection_name == "test_collection"

    def test_init_with_url(self, mock_qdrant_client):
        """Test initialization with URL for cloud connection."""
        config = {
            "url": "https://cloud.qdrant.io",
            "api_key": "test-api-key",
            "collection_name": "test_collection",
        }
        store = QdrantVectorStore(config)

        assert store.url == "https://cloud.qdrant.io"
        assert store.api_key == "test-api-key"

    def test_connection_error(self):
        """Test connection error handling."""
        with patch("app.vector_store.qdrant_store.QdrantClient") as mock_client:
            mock_client.side_effect = Exception("Connection refused")

            with pytest.raises(VectorStoreConnectionError) as exc_info:
                QdrantVectorStore({"host": "localhost", "port": 6333})

            assert "Failed to connect to Qdrant" in str(exc_info.value)
            assert exc_info.value.backend == "qdrant"

    def test_add_documents(self, store, sample_docs, mock_qdrant_client):
        """Test adding documents."""
        # Mock upsert response
        mock_qdrant_client.upsert.return_value = None

        doc_ids = store.add_documents(sample_docs)

        assert len(doc_ids) == 2
        assert "doc-001" in doc_ids
        assert "doc-002" in doc_ids

        # Verify upsert was called
        mock_qdrant_client.upsert.assert_called_once()
        call_args = mock_qdrant_client.upsert.call_args
        assert call_args[1]["collection_name"] == "test_collection"

    def test_add_documents_with_batching(self, store, mock_qdrant_client):
        """Test batching when adding many documents."""
        # Create more than batch_size documents
        docs = [
            Document(
                doc_id=f"doc-{i:03d}",
                paper_id="paper-001",
                content_type="body",
                page_start=i,
                text=f"Document {i}",
                clean_text=f"Document {i}",
                embedding=[float(i), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            )
            for i in range(150)  # More than default batch_size of 100
        ]

        mock_qdrant_client.upsert.return_value = None

        store.add_documents(docs)

        # Should be called twice (100 + 50)
        assert mock_qdrant_client.upsert.call_count == 2

    def test_add_documents_timeout(self, store, sample_docs, mock_qdrant_client):
        """Test timeout handling during add."""
        mock_qdrant_client.upsert.side_effect = Exception("Timeout")

        with pytest.raises(VectorStoreTimeoutError) as exc_info:
            store.add_documents(sample_docs)

        assert "add_documents" in str(exc_info.value.operation)

    def test_delete_documents(self, store, mock_qdrant_client):
        """Test deleting documents."""
        mock_qdrant_client.delete.return_value = None

        count = store.delete_documents(["doc-001", "doc-002"])

        assert count == 2
        mock_qdrant_client.delete.assert_called_once()

    def test_delete_documents_timeout(self, store, mock_qdrant_client):
        """Test timeout handling during delete."""
        mock_qdrant_client.delete.side_effect = Exception("Timeout")

        with pytest.raises(VectorStoreTimeoutError) as exc_info:
            store.delete_documents(["doc-001"])

        assert "delete_documents" in str(exc_info.value.operation)

    def test_get_document(self, store, mock_qdrant_client):
        """Test getting a document by ID."""
        # Mock retrieve response
        mock_point = MagicMock()
        mock_point.id = "doc-001"
        mock_point.payload = {
            "paper_id": "paper-001",
            "content_type": "body",
            "page_start": 1,
            "text": "Test document",
            "clean_text": "Test document",
        }
        mock_qdrant_client.retrieve.return_value = [mock_point]

        doc = store.get_document("doc-001")

        assert doc is not None
        assert doc.doc_id == "doc-001"
        assert doc.paper_id == "paper-001"

    def test_get_document_not_found(self, store, mock_qdrant_client):
        """Test getting a non-existent document."""
        mock_qdrant_client.retrieve.return_value = []

        doc = store.get_document("non-existent")

        assert doc is None

    def test_search(self, store, mock_qdrant_client):
        """Test vector search."""
        # Mock search response
        mock_scored_point = MagicMock()
        mock_scored_point.id = "doc-001"
        mock_scored_point.score = 0.95
        mock_scored_point.payload = {
            "paper_id": "paper-001",
            "content_type": "body",
            "page_start": 1,
            "text": "Test document",
            "clean_text": "Test document",
        }
        mock_qdrant_client.search.return_value = [mock_scored_point]

        results = store.search([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], top_k=10)

        assert len(results) == 1
        assert results[0][0].doc_id == "doc-001"
        assert results[0][1] == 0.95

    def test_search_with_filters(self, store, mock_qdrant_client):
        """Test search with metadata filters."""
        mock_scored_point = MagicMock()
        mock_scored_point.id = "doc-001"
        mock_scored_point.score = 0.95
        mock_scored_point.payload = {
            "paper_id": "paper-001",
            "content_type": "body",
            "page_start": 1,
            "text": "Test document",
            "clean_text": "Test document",
        }
        mock_qdrant_client.search.return_value = [mock_scored_point]

        results = store.search(
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            top_k=10,
            filters={"paper_id": "paper-001"},
        )

        assert len(results) == 1
        # Verify filter was passed to search
        mock_qdrant_client.search.assert_called_once()
        call_args = mock_qdrant_client.search.call_args
        assert "query_filter" in call_args[1]

    def test_get_collection_stats(self, store, mock_qdrant_client):
        """Test getting collection statistics."""
        # Mock collection info
        mock_info = MagicMock()
        mock_info.points_count = 100
        mock_qdrant_client.get_collection.return_value = mock_info

        stats = store.get_collection_stats()

        assert stats["document_count"] == 100
        assert stats["backend"] == "qdrant"
        assert stats["collection_name"] == "test_collection"

    def test_health_check_healthy(self, store, mock_qdrant_client):
        """Test health check when Qdrant is healthy."""
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_qdrant_client.get_collections.return_value = mock_collections

        is_healthy = store.health_check()

        assert is_healthy is True

    def test_health_check_unhealthy(self, store, mock_qdrant_client):
        """Test health check when Qdrant is down."""
        mock_qdrant_client.get_collections.side_effect = Exception("Connection failed")

        is_healthy = store.health_check()

        assert is_healthy is False


class TestQdrantFilterDSL:
    """Test filter DSL conversion."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create a mocked Qdrant client."""
        with patch("app.vector_store.qdrant_store.QdrantClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_collections = MagicMock()
            mock_collections.collections = []
            mock_client.get_collections.return_value = mock_collections

            yield mock_client

    @pytest.fixture
    def store(self, mock_qdrant_client):
        """Create Qdrant store with mocked client."""
        config = {
            "host": "localhost",
            "port": 6333,
            "collection_name": "test_collection",
        }
        return QdrantVectorStore(config)

    def test_exact_match_filter(self, store, mock_qdrant_client):
        """Test exact match filter conversion."""
        mock_qdrant_client.search.return_value = []

        store.search(
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], filters={"paper_id": "abc123"}
        )

        call_args = mock_qdrant_client.search.call_args
        query_filter = call_args[1]["query_filter"]

        # Verify filter structure
        assert query_filter is not None
        assert len(query_filter.must) == 1

    def test_range_filter(self, store, mock_qdrant_client):
        """Test range filter conversion."""
        mock_qdrant_client.search.return_value = []

        store.search(
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            filters={"page_start": {"gte": 5, "lte": 10}},
        )

        call_args = mock_qdrant_client.search.call_args
        query_filter = call_args[1]["query_filter"]

        assert query_filter is not None
        assert len(query_filter.must) == 1

    def test_multi_value_filter(self, store, mock_qdrant_client):
        """Test multi-value (OR) filter conversion."""
        mock_qdrant_client.search.return_value = []

        store.search(
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            filters={"content_type": ["body", "abstract"]},
        )

        call_args = mock_qdrant_client.search.call_args
        query_filter = call_args[1]["query_filter"]

        assert query_filter is not None
        assert len(query_filter.must) == 1

    def test_combined_filters(self, store, mock_qdrant_client):
        """Test combined filters."""
        mock_qdrant_client.search.return_value = []

        store.search(
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            filters={
                "paper_id": "abc123",
                "page_start": {"gte": 1, "lte": 10},
                "content_type": ["body", "abstract"],
            },
        )

        call_args = mock_qdrant_client.search.call_args
        query_filter = call_args[1]["query_filter"]

        assert query_filter is not None
        # Should have 3 conditions
        assert len(query_filter.must) == 3


class TestQdrantExportImport:
    """Test export and import functionality."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create a mocked Qdrant client."""
        with patch("app.vector_store.qdrant_store.QdrantClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_collections = MagicMock()
            mock_collections.collections = []
            mock_client.get_collections.return_value = mock_collections

            yield mock_client

    @pytest.fixture
    def store(self, mock_qdrant_client):
        """Create Qdrant store with mocked client."""
        config = {
            "host": "localhost",
            "port": 6333,
            "collection_name": "test_collection",
        }
        return QdrantVectorStore(config)

    def test_export_to_file(self, store, mock_qdrant_client, tmp_path):
        """Test exporting data to file."""
        # Mock scroll response
        mock_point = MagicMock()
        mock_point.id = "doc-001"
        mock_point.payload = {
            "paper_id": "paper-001",
            "content_type": "body",
            "page_start": 1,
            "text": "Test document",
            "clean_text": "Test document",
            "metadata": {},
        }
        mock_point.vector = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        # Return results then None to indicate end
        mock_qdrant_client.scroll.side_effect = [
            ([mock_point], None),  # First call returns results with no offset
        ]

        output_file = tmp_path / "export.json"
        store.export_to_file(str(output_file))

        assert output_file.exists()

        import json

        with open(output_file, "r") as f:
            data = json.load(f)

        assert "docs" in data
        assert len(data["docs"]) == 1
        assert data["docs"][0]["doc_id"] == "doc-001"

    def test_import_from_file(self, store, mock_qdrant_client, tmp_path):
        """Test importing data from file."""
        import json

        # Create test file
        test_file = tmp_path / "import.json"
        with open(test_file, "w") as f:
            json.dump(
                {
                    "docs": [
                        {
                            "doc_id": "doc-001",
                            "paper_id": "paper-001",
                            "content_type": "body",
                            "page_start": 1,
                            "text": "Test document",
                            "clean_text": "Test document",
                            "embedding": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                            "metadata": {},
                        }
                    ]
                },
                f,
            )

        mock_qdrant_client.upsert.return_value = None

        count = store.import_from_file(str(test_file))

        assert count == 1
        mock_qdrant_client.upsert.assert_called_once()
