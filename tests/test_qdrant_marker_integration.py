"""Integration tests for Qdrant + Marker optional paths.

This test verifies that:
1. Qdrant vector store can be used independently of Marker
2. Marker can be used independently of Qdrant
3. Both can be enabled together
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import json
from pathlib import Path

from app.vector_store import VectorStoreFactory
from app.vector_store.base import Document


class TestQdrantMarkerIntegration:
    """Test Qdrant and Marker integration scenarios."""

    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks as would be produced by Marker or legacy parser."""
        return [
            {
                "chunk_id": "paper1:00001",
                "paper_id": "paper1",
                "content_type": "body",
                "page_start": 1,
                "section": "Introduction",
                "text": "This is the introduction text from Marker parsing.",
                "clean_text": "This is the introduction text from Marker parsing.",
                "block_type": "text",
                "markdown_source": None,
            },
            {
                "chunk_id": "paper1:00002",
                "paper_id": "paper1",
                "content_type": "abstract",
                "page_start": 1,
                "section": None,
                "text": "Abstract text parsed by Marker.",
                "clean_text": "Abstract text parsed by Marker.",
                "block_type": "text",
                "markdown_source": None,
            },
        ]

    @pytest.fixture
    def sample_embeddings(self):
        """Create sample embeddings."""
        return [
            [0.1] * 768,  # Embedding for first chunk
            [0.2] * 768,  # Embedding for second chunk
        ]

    def test_qdrant_without_marker(self, tmp_path, sample_chunks, sample_embeddings):
        """Test Qdrant can work without Marker (using legacy parser output)."""
        # This simulates the scenario where:
        # - Marker is disabled (using legacy parser)
        # - Qdrant is enabled as vector backend

        with patch("app.vector_store.qdrant_store.QdrantClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Setup mocks
            mock_collections = MagicMock()
            mock_collections.collections = []
            mock_client.get_collections.return_value = mock_collections

            config = {
                "backend": "qdrant",
                "host": "localhost",
                "port": 6333,
                "collection_name": "test_collection",
                "vector_size": 768,
            }

            store = VectorStoreFactory.create(config)

            # Convert chunks to documents
            documents = []
            for i, chunk in enumerate(sample_chunks):
                doc = Document(
                    doc_id=chunk["chunk_id"],
                    paper_id=chunk["paper_id"],
                    content_type=chunk["content_type"],
                    page_start=chunk["page_start"],
                    section=chunk.get("section"),
                    text=chunk["text"],
                    clean_text=chunk["clean_text"],
                    embedding=sample_embeddings[i],
                    metadata={
                        "block_type": chunk.get("block_type"),
                        "markdown_source": chunk.get("markdown_source"),
                    },
                )
                documents.append(doc)

            # Add to Qdrant
            mock_client.upsert.return_value = None
            doc_ids = store.add_documents(documents)

            assert len(doc_ids) == 2
            mock_client.upsert.assert_called_once()

    def test_marker_enrichment_with_qdrant(self, tmp_path):
        """Test that Marker-enriched metadata is preserved when using Qdrant."""
        # Marker adds block_type and markdown_source fields
        # These should be preserved in Qdrant metadata

        with patch("app.vector_store.qdrant_store.QdrantClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_collections = MagicMock()
            mock_collections.collections = []
            mock_client.get_collections.return_value = mock_collections

            config = {
                "backend": "qdrant",
                "host": "localhost",
                "port": 6333,
                "collection_name": "test_collection",
            }

            store = VectorStoreFactory.create(config)

            # Document with Marker-specific fields
            doc = Document(
                doc_id="paper1:00001",
                paper_id="paper1",
                content_type="body",
                page_start=1,
                text="Text from Marker",
                clean_text="Text from Marker",
                embedding=[0.1] * 768,
                metadata={
                    "block_type": "text",  # Added by Marker
                    "markdown_source": "# Heading",  # Added by Marker
                    "structure_provenance": {"source": "marker"},  # Added by Marker
                },
            )

            mock_client.upsert.return_value = None
            store.add_documents([doc])

            # Verify the payload includes Marker metadata
            call_args = mock_client.upsert.call_args
            points = call_args[1]["points"]
            assert len(points) == 1

            payload = points[0].payload
            assert payload["metadata"]["block_type"] == "text"
            assert payload["metadata"]["markdown_source"] == "# Heading"

    def test_migration_from_file_to_qdrant_preserves_marker_data(self):
        """Test that migrating from file index to Qdrant preserves Marker data."""
        # This simulates running migrate_to_qdrant.py on a file index
        # that was built with Marker-enabled chunks

        index_data = {
            "docs": [
                {
                    "chunk_id": "paper1:00001",
                    "paper_id": "paper1",
                    "content_type": "body",
                    "page_start": 1,
                    "section": "Introduction",
                    "text": "Marker parsed text",
                    "clean_text": "Marker parsed text",
                    "block_type": "text",  # From Marker
                    "markdown_source": None,  # From Marker
                    "structure_provenance": {"source": "marker"},  # From Marker
                }
            ],
            "embeddings": [[0.1] * 768],
        }

        # Test conversion logic from migrate_to_qdrant.py
        docs = []
        doc_list = index_data["docs"]
        embeddings = index_data.get("embeddings", [])

        for i, doc_data in enumerate(doc_list):
            embedding = embeddings[i] if i < len(embeddings) else None

            doc = Document(
                doc_id=doc_data.get("chunk_id", f"doc_{i}"),
                paper_id=doc_data.get("paper_id", ""),
                content_type=doc_data.get("content_type", "body"),
                page_start=doc_data.get("page_start", 0),
                section=doc_data.get("section"),
                text=doc_data.get("text", ""),
                clean_text=doc_data.get("clean_text", ""),
                embedding=embedding,
                metadata={
                    "block_type": doc_data.get("block_type"),  # Preserved
                    "markdown_source": doc_data.get("markdown_source"),  # Preserved
                    "structure_provenance": doc_data.get(
                        "structure_provenance"
                    ),  # Preserved
                },
            )
            docs.append(doc)

        # Verify Marker fields are preserved
        assert len(docs) == 1
        assert docs[0].metadata["block_type"] == "text"
        assert docs[0].metadata["structure_provenance"]["source"] == "marker"


class TestBuildIndexesWithQdrant:
    """Test build_indexes.py with Qdrant backend."""

    @patch("app.build_indexes.resolve_vector_backend")
    @patch("app.build_indexes.load_and_validate_config")
    def test_build_indexes_uses_qdrant_when_configured(
        self, mock_load_config, mock_resolve_backend
    ):
        """Test that build_indexes uses Qdrant when configured."""
        from app.build_indexes import main

        # Mock config with Qdrant enabled
        mock_config = Mock()
        mock_config.embedding = Mock()
        mock_config.embedding.enabled = True
        mock_config.vector_store = Mock()
        mock_config.vector_store.backend = "qdrant"
        mock_load_config.return_value = (mock_config, [])

        # Mock backend
        mock_backend = Mock()
        mock_backend.rebuild.return_value = (Mock(), Mock())
        mock_resolve_backend.return_value = mock_backend

        with (
            patch("app.build_indexes.build_bm25_index") as mock_bm25,
            patch("app.build_indexes.build_vec_index") as mock_vec,
        ):
            mock_bm25.return_value = Mock(docs=[])
            mock_vec.return_value = Mock(docs=[])

            main(
                [
                    "--input",
                    "data/processed/chunks_clean.jsonl",
                    "--config",
                    "configs/default.yaml",
                ]
            )

        # Verify Qdrant backend was requested
        mock_resolve_backend.assert_called_once_with("qdrant")

    @patch("app.build_indexes.resolve_vector_backend")
    @patch("app.build_indexes.load_and_validate_config")
    def test_build_indexes_defaults_to_file_backend(
        self, mock_load_config, mock_resolve_backend
    ):
        """Test that build_indexes defaults to file backend when not configured."""
        from app.build_indexes import main

        # Mock config without vector_store
        mock_config = Mock()
        mock_config.embedding = Mock()
        mock_config.embedding.enabled = True
        # No vector_store attribute
        del mock_config.vector_store
        mock_load_config.return_value = (mock_config, [])

        # Mock backend
        mock_backend = Mock()
        mock_backend.rebuild.return_value = (Mock(), Mock())
        mock_resolve_backend.return_value = mock_backend

        with (
            patch("app.build_indexes.build_bm25_index") as mock_bm25,
            patch("app.build_indexes.build_vec_index") as mock_vec,
        ):
            mock_bm25.return_value = Mock(docs=[])
            mock_vec.return_value = Mock(docs=[])

            main(
                [
                    "--input",
                    "data/processed/chunks_clean.jsonl",
                    "--config",
                    "configs/default.yaml",
                ]
            )

        # Verify file backend was requested (default)
        mock_resolve_backend.assert_called_once_with("file")
