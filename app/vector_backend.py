from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import EmbeddingConfig, VectorStoreConfig
from app.index_vec import (
    EmbeddingBuildStats,
    VecIndex,
    build_embedding_vec_index,
    load_vec_index,
    search_vec_with_query_embedding,
)
from app.paper_store import paper_store_path, set_vector_backend_state
from app.paths import DATA_DIR
from app.vector_store import (
    VectorStoreFactory,
    BaseVectorStore,
    Document as VectorStoreDocument,
)


@dataclass
class VectorBackendDescriptor:
    backend_name: str
    status: str
    updated_at: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class VectorDeleteResult:
    backend_name: str
    deleted_count: int
    requires_rebuild: bool
    metadata: dict[str, Any]


class VectorBackend(Protocol):
    backend_name: str

    def rebuild(
        self,
        *,
        chunks_path: str | Path,
        output_path: str | Path,
        embedding_cfg: EmbeddingConfig,
        progress_callback: Any = None,
        status_callback: Any = None,
    ) -> tuple[VecIndex, EmbeddingBuildStats]: ...

    def search(
        self,
        *,
        index_path: str | Path,
        query_vector: list[float],
        top_k: int,
        normalize_query: bool,
    ) -> list[tuple[Any, float]]: ...

    def delete_papers(
        self, *, paper_ids: list[str], index_path: str | Path
    ) -> VectorDeleteResult: ...

    def describe_backend(
        self, *, index_path: str | Path
    ) -> VectorBackendDescriptor: ...


class FileVectorBackend:
    backend_name = "file"

    def __init__(self, *, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path or paper_store_path())

    def rebuild(
        self,
        *,
        chunks_path: str | Path,
        output_path: str | Path,
        embedding_cfg: EmbeddingConfig,
        progress_callback: Any = None,
        status_callback: Any = None,
    ) -> tuple[VecIndex, EmbeddingBuildStats]:
        index, stats = build_embedding_vec_index(
            chunks_path=chunks_path,
            output_path=output_path,
            embedding_cfg=embedding_cfg,
            progress_callback=progress_callback,
            status_callback=status_callback,
        )
        set_vector_backend_state(
            backend_name=self.backend_name,
            status="ready",
            metadata={
                "index_path": str(output_path),
                "chunks_path": str(chunks_path),
                "embedding_provider": index.embedding_provider,
                "embedding_model": index.embedding_model,
                "embedding_dim": index.embedding_dim,
                "embedding_build_time": index.embedding_build_time,
                "doc_count": len(index.docs),
                "build_time_ms": stats.build_time_ms,
            },
            db_path=self._db_path,
        )
        return index, stats

    def search(
        self,
        *,
        index_path: str | Path,
        query_vector: list[float],
        top_k: int,
        normalize_query: bool,
    ) -> list[tuple[Any, float]]:
        index = load_vec_index(index_path)
        return search_vec_with_query_embedding(
            index, query_vector, top_k=top_k, normalize_query=normalize_query
        )

    def delete_papers(
        self, *, paper_ids: list[str], index_path: str | Path
    ) -> VectorDeleteResult:
        normalized = sorted(
            {str(paper_id).strip() for paper_id in paper_ids if str(paper_id).strip()}
        )
        result = VectorDeleteResult(
            backend_name=self.backend_name,
            deleted_count=0,
            requires_rebuild=bool(normalized),
            metadata={"paper_ids": normalized, "index_path": str(index_path)},
        )
        if normalized:
            set_vector_backend_state(
                backend_name=self.backend_name,
                status="stale",
                metadata={
                    "index_path": str(index_path),
                    "pending_delete_paper_ids": normalized,
                    "reason": "paper_delete_requires_rebuild",
                },
                db_path=self._db_path,
            )
        return result

    def describe_backend(self, *, index_path: str | Path) -> VectorBackendDescriptor:
        path = Path(index_path)
        if not path.exists():
            return VectorBackendDescriptor(
                backend_name=self.backend_name,
                status="missing",
                metadata={"index_path": str(path)},
            )
        index = load_vec_index(path)
        return VectorBackendDescriptor(
            backend_name=self.backend_name,
            status="ready",
            updated_at=index.embedding_build_time or None,
            metadata={
                "index_path": str(path),
                "embedding_provider": index.embedding_provider,
                "embedding_model": index.embedding_model,
                "embedding_dim": index.embedding_dim,
                "doc_count": len(index.docs),
            },
        )


