#!/usr/bin/env python3
"""Test Qdrant connection and configuration (Local Docker Mode)."""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_config
from app.vector_store.factory import VectorStoreFactory
from app.vector_store.exceptions import VectorStoreConnectionError


def test_qdrant_connection():
    """Test Qdrant connection and basic operations."""
    print("=" * 60)
    print("Qdrant Connection Test (Local Docker Mode)")
    print("=" * 60)

    # Load configuration
    print("\n📋 Loading configuration...")
    try:
        config_obj = load_config()
        # Convert dataclass to dict for vector_store config
        vector_store_config = config_obj.vector_store
        backend = vector_store_config.get("backend", "memory")
        print(f"   ✓ Backend: {backend}")

        if backend != "qdrant":
            print(f"   ⚠️  Warning: Backend is set to '{backend}', not 'qdrant'")
            print(f"   To use Qdrant, update configs/default.yaml:")
            print(f"   vector_store:\n     backend: qdrant")
            return False

        # Check if using local or cloud mode
        host = vector_store_config.get("host", "localhost")
        port = vector_store_config.get("port", 6333)
        url = vector_store_config.get("url")

        if url and "cloud.qdrant" in url:
            print(f"   ⚠️  Configured for Qdrant Cloud (needs VPN in China)")
            print(f"   Current config uses URL: {url}")
        else:
            print(f"   ✓ Local mode: {host}:{port}")

    except Exception as e:
        print(f"   ❌ Failed to load configuration: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test connection
    print("\n🔗 Testing Qdrant connection...")
    try:
        store = VectorStoreFactory.create(vector_store_config)
        print(f"   ✓ Successfully connected to Qdrant")
        print(f"   ✓ Collection: {store.collection_name}")

        # Test health check
        print("\n🏥 Testing health check...")
        is_healthy = store.health_check()
        if is_healthy:
            print("   ✓ Qdrant is healthy")
        else:
            print("   ⚠️  Qdrant health check returned False")

        # Test collection info
        print("\n📊 Collection info...")
        try:
            info = store.get_collection_info()
            print(f"   ✓ Collection exists")
            print(f"   ✓ Vector size: {info.get('vector_size', 'N/A')}")
            print(f"   ✓ Distance: {info.get('distance', 'N/A')}")
            print(f"   ✓ Document count: {info.get('document_count', 'N/A')}")
        except Exception as e:
            print(f"   ⚠️  Could not get collection info: {e}")

        print("\n" + "=" * 60)
        print("✅ Qdrant configuration test PASSED")
        print("=" * 60)
        return True

    except VectorStoreConnectionError as e:
        print(f"   ❌ Connection failed: {e}")
        print("\n" + "=" * 60)
        print("❌ Qdrant configuration test FAILED")
        print("=" * 60)
        print("\nTroubleshooting:")
        print("1. Is Qdrant running? Start it with: bash scripts/start_qdrant.sh")
        print("2. Check if port 6333 is available: lsof -i :6333")
        print("3. Check Docker status: docker ps | grep qdrant")
        print("4. If using Qdrant Cloud, ensure you have VPN access")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_qdrant_connection()
    sys.exit(0 if success else 1)
