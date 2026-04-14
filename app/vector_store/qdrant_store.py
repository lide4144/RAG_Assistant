"""Qdrant vector store implementation."""

import json
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from app.vector_store.base import BaseVectorStore, Document
from app.vector_store.exceptions import (
    VectorStoreConnectionError,
    VectorStoreTimeoutError,
)


class QdrantVectorStore(BaseVectorStore):
    """Qdrant vector storage backend.

    This implementation uses Qdrant vector database for scalable
    vector storage and retrieval.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize Qdrant vector store.

        Args:
            config: Configuration with:
                - host: Qdrant host (default: localhost)
                - port: Qdrant port (default: 6333)
                - url: Qdrant URL (for cloud, overrides host/port)
                - api_key: API key for Qdrant Cloud
                - collection_name: Collection name (default: paper_chunks)
                - vector_size: Vector dimension (default: 1024)
                - distance: Distance metric (default: COSINE)
        """
        super().__init__(config)
        self.host = self.config.get("host", "localhost")
        self.port = self.config.get("port", 6333)
        self.url = self.config.get("url")
        self.api_key = self.config.get("api_key")
        self.collection_name = self.config.get("collection_name", "paper_chunks")
        self.vector_size = self.config.get("vector_size", 1024)
        self.distance = self.config.get("distance", "COSINE")
        self.batch_size = self.config.get("batch_size", 100)
        self.timeout = self.config.get("timeout", 60)

        self._client = None
        self._create_client()
        self._ensure_collection()

    def _create_client(self) -> None:
        """Create Qdrant client connection."""
        try:
            from qdrant_client import QdrantClient

            if self.url:
                # Cloud/remote connection
                self._client = QdrantClient(
                    url=self.url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
            else:
                # Local connection
                self._client = QdrantClient(
                    host=self.host,
                    port=self.port,
                    timeout=self.timeout,
                )
        except Exception as e:
            raise VectorStoreConnectionError(
                f"Failed to connect to Qdrant: {str(e)}", backend="qdrant"
            )

    def _ensure_collection(self) -> None:
        """Ensure collection exists, create if not."""
        from qdrant_client.models import Distance, VectorParams

        try:
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name not in collection_names:
                # Create new collection
                distance_map = {
                    "COSINE": Distance.COSINE,
                    "EUCLID": Distance.EUCLID,
                    "DOT": Distance.DOT,
                }
                distance = distance_map.get(self.distance, Distance.COSINE)

                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=distance,
                    ),
                )
        except Exception as e:
            raise VectorStoreConnectionError(
                f"Failed to ensure collection: {str(e)}", backend="qdrant"
            )

    def add_documents(self, documents: List[Document]) -> List[str]:
        """Add documents to Qdrant store.

        Args:
            documents: List of documents to add

        Returns:
            List of document IDs
        """
        from qdrant_client.models import PointStruct

        doc_ids = []
        chunks = self._chunk_list(documents, self.batch_size)

        for chunk in chunks:
            points = []
            for doc in chunk:
                if not doc.embedding:
                    continue

                payload = {
                    "paper_id": doc.paper_id,
                    "content_type": doc.content_type,
                    "page_start": doc.page_start,
                    "section": doc.section,
                    "text": doc.text,
                    "clean_text": doc.clean_text,
                    "metadata": doc.metadata,
                }

                point = PointStruct(
                    id=doc.doc_id,
                    vector=doc.embedding,
                    payload=payload,
                )
                points.append(point)
                doc_ids.append(doc.doc_id)

            if points:
                try:
                    self._client.upsert(
                        collection_name=self.collection_name,
                        points=points,
                    )
                except Exception as e:
                    raise VectorStoreTimeoutError(
                        f"Failed to add documents: {str(e)}", operation="add_documents"
                    )

        return doc_ids

    def delete_documents(self, doc_ids: List[str]) -> int:
        """Delete documents from Qdrant store.

        Args:
            doc_ids: List of document IDs to delete

        Returns:
            Number of documents deleted
        """
        chunks = self._chunk_list(doc_ids, self.batch_size)
        total_deleted = 0

        for chunk in chunks:
            try:
                self._client.delete(
                    collection_name=self.collection_name,
                    points_selector=chunk,
                )
                total_deleted += len(chunk)
            except Exception as e:
                raise VectorStoreTimeoutError(
                    f"Failed to delete documents: {str(e)}",
                    operation="delete_documents",
                )

        return total_deleted

    def update_document(self, doc_id: str, document: Document) -> bool:
        """Update a document in Qdrant store.

        Args:
            doc_id: Document ID to update
            document: New document data

        Returns:
            True if updated successfully
        """
        # In Qdrant, update is same as upsert
        if not document.embedding:
            return False

        try:
            self.add_documents([document])
            return True
        except Exception:
            return False

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        try:
            result = self._client.retrieve(
                collection_name=self.collection_name,
                ids=[doc_id],
            )

            if not result:
                return None

            point = result[0]
            payload = point.payload or {}

            return Document(
                doc_id=point.id,
                paper_id=payload.get("paper_id", ""),
                content_type=payload.get("content_type", ""),
                page_start=payload.get("page_start", 0),
                section=payload.get("section"),
                text=payload.get("text", ""),
                clean_text=payload.get("clean_text", ""),
                embedding=point.vector if hasattr(point, "vector") else None,
                metadata=payload.get("metadata", {}),
            )
        except Exception:
            return None

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """Search for similar documents in Qdrant.

        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filters: Metadata filters (optional)

        Returns:
            List of (document, score) tuples
        """
        from qdrant_client.models import Filter

        qdrant_filter = None
        if filters:
            qdrant_filter = self._convert_filters(filters)

        try:
            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
                with_vectors=False,
            )

            documents = []
            for scored_point in results:
                payload = scored_point.payload or {}
                doc = Document(
                    doc_id=scored_point.id,
                    paper_id=payload.get("paper_id", ""),
                    content_type=payload.get("content_type", ""),
                    page_start=payload.get("page_start", 0),
                    section=payload.get("section"),
                    text=payload.get("text", ""),
                    clean_text=payload.get("clean_text", ""),
                    embedding=None,
                    metadata=payload.get("metadata", {}),
                )
                documents.append((doc, scored_point.score))

            return documents
        except Exception as e:
            raise VectorStoreTimeoutError(
                f"Search failed: {str(e)}", operation="search"
            )

    def _convert_filters(self, filters: Dict[str, Any]) -> Any:
        """Convert filter DSL to Qdrant Filter.

        Supports:
        - Exact match: {"field": "value"}
        - Range query: {"field": {"gte": 5, "lte": 10}}
        - Multi-value: {"field": ["value1", "value2"]}

        Args:
            filters: Filter DSL dictionary

        Returns:
            Qdrant Filter object
        """
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchValue,
            MatchAny,
            Range,
        )

        conditions = []

        for key, value in filters.items():
            if isinstance(value, dict):
                # Range query
                range_params = {}
                if "gte" in value:
                    range_params["gte"] = value["gte"]
                if "gt" in value:
                    range_params["gt"] = value["gt"]
                if "lte" in value:
                    range_params["lte"] = value["lte"]
                if "lt" in value:
                    range_params["lt"] = value["lt"]

                if range_params:
                    conditions.append(
                        FieldCondition(
                            key=key,
                            range=Range(**range_params),
                        )
                    )
                elif "eq" in value:
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value["eq"]),
                        )
                    )
            elif isinstance(value, list):
                # Multi-value match
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchAny(any=value),
                    )
                )
            else:
                # Exact match
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )

        return Filter(must=conditions) if conditions else None

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics from Qdrant.

        Returns:
            Dictionary with statistics
        """
        try:
            collection_info = self._client.get_collection(
                collection_name=self.collection_name
            )

            return {
                "document_count": collection_info.points_count,
                "vector_count": collection_info.points_count,
                "vector_dimension": self.vector_size,
                "backend": "qdrant",
                "collection_name": self.collection_name,
            }
        except Exception as e:
            return {
                "document_count": 0,
                "vector_count": 0,
                "vector_dimension": self.vector_size,
                "backend": "qdrant",
                "error": str(e),
            }

    def health_check(self) -> bool:
        """Check if Qdrant connection is healthy.

        Returns:
            True if healthy
        """
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def export_to_file(self, filepath: str) -> None:
        """Export all documents to JSON file.

        Args:
            filepath: Path to export file
        """
        from qdrant_client.models import ScrollRequest

        all_docs = []
        offset = None

        while True:
            try:
                results, offset = self._client.scroll(
                    collection_name=self.collection_name,
                    offset=offset,
                    limit=1000,
                    with_vectors=True,
                )

                for point in results:
                    payload = point.payload or {}
                    doc_data = {
                        "doc_id": point.id,
                        "paper_id": payload.get("paper_id", ""),
                        "content_type": payload.get("content_type", ""),
                        "page_start": payload.get("page_start", 0),
                        "section": payload.get("section"),
                        "text": payload.get("text", ""),
                        "clean_text": payload.get("clean_text", ""),
                        "embedding": point.vector if hasattr(point, "vector") else None,
                        "metadata": payload.get("metadata", {}),
                    }
                    all_docs.append(doc_data)

                if offset is None:
                    break
            except Exception as e:
                raise VectorStoreTimeoutError(
                    f"Export failed: {str(e)}", operation="export"
                )

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"docs": all_docs}, f, ensure_ascii=False, indent=2)

    def import_from_file(self, filepath: str) -> int:
        """Import documents from JSON file.

        Args:
            filepath: Path to import file

        Returns:
            Number of documents imported
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        docs_data = data.get("docs", [])
        documents = []

        for doc_data in docs_data:
            doc = Document(
                doc_id=doc_data["doc_id"],
                paper_id=doc_data["paper_id"],
                content_type=doc_data["content_type"],
                page_start=doc_data["page_start"],
                section=doc_data.get("section"),
                text=doc_data["text"],
                clean_text=doc_data["clean_text"],
                embedding=doc_data.get("embedding"),
                metadata=doc_data.get("metadata", {}),
            )
            documents.append(doc)

        self.add_documents(documents)
        return len(documents)

    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection.

        Returns:
            Dictionary with collection info including:
            - vector_size: Vector dimension
            - distance: Distance metric
            - document_count: Number of documents
        """
        try:
            collection = self._client.get_collection(self.collection_name)
            return {
                "vector_size": collection.config.params.vectors.size,
                "distance": str(collection.config.params.vectors.distance),
                "document_count": collection.points_count,
            }
        except Exception as e:
            return {
                "vector_size": self.vector_size,
                "distance": self.distance,
                "document_count": 0,
                "error": str(e),
            }

    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection.

        Returns:
            Dictionary with collection info including:
            - vector_size: Vector dimension
            - distance: Distance metric
            - document_count: Number of documents
        """
        try:
            collection = self._client.get_collection(self.collection_name)
            return {
                "vector_size": collection.config.params.vectors.size,
                "distance": str(collection.config.params.vectors.distance),
                "document_count": collection.points_count,
            }
        except Exception as e:
            return {
                "vector_size": self.vector_size,
                "distance": self.distance,
                "document_count": 0,
                "error": str(e),
            }
