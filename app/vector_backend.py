from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import EmbeddingConfig
from app.index_vec import EmbeddingBuildStats, VecIndex, build_embedding_vec_index, load_vec_index, search_vec_with_query_embedding
from app.paper_store import paper_store_path, set_vector_backend_state
from app.paths import DATA_DIR


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
    ) -> tuple[VecIndex, EmbeddingBuildStats]:
        ...

    def search(self, *, index_path: str | Path, query_vector: list[float], top_k: int, normalize_query: bool) -> list[tuple[Any, float]]:
        ...

    def delete_papers(self, *, paper_ids: list[str], index_path: str | Path) -> VectorDeleteResult:
        ...

    def describe_backend(self, *, index_path: str | Path) -> VectorBackendDescriptor:
        ...


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

    def search(self, *, index_path: str | Path, query_vector: list[float], top_k: int, normalize_query: bool) -> list[tuple[Any, float]]:
        index = load_vec_index(index_path)
        return search_vec_with_query_embedding(index, query_vector, top_k=top_k, normalize_query=normalize_query)

    def delete_papers(self, *, paper_ids: list[str], index_path: str | Path) -> VectorDeleteResult:
        normalized = sorted({str(paper_id).strip() for paper_id in paper_ids if str(paper_id).strip()})
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


def resolve_vector_backend(name: str | None = None, *, db_path: str | Path | None = None) -> VectorBackend:
    backend_name = str(name or "file").strip().lower() or "file"
    if backend_name == "file":
        return FileVectorBackend(db_path=db_path)
    raise ValueError(f"unsupported vector backend: {backend_name}")


DEFAULT_FILE_VECTOR_BACKEND = FileVectorBackend(db_path=DATA_DIR / "processed" / "paper_store.sqlite3")
