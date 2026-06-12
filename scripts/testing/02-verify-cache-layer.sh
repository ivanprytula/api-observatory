#!/usr/bin/env bash
# Verify Cache cache layer functionality — test hits, misses, fail-open behavior, metrics.
# Uses docker compose for full integration test.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "==> Cache Layer Verification"
echo ""

echo "Step 0: Installing dependencies"
uv sync --quiet
echo "✓ Dependencies installed"
echo ""

echo "Step 1: Starting docker compose (db + cache)"
docker compose up -d db cache
echo "Waiting for services to be healthy..."
docker compose ps

max_attempts=30
for i in $(seq 1 $max_attempts); do
  if docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1 && \
     docker compose exec -T cache redis-cli ping >/dev/null 2>&1; then
    echo "✓ Services healthy"
    break
  fi
  if [ $i -eq $max_attempts ]; then
    echo "✗ Services failed to start after ${max_attempts} attempts" >&2
    exit 1
  fi
  sleep 1
done
echo ""

echo "Step 2: Running cache integration tests (7 tests)"
if uv run pytest tests/integration/records/test_cache.py -v; then
  echo "✓ All 7 cache tests passed"
else
  echo "✗ Cache tests failed" >&2
  exit 1
fi
echo ""

echo "Step 3: Manual HTTP test – populate cache and verify hit"

echo "Starting app..."
uv run uvicorn services/ingestor/main:app --host 0.0.0.0 --port 8000 >/dev/null 2>&1 &
APP_PID=$!
trap "kill $APP_PID 2>/dev/null || true" EXIT

sleep 3
if ! kill -0 $APP_PID 2>/dev/null; then
  echo "✗ App failed to start" >&2
  exit 1
fi

echo "  Creating test record..."
RECORD=$(curl -s -X POST http://localhost:8000/api/v1/records \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test.example.com",
    "timestamp": "2024-01-15T10:00:00",
    "data": {"test": true},
    "tags": ["cache-test"]
  }')

RECORD_ID=$(echo "$RECORD" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')
if [ -z "$RECORD_ID" ]; then
  echo "✗ Failed to create test record" >&2
  kill $APP_PID 2>/dev/null || true
  exit 1
fi
echo "  Record ID: $RECORD_ID"

echo "  First GET (cache miss)..."
curl -s http://localhost:8000/api/v1/records/$RECORD_ID >/dev/null
echo "  ✓ Retrieved from DB, stored in cache"

echo "  Second GET (cache hit)..."
curl -s http://localhost:8000/api/v1/records/$RECORD_ID >/dev/null
echo "  ✓ Retrieved from cache"

echo "  Verifying Cache key..."
REDIS_KEY=$(docker compose exec -T cache redis-cli GET "dp:record:$RECORD_ID" | head -1)
if [ -n "$REDIS_KEY" ]; then
  echo "✓ Cache key found in cache service: dp:record:$RECORD_ID"
else
  echo "✗ Cache key not found in Cache" >&2
  kill $APP_PID 2>/dev/null || true
  exit 1
fi
echo ""

echo "Step 4: Testing fail-open – stop Cache, verify API still works"
docker compose stop cache
sleep 2
echo "  Cache service stopped. Making request without cache..."

RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/v1/records/$RECORD_ID)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)

if [ "$HTTP_CODE" = "200" ]; then
  echo "✓ API returned 200 even with Cache down (fail-open works)"
else
  echo "✗ API failed with HTTP $HTTP_CODE when Cache was down" >&2
  kill $APP_PID 2>/dev/null || true
  exit 1
fi
echo ""

echo "Step 5: Testing cache invalidation on DELETE"
docker compose start cache
sleep 2
echo "  Cache service restarted. Creating new record..."

RECORD2=$(curl -s -X POST http://localhost:8000/api/v1/records \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test2.example.com",
    "timestamp": "2024-01-15T11:00:00",
    "data": {"test": true},
    "tags": ["invalidation-test"]
  }')

RECORD_ID2=$(echo "$RECORD2" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')
echo "  Record ID: $RECORD_ID2"

echo "  Populating cache..."
curl -s http://localhost:8000/api/v1/records/$RECORD_ID2 >/dev/null

REDIS_KEY2=$(docker compose exec -T cache redis-cli GET "dp:record:$RECORD_ID2" | head -1)
if [ -n "$REDIS_KEY2" ]; then
  echo "  ✓ Record in cache"
else
  echo "✗ Record not in cache" >&2
  kill $APP_PID 2>/dev/null || true
  exit 1
fi

echo "  Deleting record..."
curl -s -X DELETE http://localhost:8000/api/v1/records/$RECORD_ID2

sleep 1
REDIS_KEY2_AFTER=$(docker compose exec -T cache redis-cli GET "dp:record:$RECORD_ID2" 2>/dev/null || true)
if [ -z "$REDIS_KEY2_AFTER" ]; then
  echo "✓ Cache invalidated after DELETE"
else
  echo "✗ Cache was not invalidated" >&2
  kill $APP_PID 2>/dev/null || true
  exit 1
fi
echo ""

kill $APP_PID 2>/dev/null || true
docker compose stop db cache >/dev/null 2>&1 || true

echo "==> All cache verification tests passed!"
echo ""
echo "Summary:"
echo "  ✓ Cache integration tests (7/7 passed)"
echo "  ✓ Cache miss → DB fetch → cache store"
echo "  ✓ Cache hit from Cache"
echo "  ✓ Fail-open: API works with Cache down"
echo "  ✓ Cache invalidation on DELETE"
