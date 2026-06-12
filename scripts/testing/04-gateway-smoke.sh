#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=scripts/daily/local-url.sh
source "${PROJECT_ROOT}/scripts/daily/local-url.sh"
export LOCAL_API_SCHEME="${LOCAL_API_SCHEME:-https}"
export LOCAL_TLS_VERIFY="${LOCAL_TLS_VERIFY:-false}"

BASE_URL="${1:-${BASE_URL:-https://127.0.0.1}}"

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command not found: $1" >&2
        exit 1
    fi
}

check_http() {
    local url="$1"
    local name="$2"
    local code

    code="$(curl_local -s -o /dev/null -w "%{http_code}" "$url")"

    # Accept success and redirects for edge/doc routes.
    if [[ "$code" =~ ^2[0-9][0-9]$ || "$code" =~ ^3[0-9][0-9]$ ]]; then
        echo "[PASS] $name ($url) -> HTTP $code"
    else
        echo "[FAIL] $name ($url) -> HTTP $code" >&2
        exit 1
    fi
}

require_cmd docker
require_cmd curl
require_cmd grep

echo "Running API Gateway smoke checks against: $BASE_URL"

echo "[1/5] Validate compose model"
docker compose config >/tmp/compose.out
echo "[PASS] compose-config-ok"

echo "[2/5] Gateway HTTPS edge"
check_http "$BASE_URL/" "gateway edge"

echo "[3/5] API docs via gateway"
check_http "$BASE_URL/api/docs" "ingestor docs via gateway"

echo "[4/5] Analytics health via gateway"
check_http "$BASE_URL/analytics/health" "analytics route via gateway"

echo "[5/5] X-Request-ID header on /api/*"
headers="$(curl_local -sSI "$BASE_URL/api/docs")"
if grep -qi '^x-request-id:' <<<"$headers"; then
    echo "[PASS] x-request-id header present"
else
    echo "[FAIL] x-request-id header missing" >&2
    exit 1
fi

echo "Gateway smoke test completed successfully."
