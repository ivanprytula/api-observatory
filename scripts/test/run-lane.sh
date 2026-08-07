#!/usr/bin/env bash

################################################################################
# Script: run-lane.sh
# Description: Run a standard test lane without embedding long commands in Just.
# Usage: scripts/test/run-lane.sh {unit|integration|e2e|live}
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

trap 'error "Test lane failed at line ${LINENO}"' ERR

run_unit() {
    uv run --extra ai --extra messaging --extra etl pytest \
        tests/unit services/ingestor/tests/unit -m unit -q
}

run_integration() {
    uv run pytest -m integration -q
}

run_e2e() {
    uv run pytest -m 'e2e and not live and not chaos' -q
}

run_live() {
    uv run pytest -m 'live and e2e' --no-cov -q
}

cd "${PROJECT_ROOT}"

case "${1:-}" in
    unit) run_unit ;;
    integration) run_integration ;;
    e2e) run_e2e ;;
    live) run_live ;;
    *) error "Usage: ${0} {unit|integration|e2e|live}" ;;
esac
