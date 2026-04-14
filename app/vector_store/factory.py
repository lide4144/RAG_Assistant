"""Vector store factory for creating backend instances."""

from typing import Any, Dict

from app.vector_store.base import BaseVectorStore
from app.vector_store.memory_store import MemoryVectorStore


class VectorStoreFactory:
    """Factory for creating vector store instances.

    This factory creates the appropriate vector store backend
    based on configuration settings.
    """

    _backends = {
        "memory": MemoryVectorStore,
    }

    @classmethod
    def create(cls, config: Dict[str, Any]) -> BaseVectorStore:
        """Create vector store instance from configuration.

        Args:
            config: Configuration dictionary with 'backend' key
                   and backend-specific settings

        Returns:
            Vector store instance

        Raises:
            ValueError: If backend type is unknown
        """
        backend = config.get("backend", "memory")

        if backend == "qdrant":
            # Lazy import to avoid qdrant-client dependency when not needed
            from app.vector_store.qdrant_store import QdrantVectorStore

            return QdrantVectorStore(config)

        if backend not in cls._backends:
            raise ValueError(
                f"Unknown vector store backend: {backend}. "
                f"Available: {list(cls._backends.keys()) + ['qdrant']}"
            )

        return cls._backends[backend](config)

    @classmethod
    def register_backend(cls, name: str, backend_class: type) -> None:
        """Register a new backend type.

        Args:
            name: Backend name
            backend_class: Backend class (must inherit BaseVectorStore)
        """
        if not issubclass(backend_class, BaseVectorStore):
            raise ValueError("Backend class must inherit from BaseVectorStore")
        cls._backends[name] = backend_class

    @classmethod
    def list_backends(cls) -> list:
        """List available backend types.

        Returns:
            List of backend names
        """
        return list(cls._backends.keys()) + ["qdrant"]
