#!/usr/bin/env bash

################################################################################
# Script: run-profile.sh
# Description: Run one explicit ingestor test capability profile.
# Usage: scripts/test/run-profile.sh {core|rls|broker|ai}
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

trap 'error "Profile test failed at line ${LINENO}"' ERR

cd "${PROJECT_ROOT}"

run_core() {
    local marker
    marker='((unit or integration) and not capability_rls and not capability_broker'
    marker+=' and not capability_ai and not full_optional and not demo and not e2e)'
    env \
        CACHE_ENABLED=false \
        BROKER_ENABLED=false \
        NOTIFICATIONS_ENABLED=false \
        AUTH_DEMO_ROUTES_ENABLED=false \
        OPENAI_ENABLED=false \
        ANTHROPIC_ENABLED=false \
        OTEL_ENABLED=false \
        BACKGROUND_WORKERS_ENABLED=false \
        RETENTION_ENABLED=false \
        uv run pytest tests/unit services/ingestor/tests -m "${marker}" -q
}

run_rls() {
    env RLS_ENABLED=true uv run pytest services/ingestor/tests -m capability_rls -q
}

run_broker() {
    env \
        BROKER_ENABLED=true \
        NOTIFICATIONS_ENABLED=true \
        NOTIFICATION_DELIVERY_MODE=broker \
        uv run --extra messaging pytest services/ingestor/tests -m capability_broker -q
}

run_ai() {
    env ANTHROPIC_ENABLED=false uv run --extra ai pytest services/ingestor/tests -m capability_ai -q
}

case "${1:-}" in
    core) run_core ;;
    rls) run_rls ;;
    broker) run_broker ;;
    ai) run_ai ;;
    *) error "Usage: ${0} {core|rls|broker|ai}" ;;
esac
