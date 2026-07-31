#!/usr/bin/env bash
set -euo pipefail

# Post-deploy smoke-test for ingestor + dashboard.
#
# Usage:
#   scripts/smoke-test.sh [BASE_URL] [DASHBOARD_URL] [MAX_WAIT_SECONDS]
#
# Environment:
#   BASE_URL        Ingestor base URL (default: http://127.0.0.1:8000)
#   DASHBOARD_URL   Dashboard base URL (default: http://127.0.0.1:8501)
#   MAX_WAIT_SECONDS How long to wait for services (default: 120)
#   LOCAL_API_SCHEME http or https (default: http)
#   LOCAL_TLS_VERIFY false to pass -k for local HTTPS
#   SMOKE_JWT       Override JWT for v1 API routes. When unset, a token is
#                   minted locally from API_OBS_JWT_SECRET (.env) so the smoke
#                   test can authenticate against the local or deployed stack.
#
# Exit 0 if all checks pass, 1 otherwise.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
DASHBOARD_URL="${2:-${DASHBOARD_URL:-http://127.0.0.1:8501}}"
MAX_WAIT="${3:-${MAX_WAIT_SECONDS:-120}}"
LOCAL_API_SCHEME="${LOCAL_API_SCHEME:-http}"
LOCAL_TLS_VERIFY="${LOCAL_TLS_VERIFY:-true}"
PASS=0
FAIL=0

CURL_TLS_FLAG=()
if [ "$LOCAL_TLS_VERIFY" = "false" ]; then
  CURL_TLS_FLAG=(-k)
fi

SMOKE_JWT="${SMOKE_JWT:-}"
if [ -z "$SMOKE_JWT" ]; then
  if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env"
    set +a
    SMOKE_JWT="$(
      cd "$PROJECT_ROOT"
      JWT_SECRET="${API_OBS_JWT_SECRET:-}" uv run python -c \
        'from services.ingestor.auth import create_jwt_token
print(create_jwt_token("smoke-test", {"roles": ["admin"]}))'
    )" || SMOKE_JWT=""
  fi
fi
AUTH_ARGS=()
if [ -n "$SMOKE_JWT" ]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${SMOKE_JWT}")
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
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
      "${AUTH_ARGS[@]}" \
      "${CURL_TLS_FLAG[@]}" \
      -d "$data" \
      --max-time 10 "$url" 2>/dev/null || echo "000")
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" -X GET \
      "${AUTH_ARGS[@]}" \
      "${CURL_TLS_FLAG[@]}" \
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
  while [ $elapsed -lt "$MAX_WAIT" ]; do
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

check_http_range() {
  local name="$1"
  local url="$2"
  local code

  code="$(curl "${CURL_TLS_FLAG[@]}" -s -o /dev/null -w "%{http_code}" \
    --max-time 10 "$url" 2>/dev/null || echo "000")"

  # Accept success and redirects for edge/doc routes.
  if [[ "$code" =~ ^2[0-9][0-9]$ || "$code" =~ ^3[0-9][0-9]$ ]]; then
    echo -e "${GREEN}PASS${NC} $name (HTTP $code)"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${NC} $name (HTTP $code, expected 2xx/3xx) — $url"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Post-deploy smoke test ==="
echo "Ingestor: $BASE_URL"
echo "Dashboard: $DASHBOARD_URL"
echo "Timeout: ${MAX_WAIT}s"
echo ""

# Wait for ingestor
wait_for "ingestor readyz" "${BASE_URL%/}/readyz" || true
wait_for "ingestor health" "${BASE_URL%/}/health" || true

# Core API checks
check "GET /metrics" "${BASE_URL%/}/metrics"
check "GET /health" "${BASE_URL%/}/health"
check "GET /readyz" "${BASE_URL%/}/readyz"
check "GET /api/v1/scorecards" "${BASE_URL%/}/api/v1/scorecards"
check "GET /api/v1/sources" "${BASE_URL%/}/api/v1/sources"
check "GET /health/jobs-metrics" "${BASE_URL%/}/health/jobs-metrics"

# Create + list observation cycle
OBS_PAYLOAD='{"source":"smoke-test","data":{"test":true,"ts":'$(date +%s)'},"tags":["smoke"]}'
check "POST /api/v1/observations" "${BASE_URL%/}/api/v1/observations" "POST" "$OBS_PAYLOAD" "201"

# List observations (paginated)
check "GET /api/v1/observations" "${BASE_URL%/}/api/v1/observations?limit=5"

# Dashboard checks (non-blocking — dashboard may be behind a path proxy)
if [ "${LOCAL_API_SCHEME}" = "https" ]; then
  DASH_HEALTH="${DASHBOARD_URL%/}_stcore/health"
  check "GET edge dashboard health" "$DASH_HEALTH" || \
    check "GET dashboard path health" "${DASHBOARD_URL%/}/dashboard/_stcore/health" || \
    check "GET direct dashboard health" "$DASHBOARD_URL/_stcore/health"
else
  DASH_HEALTH="$DASHBOARD_URL/_stcore/health"
  check "GET dashboard health" "$DASH_HEALTH"
fi

# Gateway/ingress checks (only when running through the HTTPS ingress proxy).
# BASE_URL must point at the gateway (e.g. https://127.0.0.1).
if [ "${LOCAL_API_SCHEME}" = "https" ]; then
  echo ""
  echo "=== Gateway / ingress checks ==="

  if docker compose config >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC} compose-config-ok"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${NC} compose-config-ok"
    FAIL=$((FAIL + 1))
  fi

  check_http_range "gateway edge" "${BASE_URL%/}/"
  check_http_range "ingestor docs via gateway" "${BASE_URL%/}/api/docs"
  check_http_range "analytics route via gateway" "${BASE_URL%/}/analytics/health"

  headers="$(curl "${CURL_TLS_FLAG[@]}" -sSI "${BASE_URL%/}/api/docs" 2>/dev/null || true)"
  if grep -qi '^x-request-id:' <<<"$headers"; then
    echo -e "${GREEN}PASS${NC} x-request-id header present"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${NC} x-request-id header missing"
    FAIL=$((FAIL + 1))
  fi
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
