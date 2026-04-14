"""In-memory vector store implementation."""

import json
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from app.vector_store.base import BaseVectorStore, Document


class MemoryVectorStore(BaseVectorStore):
    """In-memory vector storage using dict/list structures.

    This implementation stores documents and vectors in memory,
    suitable for small to medium datasets and development/testing.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize memory vector store.

        Args:
            config: Configuration with optional 'index_dir' for persistence
        """
        super().__init__(config)
        self._documents: Dict[str, Document] = {}
        self._vectors: Dict[str, List[float]] = {}
        self.index_dir = self.config.get("index_dir", "data/indexes")

    def add_documents(self, documents: List[Document]) -> List[str]:
        """Add documents to memory store.

        Args:
            documents: List of documents to add

        Returns:
            List of document IDs
        """
        doc_ids = []
        for doc in documents:
            self._documents[doc.doc_id] = doc
            if doc.embedding:
                self._vectors[doc.doc_id] = doc.embedding
            doc_ids.append(doc.doc_id)
        return doc_ids

    def delete_documents(self, doc_ids: List[str]) -> int:
        """Delete documents from memory store.

        Args:
            doc_ids: List of document IDs to delete

        Returns:
            Number of documents deleted
        """
        count = 0
        for doc_id in doc_ids:
            if doc_id in self._documents:
                del self._documents[doc_id]
                self._vectors.pop(doc_id, None)
                count += 1
        return count

    def update_document(self, doc_id: str, document: Document) -> bool:
        """Update a document in memory store.

        Args:
            doc_id: Document ID to update
            document: New document data

        Returns:
            True if updated successfully
        """
        if doc_id not in self._documents:
            return False
        self._documents[doc_id] = document
        if document.embedding:
            self._vectors[doc_id] = document.embedding
        return True

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        return self._documents.get(doc_id)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """Search for similar documents using cosine similarity.

        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filters: Metadata filters (optional)

        Returns:
            List of (document, score) tuples, sorted by score
        """
        query_vec = np.array(query_vector)
        results = []

        for doc_id, vector in self._vectors.items():
            doc = self._documents.get(doc_id)
            if doc is None:
                continue

            # Apply metadata filters
            if filters and not self._matches_filters(doc, filters):
                continue

            # Calculate cosine similarity
            vec = np.array(vector)
            similarity = self._cosine_similarity(query_vec, vec)
            results.append((doc, float(similarity)))

        # Sort by score descending and return top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _matches_filters(self, doc: Document, filters: Dict[str, Any]) -> bool:
        """Check if document matches metadata filters.

        Args:
            doc: Document to check
            filters: Filter conditions

        Returns:
            True if all filters match
        """
        doc_dict = doc.to_dict()

        for key, value in filters.items():
            if key == "metadata" and isinstance(value, dict):
                # Handle nested metadata filters
                for meta_key, meta_value in value.items():
                    if not self._check_condition(
                        doc.metadata.get(meta_key), meta_value
                    ):
                        return False
            else:
                doc_value = doc_dict.get(key)
                if not self._check_condition(doc_value, value):
                    return False

        return True

    def _check_condition(self, doc_value: Any, condition: Any) -> bool:
        """Check if document value matches filter condition.

        Supports:
        - Exact match: {"field": "value"}
        - Range query: {"field": {"gte": 5, "lte": 10}}
        - Multi-value: {"field": ["value1", "value2"]}

        Args:
            doc_value: Value from document
            condition: Filter condition

        Returns:
            True if condition matches
        """
        # Range query
        if isinstance(condition, dict):
            if doc_value is None:
                return False
            for op, val in condition.items():
                if op == "gte" and not (doc_value >= val):
                    return False
                elif op == "gt" and not (doc_value > val):
                    return False
                elif op == "lte" and not (doc_value <= val):
                    return False
                elif op == "lt" and not (doc_value < val):
                    return False
                elif op == "eq" and not (doc_value == val):
                    return False
                elif op == "ne" and not (doc_value != val):
                    return False
            return True

        # Multi-value match (OR)
        if isinstance(condition, list):
            return doc_value in condition

        # Exact match
        return doc_value == condition

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity score
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return np.dot(a, b) / (norm_a * norm_b)

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics.

        Returns:
            Dictionary with statistics
        """
        vectors = list(self._vectors.values())
        dim = len(vectors[0]) if vectors else 0

        return {
            "document_count": len(self._documents),
            "vector_count": len(self._vectors),
            "vector_dimension": dim,
            "backend": "memory",
        }

    def health_check(self) -> bool:
        """Check if the store is healthy.

        Returns:
            Always True for memory store
        """
        return True

    def save_to_file(self, filepath: str) -> None:
        """Save index to file.

        Args:
            filepath: Path to save index
        """
        data = {
            "documents": {k: v.to_dict() for k, v in self._documents.items()},
            "vectors": self._vectors,
        }
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, filepath: str) -> None:
        """Load index from file.

        Args:
            filepath: Path to load index from
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._documents = {
            k: Document.from_dict(v) for k, v in data.get("documents", {}).items()
        }
        self._vectors = data.get("vectors", {})
