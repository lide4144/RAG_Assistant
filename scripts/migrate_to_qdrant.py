#!/usr/bin/env python3
"""Migrate existing vector index to Qdrant.

Usage:
    python scripts/migrate_to_qdrant.py [options]

Examples:
    # Preview migration without uploading
    python scripts/migrate_to_qdrant.py --dry-run

    # Migrate and verify
    python scripts/migrate_to_qdrant.py --verify

    # Migrate specific index file
    python scripts/migrate_to_qdrant.py --input data/indexes/vec_index_embed.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.vector_store import Document, VectorStoreFactory
from app.vector_store.qdrant_store import QdrantVectorStore


def load_index_file(filepath: str) -> Dict[str, Any]:
    """Load vector index from JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def convert_to_documents(index_data: Dict[str, Any]) -> List[Document]:
    """Convert index data to Document objects.

    Supports both vec_index.json and vec_index_embed.json formats.
    """
    docs = []

    # Handle embed index format (with embeddings)
    if "docs" in index_data and isinstance(index_data["docs"], list):
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
                    "block_type": doc_data.get("block_type"),
                    "markdown_source": doc_data.get("markdown_source"),
                    "structure_provenance": doc_data.get("structure_provenance"),
                },
            )
            docs.append(doc)
    else:
        # Handle simple format
        for i, (doc_id, doc_data) in enumerate(index_data.items()):
            if isinstance(doc_data, dict):
                doc = Document(
                    doc_id=doc_id,
                    paper_id=doc_data.get("paper_id", ""),
                    content_type=doc_data.get("content_type", "body"),
                    page_start=doc_data.get("page_start", 0),
                    section=doc_data.get("section"),
                    text=doc_data.get("text", ""),
                    clean_text=doc_data.get("clean_text", ""),
                    embedding=doc_data.get("embedding"),
                    metadata=doc_data.get("metadata", {}),
                )
                docs.append(doc)

    return docs


def check_existing_documents(store: QdrantVectorStore, doc_ids: List[str]) -> List[str]:
    """Check which documents already exist in Qdrant.

    Returns:
        List of existing document IDs
    """
    existing = []
    for doc_id in doc_ids:
        doc = store.get_document(doc_id)
        if doc is not None:
            existing.append(doc_id)
    return existing


def migrate(
    input_path: str,
    config: Dict[str, Any],
    dry_run: bool = False,
    verify: bool = False,
    skip_existing: bool = True,
) -> bool:
    """Migrate index to Qdrant.

    Args:
        input_path: Path to input index file
        config: Qdrant configuration
        dry_run: If True, only preview without uploading
        verify: If True, verify after migration
        skip_existing: If True, skip documents that already exist

    Returns:
        True if successful
    """
    print(f"Loading index from: {input_path}")
    index_data = load_index_file(input_path)

    print("Converting to documents...")
    documents = convert_to_documents(index_data)
    print(f"Found {len(documents)} documents")

    if not documents:
        print("No documents to migrate!")
        return False

    # Check for embeddings
    docs_with_embeddings = [d for d in documents if d.embedding]
    print(f"Documents with embeddings: {len(docs_with_embeddings)}")

    if dry_run:
        print("\n[DRY RUN] Would upload the following documents:")
        for doc in documents[:5]:
            print(f"  - {doc.doc_id}: {doc.paper_id} (page {doc.page_start})")
        if len(documents) > 5:
            print(f"  ... and {len(documents) - 5} more")
        return True

    # Connect to Qdrant
    print(
        f"\nConnecting to Qdrant at {config.get('host', 'localhost')}:{config.get('port', 6333)}"
    )
    try:
        store = VectorStoreFactory.create(config)
        if not isinstance(store, QdrantVectorStore):
            print("Error: Configured backend is not Qdrant!")
            return False
    except Exception as e:
        print(f"Failed to connect to Qdrant: {e}")
        return False

    # Check health
    if not store.health_check():
        print("Qdrant health check failed!")
        return False
    print("Qdrant connection: OK")

    # Check for existing documents
    if skip_existing:
        doc_ids = [d.doc_id for d in documents]
        existing_ids = check_existing_documents(store, doc_ids)
        if existing_ids:
            print(f"\nFound {len(existing_ids)} existing documents, skipping...")
            documents = [d for d in documents if d.doc_id not in existing_ids]
            print(f"Documents to upload: {len(documents)}")

    if not documents:
        print("No new documents to upload!")
        return True

    # Upload documents
    print(f"\nUploading {len(documents)} documents to Qdrant...")
    try:
        uploaded_ids = store.add_documents(documents)
        print(f"Successfully uploaded {len(uploaded_ids)} documents")
    except Exception as e:
        print(f"Upload failed: {e}")
        return False

    # Verify
    if verify:
        print("\nVerifying migration...")
        stats = store.get_collection_stats()
        print(f"Collection stats: {stats}")

        # Check a few documents
        sample_docs = documents[: min(5, len(documents))]
        verified = 0
        for doc in sample_docs:
            retrieved = store.get_document(doc.doc_id)
            if retrieved and retrieved.paper_id == doc.paper_id:
                verified += 1
        print(f"Verification: {verified}/{len(sample_docs)} sample documents OK")

    print("\nMigration complete!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate existing vector index to Qdrant"
    )
    parser.add_argument(
        "--input",
        default="data/indexes/vec_index_embed.json",
        help="Input index file path (default: data/indexes/vec_index_embed.json)",
    )
    parser.add_argument(
        "--host", default="localhost", help="Qdrant host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=6333, help="Qdrant port (default: 6333)"
    )
    parser.add_argument("--url", help="Qdrant Cloud URL (overrides host/port)")
    parser.add_argument("--api-key", help="Qdrant Cloud API key")
    parser.add_argument(
        "--collection",
        default="paper_chunks",
        help="Qdrant collection name (default: paper_chunks)",
    )
    parser.add_argument(
        "--vector-size", type=int, default=1024, help="Vector dimension (default: 1024)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview migration without uploading"
    )
    parser.add_argument(
        "--verify", action="store_true", help="Verify migration after upload"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-upload existing documents (default: skip)",
    )

    args = parser.parse_args()

    # Build config
    config = {
        "backend": "qdrant",
        "host": args.host,
        "port": args.port,
        "collection_name": args.collection,
        "vector_size": args.vector_size,
        "batch_size": 100,
        "timeout": 60,
    }

    if args.url:
        config["url"] = args.url
        config["api_key"] = args.api_key

    # Run migration
    success = migrate(
        input_path=args.input,
        config=config,
        dry_run=args.dry_run,
        verify=args.verify,
        skip_existing=not args.no_skip_existing,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
