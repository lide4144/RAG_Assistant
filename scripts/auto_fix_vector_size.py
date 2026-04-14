#!/usr/bin/env python3
"""Auto-fix vector_store.vector_size based on embedding model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Model dimensions mapping
MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "Qwen/Qwen3-Embedding-8B": 1024,
    "Qwen/Qwen3-Embedding-4B": 1024,
    "BAAI/bge-large-zh": 1024,
    "BAAI/bge-base-zh": 768,
    "BAAI/bge-m3": 1024,
    "nomic-embed-text": 768,
}


def get_expected_dimension(model_name: str) -> int | None:
    """Get expected vector dimension for a model."""
    # Exact match
    if model_name in MODEL_DIMENSIONS:
        return MODEL_DIMENSIONS[model_name]

    # Partial match
    for key, dim in MODEL_DIMENSIONS.items():
        if key in model_name or model_name in key:
            return dim

    return None


def fix_vector_size():
    """Auto-fix vector_size in config."""
    from app.config import load_config
    import yaml

    config = load_config()

    # Get current embedding model
    embedding_model = ""
    if hasattr(config, "embedding") and config.embedding:
        emb = config.embedding
        if hasattr(emb, "model"):
            embedding_model = emb.model
    elif hasattr(config, "embedding_model"):
        embedding_model = config.embedding_model

    if not embedding_model:
        print("❌ Could not detect embedding model")
        return False

    # Get expected dimension
    expected_dim = get_expected_dimension(embedding_model)
    if not expected_dim:
        print(f"⚠️  Unknown model: {embedding_model}")
        print("   Please manually set vector_store.vector_size")
        return False

    # Get current vector_size
    vector_store = config.vector_store
    current_dim = vector_store.get("vector_size", 1024)

    if current_dim == expected_dim:
        print(f"✅ Vector size already correct: {current_dim}D")
        return True

    print(f"🔧 Fixing vector_size:")
    print(f"   Model: {embedding_model}")
    print(f"   Current: {current_dim}D")
    print(f"   Expected: {expected_dim}D")

    # Read YAML file
    config_path = Path("configs/default.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace vector_size
    import re

    pattern = r"(vector_store:[\s\S]*?vector_size:\s*)\d+"
    replacement = r"\g<1>" + str(expected_dim)

    new_content = re.sub(pattern, replacement, content)

    if new_content == content:
        print("❌ Could not auto-fix. Please manually edit configs/default.yaml")
        return False

    # Write back
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Updated vector_store.vector_size to {expected_dim}")
    print(f"   Please restart the service to apply changes")
    return True


if __name__ == "__main__":
    success = fix_vector_size()
    sys.exit(0 if success else 1)
