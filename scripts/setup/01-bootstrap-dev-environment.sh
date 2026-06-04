#!/usr/bin/env bash
# Complete development environment setup.
# Installs uv, syncs deps, creates .env, starts Docker Compose, initializes DB schema.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
NC='\033[0m'

echo "Data Pipeline — Complete Development Setup"
echo ""

echo "Step 1: Install uv package manager"
if command -v uv >/dev/null 2>&1; then
  UV_VERSION=$(uv --version | awk '{print $2}')
  echo "✓ uv already installed (v$UV_VERSION)"
else
  echo "Installing uv via official installer..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || {
    echo "✗ Failed to install uv. See: https://github.com/astral-sh/uv" >&2
    exit 1
  }
  echo "✓ uv installed"
fi

echo "Step 2: Initialize .env configuration"
if [ -f .env ]; then
  echo "✓ .env already exists (skipping)"
else
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "✓ .env created from .env.example"
    echo "Edit .env to customize settings (optional)"
  else
    echo "✗ .env.example not found" >&2
    exit 1
  fi
fi

echo "Step 3: Sync Python dependencies"
if uv sync; then
  echo "✓ Dependencies synced"
else
  echo "✗ Failed to sync dependencies" >&2
  exit 1
fi

echo "Step 4: Start Docker Compose services (db + redis)"
if ! command -v docker >/dev/null 2>&1; then
  echo "✗ Docker not installed or not in PATH" >&2
  echo "Install Docker Engine (Ubuntu/Debian): https://docs.docker.com/engine/install/ubuntu/" >&2
  exit 1
fi

if ! docker compose >/dev/null 2>&1; then
  echo "✗ Docker Compose not found" >&2
  exit 1
fi

echo "  Starting db and redis..."
docker compose up -d db redis
echo "  Waiting for services to be healthy..."

# Wait for services to be healthy (with timeout)
max_attempts=60
for i in $(seq 1 $max_attempts); do
  DB_READY=$(docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1 && echo "1" || echo "0")
  REDIS_READY=$(docker compose exec -T redis redis-cli ping >/dev/null 2>&1 && echo "1" || echo "0")

  if [ "$DB_READY" = "1" ] && [ "$REDIS_READY" = "1" ]; then
    echo -e "${GREEN}✓ Services healthy${NC}"
    break
  fi

  if [ $i -eq $max_attempts ]; then
    echo "✗ Services failed to start after ${max_attempts} attempts" >&2
    exit 1
  fi

  printf "."
  sleep 1
done
echo ""

echo "Step 5: Initialize database schema"
if uv run alembic upgrade head; then
  echo "✓ Database schema initialized"
else
  echo "✗ Failed to initialize database schema" >&2
  exit 1
fi

echo "✓ Development environment ready!"
echo ""
echo "Next steps:"
echo "1. Start the development server: just ingestor-start"
echo "2. Open API docs: http://localhost:8000/docs"
echo "3. Run tests:             just test"
echo "4. Full quality checks:   just quality"
echo ""
echo "Services running:"
docker compose ps
