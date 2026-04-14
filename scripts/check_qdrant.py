#!/usr/bin/env python3
"""Check Qdrant collection stats."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_config
from app.vector_store.factory import VectorStoreFactory


def check_qdrant():
    """Check Qdrant collection stats."""
    print("=" * 60)
    print("Qdrant Collection Status")
    print("=" * 60)

    config = load_config()
    store = VectorStoreFactory.create(config.vector_store)

    # Get collection info
    info = store.get_collection_info()
    print(f"\n📊 Collection: {store.collection_name}")
    print(f"   Vector size: {info.get('vector_size')}")
    print(f"   Distance: {info.get('distance')}")
    print(f"   Document count: {info.get('document_count', 0)}")

    # Check if empty
    doc_count = info.get("document_count", 0)
    if doc_count == 0:
        print("\n⚠️  Collection is empty")
        print("\n   To add documents, run:")
        print("   python -m app.build_indexes \\")
        print("     --input data/processed/chunks_clean.jsonl \\")
        print("     --bm25-out data/indexes/bm25_index.json \\")
        print("     --vec-out data/indexes/vec_index.json \\")
        print("     --embed-out data/indexes/vec_index_embed.json")
    else:
        print(f"\n✅ Collection has {doc_count} documents")
        print("\n   Documents are ready for search!")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    check_qdrant()
