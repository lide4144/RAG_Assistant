"""Tests for vector store factory."""

import pytest
from app.vector_store.factory import VectorStoreFactory
from app.vector_store.memory_store import MemoryVectorStore
from app.vector_store.base import BaseVectorStore


class TestVectorStoreFactory:
    """Test VectorStoreFactory."""

    def test_create_memory_backend(self):
        config = {"backend": "memory", "index_dir": "data/indexes"}
        store = VectorStoreFactory.create(config)
        assert isinstance(store, MemoryVectorStore)

    def test_create_default_backend(self):
        config = {"index_dir": "data/indexes"}
        store = VectorStoreFactory.create(config)
        assert isinstance(store, MemoryVectorStore)

    def test_create_unknown_backend(self):
        config = {"backend": "unknown"}
        with pytest.raises(ValueError, match="Unknown vector store backend"):
            VectorStoreFactory.create(config)

    def test_list_backends(self):
        backends = VectorStoreFactory.list_backends()
        assert "memory" in backends
        assert "qdrant" in backends

    def test_register_backend(self):
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

        VectorStoreFactory.register_backend("mock", MockStore)

        config = {"backend": "mock"}
        store = VectorStoreFactory.create(config)
        assert isinstance(store, MockStore)

    def test_register_invalid_backend(self):
        with pytest.raises(ValueError, match="must inherit from BaseVectorStore"):
            VectorStoreFactory.register_backend("invalid", str)
