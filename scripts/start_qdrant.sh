#!/bin/bash
# Start Qdrant locally using Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "======================================"
echo "Starting Qdrant (Local Docker Mode)"
echo "======================================"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found!"
    echo ""
    echo "Please install Docker first:"
    echo "  Option 1: Install Docker Desktop from https://www.docker.com/products/docker-desktop"
    echo "            Enable WSL2 integration in Settings → Resources → WSL Integration"
    echo "  Option 2: Run: bash scripts/install_docker_wsl.sh (for WSL without Docker Desktop)"
    echo ""
    exit 1
fi

echo "✓ Docker found: $(docker --version)"

# Check if Docker Compose is available
if ! docker compose version &> /dev/null && ! docker-compose --version &> /dev/null; then
    echo "❌ Docker Compose not found!"
    echo ""
    exit 1
fi

echo "✓ Docker Compose found"
echo ""

# Start Qdrant
echo "🚀 Starting Qdrant container..."
cd "$PROJECT_DIR"

if [ -f "docker-compose.qdrant.yml" ]; then
    docker compose -f docker-compose.qdrant.yml up -d
    echo ""
    echo "✅ Qdrant started successfully!"
    echo ""
    echo "📊 Qdrant Dashboard: http://localhost:6333/dashboard"
    echo "🔗 API Endpoint: http://localhost:6333"
    echo ""
    echo "To stop Qdrant:"
    echo "  docker compose -f docker-compose.qdrant.yml down"
    echo ""
    echo "To check status:"
    echo "  docker ps | grep qdrant"
    echo ""
    
    # Wait a moment for Qdrant to be ready
    echo "⏳ Waiting for Qdrant to be ready..."
    sleep 3
    
    # Test connection
    if command -v curl &> /dev/null; then
        if curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
            echo "✅ Qdrant is healthy and ready!"
        else
            echo "⚠️  Qdrant is starting, please wait a few more seconds..."
        fi
    fi
else
    echo "❌ docker-compose.qdrant.yml not found!"
    exit 1
fi
