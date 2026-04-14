"""Vector store module for RAG GPT.

This module provides a unified interface for vector storage backends,
supporting both in-memory and Qdrant implementations.
"""

from app.vector_store.base import BaseVectorStore, Document
from app.vector_store.exceptions import (
    VectorStoreConnectionError,
    VectorStoreTimeoutError,
)
from app.vector_store.factory import VectorStoreFactory
from app.vector_store.memory_store import MemoryVectorStore

__all__ = [
    "BaseVectorStore",
    "Document",
    "VectorStoreConnectionError",
    "VectorStoreTimeoutError",
    "VectorStoreFactory",
    "MemoryVectorStore",
]


# QdrantVectorStore is imported lazily to avoid qdrant-client dependency
# when not using Qdrant backend
def get_qdrant_store():
    """Lazy import for QdrantVectorStore."""
    from app.vector_store.qdrant_store import QdrantVectorStore

    return QdrantVectorStore
