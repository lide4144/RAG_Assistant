"""Base vector store interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class Document:
    """Document data model for vector store.

    Attributes:
        doc_id: Unique document identifier
        paper_id: Paper identifier
        content_type: Content type ("body", "abstract", "title")
        page_start: Starting page number
        section: Section title (optional)
        text: Original text content
        clean_text: Cleaned text content
        embedding: Vector embedding (optional)
        metadata: Additional metadata fields
    """

    doc_id: str
    paper_id: str
    content_type: str
    page_start: int
    text: str
    clean_text: str
    section: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary."""
        return {
            "doc_id": self.doc_id,
            "paper_id": self.paper_id,
            "content_type": self.content_type,
            "page_start": self.page_start,
            "section": self.section,
            "text": self.text,
            "clean_text": self.clean_text,
            "embedding": self.embedding,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        """Create document from dictionary."""
        return cls(
            doc_id=data["doc_id"],
            paper_id=data["paper_id"],
            content_type=data["content_type"],
            page_start=data["page_start"],
            section=data.get("section"),
            text=data["text"],
            clean_text=data["clean_text"],
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {}),
        )


class BaseVectorStore(ABC):
    """Abstract base class for vector storage backends.

    All vector store implementations must inherit from this class
    and implement all abstract methods.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize vector store.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

    @abstractmethod
    def add_documents(self, documents: List[Document]) -> List[str]:
        """Add documents to the store.

        Args:
            documents: List of documents to add

        Returns:
            List of document IDs
        """
        pass

    @abstractmethod
    def delete_documents(self, doc_ids: List[str]) -> int:
        """Delete documents from the store.

        Args:
            doc_ids: List of document IDs to delete

        Returns:
            Number of documents deleted
        """
        pass

    @abstractmethod
    def update_document(self, doc_id: str, document: Document) -> bool:
        """Update a document in the store.

        Args:
            doc_id: Document ID to update
            document: New document data

        Returns:
            True if updated successfully
        """
        pass

    @abstractmethod
    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """Search for similar documents.

        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filters: Metadata filters (optional)

        Returns:
            List of (document, score) tuples, sorted by score
        """
        pass

    @abstractmethod
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics.

        Returns:
            Dictionary with statistics (document count, vector dimension, etc.)
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the store is healthy.

        Returns:
            True if healthy
        """
        pass

    def _chunk_list(self, items: List, chunk_size: int = 100) -> List[List]:
        """Split list into chunks for batch processing.

        Args:
            items: List to chunk
            chunk_size: Size of each chunk

        Returns:
            List of chunks
        """
        return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