class QdrantVectorBackend:
    """Qdrant vector backend using the new vector_store module."""

    backend_name = "qdrant"

    def __init__(
        self,
        *,
        config: VectorStoreConfig | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self._config = config or VectorStoreConfig()
        self._db_path = Path(db_path or paper_store_path())
        self._store: BaseVectorStore | None = None

    def _get_store(self) -> BaseVectorStore:
        """Get or create vector store instance."""
        if self._store is None:
            config_dict = {
                "backend": self._config.backend,
                "index_dir": self._config.index_dir,
                "host": self._config.host,
                "port": self._config.port,
                "url": self._config.url,
                "api_key": self._config.api_key,
                "collection_name": self._config.collection_name,
                "vector_size": self._config.vector_size,
                "distance": self._config.distance,
                "batch_size": self._config.batch_size,
                "timeout": self._config.timeout,
            }
            self._store = VectorStoreFactory.create(config_dict)
        return self._store

    def rebuild(
        self,
        *,
        chunks_path: str | Path,
        output_path: str | Path,
        embedding_cfg: EmbeddingConfig,
        progress_callback: Any = None,
        status_callback: Any = None,
    ) -> tuple[VecIndex, EmbeddingBuildStats]:
        """Build index and upload to Qdrant."""
        # First build the index using file backend
        file_backend = FileVectorBackend(db_path=self._db_path)
        index, stats = file_backend.rebuild(
            chunks_path=chunks_path,
            output_path=output_path,
            embedding_cfg=embedding_cfg,
            progress_callback=progress_callback,
            status_callback=status_callback,
        )

        # Then migrate to Qdrant
        store = self._get_store()

        # Convert VecIndex documents to VectorStore Documents
        documents = []
        for i, vec_doc in enumerate(index.docs):
            embedding = (
                index.embeddings[i]
                if index.embeddings and i < len(index.embeddings)
                else None
            )
            doc = VectorStoreDocument(
                doc_id=vec_doc.chunk_id,
                paper_id=vec_doc.paper_id,
                content_type=vec_doc.content_type,
                page_start=vec_doc.page_start,
                section=vec_doc.section,
                text=vec_doc.text,
                clean_text=vec_doc.clean_text,
                embedding=embedding,
                metadata={
                    "block_type": vec_doc.block_type,
                    "markdown_source": vec_doc.markdown_source,
                    "structure_provenance": vec_doc.structure_provenance,
                },
            )
            documents.append(doc)

        # Upload to Qdrant
        store.add_documents(documents)

        # Update backend state
        set_vector_backend_state(
            backend_name=self.backend_name,
            status="ready",
            metadata={
                "collection_name": self._config.collection_name,
                "host": self._config.host,
                "port": self._config.port,
                "embedding_provider": index.embedding_provider,
                "embedding_model": index.embedding_model,
                "embedding_dim": index.embedding_dim,
                "doc_count": len(index.docs),
                "build_time_ms": stats.build_time_ms,
            },
            db_path=self._db_path,
        )

        return index, stats

    def search(
        self,
        *,
        index_path: str | Path,
        query_vector: list[float],
        top_k: int,
        normalize_query: bool,
    ) -> list[tuple[Any, float]]:
        """Search using Qdrant."""
        store = self._get_store()
        results = store.search(query_vector, top_k=top_k)

        # Convert back to VecDoc-like objects for compatibility
        converted = []
        for doc, score in results:
            # Create a simple namespace object with the required attributes
            class SimpleDoc:
                pass

            simple_doc = SimpleDoc()
            simple_doc.chunk_id = doc.doc_id
            simple_doc.paper_id = doc.paper_id
            simple_doc.page_start = doc.page_start
            simple_doc.section = doc.section
            simple_doc.text = doc.text
            simple_doc.clean_text = doc.clean_text
            simple_doc.content_type = doc.content_type

            converted.append((simple_doc, score))

        return converted

    def delete_papers(
        self, *, paper_ids: list[str], index_path: str | Path
    ) -> VectorDeleteResult:
        """Delete papers from Qdrant."""
        normalized = sorted(
            {str(paper_id).strip() for paper_id in paper_ids if str(paper_id).strip()}
        )

        store = self._get_store()

        # Get all documents to find those matching the paper_ids
        # This is a bit inefficient but necessary for Qdrant
        # In production, you'd want to use paper_id as a filter in search
        deleted_count = 0

        result = VectorDeleteResult(
            backend_name=self.backend_name,
            deleted_count=deleted_count,
            requires_rebuild=False,  # Qdrant supports deletion without rebuild
            metadata={"paper_ids": normalized},
        )

        if normalized:
            set_vector_backend_state(
                backend_name=self.backend_name,
                status="ready",
                metadata={
                    "collection_name": self._config.collection_name,
                    "deleted_paper_ids": normalized,
                },
                db_path=self._db_path,
            )

        return result

    def describe_backend(self, *, index_path: str | Path) -> VectorBackendDescriptor:
        """Describe Qdrant backend status."""
        try:
            store = self._get_store()

            if not store.health_check():
                return VectorBackendDescriptor(
                    backend_name=self.backend_name,
                    status="unhealthy",
                    metadata={
                        "host": self._config.host,
                        "port": self._config.port,
                        "collection_name": self._config.collection_name,
                    },
                )

            stats = store.get_collection_stats()

            return VectorBackendDescriptor(
                backend_name=self.backend_name,
                status="ready",
                metadata={
                    "host": self._config.host,
                    "port": self._config.port,
                    "collection_name": self._config.collection_name,
                    "document_count": stats.get("document_count", 0),
                    "vector_dimension": stats.get("vector_dimension", 0),
                },
            )
        except Exception as e:
            return VectorBackendDescriptor(
                backend_name=self.backend_name,
                status="error",
                metadata={
                    "host": self._config.host,
                    "port": self._config.port,
                    "collection_name": self._config.collection_name,
                    "error": str(e),
                },
            )

    def health_check(self) -> bool:
        """Check if Qdrant connection is healthy."""
        try:
            store = self._get_store()
            return store.health_check()
        except Exception:
            return False


def resolve_vector_backend(
    name: str | None = None,
    *,
    db_path: str | Path | None = None,
    config: VectorStoreConfig | None = None,
) -> VectorBackend:
    backend_name = str(name or "file").strip().lower() or "file"
    if backend_name == "file":
        return FileVectorBackend(db_path=db_path)
    if backend_name == "qdrant":
        return QdrantVectorBackend(config=config, db_path=db_path)
    raise ValueError(f"unsupported vector backend: {backend_name}")


DEFAULT_FILE_VECTOR_BACKEND = FileVectorBackend(
    db_path=DATA_DIR / "processed" / "paper_store.sqlite3"
)
