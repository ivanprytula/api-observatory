#!/usr/bin/env bash

################################################################################
# Script: run-full-optional.sh
# Description: Run the deterministic composed optional operational flow.
# Usage: scripts/test/run-full-optional.sh
################################################################################

set -o errexit -o pipefail -o nounset -o errtrace

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly PROJECT_ROOT

: "${UV_CACHE_DIR:=/tmp/api-obs-uv-cache}"
export UV_CACHE_DIR

error() {
    echo "[error] $*" >&2
    exit 1
}

cleanup() {
    "${COMPOSE[@]}" rm --force --stop test-harness || true
}

trap 'error "Full optional test failed at line ${LINENO}"' ERR

readonly -a COMPOSE=(
    docker compose
    -f "${PROJECT_ROOT}/docker-compose.yml"
    -f "${PROJECT_ROOT}/docker-compose.test.yml"
    --profile test-harness
)

trap cleanup EXIT

"${COMPOSE[@]}" up -d --build --no-deps test-harness

for attempt in {1..30}; do
    if "${COMPOSE[@]}" exec -T test-harness python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"; then
        break
    fi
    if [[ "${attempt}" -eq 30 ]]; then
        error "Test harness did not become ready"
    fi
    sleep 1
done

env \
    TEST_HARNESS_URL=http://127.0.0.1:18080 \
    RLS_ENABLED=true \
    BROKER_ENABLED=true \
    NOTIFICATIONS_ENABLED=true \
    NOTIFICATION_DELIVERY_MODE=broker \
    ANTHROPIC_ENABLED=false \
    uv run --extra ai --extra messaging pytest \
    services/ingestor/tests/integration/test_full_optional_flow.py -q
