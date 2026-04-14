#!/usr/bin/env python3
"""Validate configuration consistency."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_config

# Common embedding model dimensions
MODEL_DIMENSIONS = {
    # OpenAI
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    # Qwen
    "Qwen/Qwen3-Embedding-8B": 1024,
    "Qwen/Qwen3-Embedding-4B": 1024,
    # BGE
    "BAAI/bge-large-zh": 1024,
    "BAAI/bge-base-zh": 768,
    "BAAI/bge-m3": 1024,
    # Others
    "nomic-embed-text": 768,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}


def validate_config():
    """Validate configuration consistency."""
    print("=" * 60)
    print("Configuration Validation")
    print("=" * 60)

    config = load_config()
    warnings = []
    errors = []

    # Check vector store backend
    print("\n📦 Vector Store Configuration:")
    vector_store = config.vector_store
    backend = vector_store.get("backend", "memory")
    print(f"   Backend: {backend}")

    if backend == "qdrant":
        host = vector_store.get("host", "localhost")
        port = vector_store.get("port", 6333)
        collection = vector_store.get("collection_name", "paper_chunks")
        vector_size = vector_store.get("vector_size", 1024)

        print(f"   Host: {host}:{port}")
        print(f"   Collection: {collection}")
        print(f"   Vector size: {vector_size}")

    # Check embedding configuration
    print("\n🤖 Embedding Service:")
    embedding_model = ""
    if hasattr(config, "embedding") and config.embedding:
        emb = config.embedding
        if hasattr(emb, "model"):
            embedding_model = emb.model
            print(f"   Model: {embedding_model}")
        if hasattr(emb, "enabled"):
            print(f"   Enabled: {emb.enabled}")
        if hasattr(emb, "provider"):
            print(f"   Provider: {emb.provider}")
        if hasattr(emb, "batch_size"):
            print(f"   Batch size: {emb.batch_size}")
    elif hasattr(config, "embedding_model"):
        embedding_model = config.embedding_model
        print(f"   Model: {embedding_model}")

    # Check dimension compatibility for Qdrant
    if backend == "qdrant" and embedding_model:
        print("\n🔗 Dimension Compatibility Check:")
        expected_dim = MODEL_DIMENSIONS.get(embedding_model)
        if expected_dim:
            print(f"   Model dimension: {expected_dim}")
            print(f"   Qdrant vector_size: {vector_size}")
            if expected_dim != vector_size:
                errors.append(
                    f"❌ Dimension mismatch! Model outputs {expected_dim}D, "
                    f"but Qdrant expects {vector_size}D"
                )
                print(f"\n   ❌ ERROR: Dimension mismatch!")
                print(f"      Fix: Set vector_store.vector_size = {expected_dim}")
            else:
                print(f"   ✅ Dimensions match: {vector_size}D")
        else:
            warnings.append(f"⚠️  Unknown embedding model: {embedding_model}")
            print(f"   ⚠️  Unknown model dimension")
            print(f"      Please ensure vector_size ({vector_size}) matches your model")

    # Display results
    print("\n" + "=" * 60)
    if errors:
        print("❌ ERRORS FOUND:")
        for error in errors:
            print(f"   {error}")

    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   {warning}")

    if not errors and not warnings:
        print("✅ Configuration is valid!")

    print("=" * 60)

    return len(errors) == 0


if __name__ == "__main__":
    success = validate_config()
    sys.exit(0 if success else 1)
