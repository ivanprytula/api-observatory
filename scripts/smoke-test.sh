#!/usr/bin/env bash
set -euo pipefail

# Post-deploy smoke-test for ingestor + dashboard.
#
# Usage:
#   scripts/smoke-test.sh [BASE_URL] [MAX_WAIT_SECONDS]
#
# Environment:
#   BASE_URL        Ingestor base URL (default: http://localhost:8000)
#   DASHBOARD_URL   Dashboard base URL (default: http://localhost:8501)
#   MAX_WAIT_SECONDS How long to wait for services (default: 120)
#
# Exit 0 if all checks pass, 1 otherwise.

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
DASHBOARD_URL="${2:-${DASHBOARD_URL:-http://localhost:8501}}"
MAX_WAIT="${MAX_WAIT_SECONDS:-120}"
PASS=0
FAIL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
  local name="$1"
  local url="$2"
  local method="${3:-GET}"
  local data="${4:-}"
  local expected="${5:-200}"

  if [ "$method" = "POST" ] && [ -n "$data" ]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Content-Type: application/json" \
      -d "$data" \
      --max-time 10 "$url" 2>/dev/null || echo "000")
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" -X GET \
      --max-time 10 "$url" 2>/dev/null || echo "000")
  fi

  if [ "$code" = "$expected" ]; then
    echo -e "${GREEN}PASS${NC} $name (HTTP $code)"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${NC} $name (HTTP $code, expected $expected) — $url"
    FAIL=$((FAIL + 1))
  fi
}

wait_for() {
  local name="$1"
  local url="$2"
  local elapsed=0
  while [ $elapsed -lt $MAX_WAIT ]; do
    if curl -sf --max-time 3 "$url" >/dev/null 2>&1; then
      echo -e "${GREEN}READY${NC} $name ($url)"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo -e "${RED}TIMEOUT${NC} $name after ${MAX_WAIT}s ($url)"
  return 1
}

echo "=== Post-deploy smoke test ==="
echo "Ingestor: $BASE_URL"
echo "Dashboard: $DASHBOARD_URL"
echo "Timeout: ${MAX_WAIT}s"
echo ""

# Wait for ingestor
wait_for "ingestor readyz" "$BASE_URL/readyz" || true
wait_for "ingestor health" "$BASE_URL/health" || true

# Core API checks
check "GET /metrics" "$BASE_URL/metrics"
check "GET /health" "$BASE_URL/health"
check "GET /readyz" "$BASE_URL/readyz"
check "GET /api/v1/scorecards" "$BASE_URL/api/v1/scorecards"
check "GET /api/v1/sources" "$BASE_URL/api/v1/sources"
check "GET /health/jobs-metrics" "$BASE_URL/health/jobs-metrics"

# Create + list observation cycle
OBS_PAYLOAD='{"source":"smoke-test","raw_data":{"test":true,"ts":'$(date +%s)'},"tags":["smoke"]}'
check "POST /api/v1/observations" "$BASE_URL/api/v1/observations" "POST" "$OBS_PAYLOAD" "201"

# List observations (paginated)
check "GET /api/v1/observations" "$BASE_URL/api/v1/observations?limit=5"

# Dashboard checks (non-blocking — dashboard may be behind a path proxy)
DASH_HEALTH="$DASHBOARD_URL/_stcore/health"
if [ "$DASHBOARD_URL" != "http://localhost:8501" ]; then
  # Try nginx-proxied path first, then direct
  DASH_HEALTH="$BASE_URL/dashboard/_stcore/health"
  check "GET /dashboard/_stcore/health" "$DASH_HEALTH" || \
    check "GET dashboard health" "$DASHBOARD_URL/_stcore/health"
else
  check "GET dashboard health" "$DASH_HEALTH"
fi

echo ""
echo "=== Results ==="
echo -e "Passed: ${GREEN}${PASS}${NC}"
echo -e "Failed: ${RED}${FAIL}${NC}"

if [ $FAIL -gt 0 ]; then
  echo ""
  echo "Smoke test FAILED — check the failed endpoints above."
  exit 1
fi
echo ""
echo "Smoke test PASSED — all endpoints healthy."
exit 0
