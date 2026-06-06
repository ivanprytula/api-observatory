#!/usr/bin/env bash
# load_test.sh — seed test data and run k6 or locust pagination load tests.
#
# Commands:
#   seed [N]            Insert N records via the batch API (default: 10 000)
#   k6 [flags]          Run k6 comparison test (offset vs cursor)
#   locust [--web]      Run locust headless or with web UI (http://localhost:8089)
#   help                Show this message
#
# Environment variables:
#   BASE_URL      App base URL            (default: http://localhost:8000)
#   VUS           k6 virtual users        (default: 10)
#   DURATION      k6 test duration        (default: 30s)
#   LIMIT         Page size               (default: 50)
#   USERS         Locust concurrent users (default: 20)
#   SPAWN_RATE    Locust spawn rate/s     (default: 5)
#   RUNTIME       Locust run time         (default: 60s)
#
# Examples:
#   ./scripts/testing/03-load-test.sh seed 10000
#   ./scripts/testing/03-load-test.sh k6
#   VUS=20 DURATION=60s ./scripts/testing/03-load-test.sh k6
#   ./scripts/testing/03-load-test.sh locust
#   ./scripts/testing/03-load-test.sh locust --web
#   USERS=50 RUNTIME=120s ./scripts/testing/03-load-test.sh locust

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_info()  { echo "[info]  $*"; }
_error() { echo "[error] $*" >&2; exit 1; }

_check_app() {
    _info "Checking app health at ${BASE_URL}/health ..."
    if ! curl -fs "${BASE_URL}/health" > /dev/null 2>&1; then
        _error "App not reachable at ${BASE_URL}. Start it with: docker compose up app"
    fi
    _info "App is reachable."
}

_check_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" &> /dev/null; then
        _error "'$cmd' not found. Install it first:
  k6:    https://k6.io/docs/get-started/installation/
  locust: uv add --dev locust (already in pyproject.toml dev deps)"
    fi
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_seed() {
    local total="${1:-10000}"
    _info "Seeding ${total} records into ${BASE_URL} ..."
    _check_app
    uv run python "${SCRIPT_DIR}/seed_data.py" "${total}" "${BASE_URL}"
}

cmd_k6() {
    _check_cmd k6
    _check_app

    local vus="${VUS:-10}"
    local duration="${DURATION:-30s}"
    local limit="${LIMIT:-50}"

    _info "Running k6 — vus=${vus}, duration=${duration}, limit=${limit}"
    _info "Script: ${SCRIPT_DIR}/load_test_pagination.js"

    k6 run \
        --vus       "${vus}" \
        --duration  "${duration}" \
        --env       "BASE_URL=${BASE_URL}" \
        --env       "LIMIT=${limit}" \
        "$@" \
        "${SCRIPT_DIR}/load_test_pagination.js"
}

cmd_locust() {
    _check_cmd locust || _check_cmd "uv"
    _check_app

    if [[ "${1:-}" == "--web" ]]; then
        _info "Starting locust web UI → http://localhost:8089"
        _info "Press Ctrl-C to stop."
        uv run locust \
            -f "${SCRIPT_DIR}/locustfile.py" \
            --host "${BASE_URL}"
    else
        local users="${USERS:-20}"
        local spawn_rate="${SPAWN_RATE:-5}"
        local runtime="${RUNTIME:-60s}"

        _info "Running locust headless — users=${users}, spawn-rate=${spawn_rate}, run-time=${runtime}"
        uv run locust \
            -f "${SCRIPT_DIR}/locustfile.py" \
            --headless \
            -u "${users}" \
            -r "${spawn_rate}" \
            --run-time "${runtime}" \
            --host "${BASE_URL}" \
            "${@}"
    fi
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "${1:-help}" in
    seed)
        shift
        cmd_seed "$@"
        ;;
    k6)
        shift
        cmd_k6 "$@"
        ;;
    locust)
        shift
        cmd_locust "$@"
        ;;
    help | --help | -h | "")
        sed -n '/^# /p' "${BASH_SOURCE[0]}" | sed 's/^# //'
        ;;
    *)
        _error "Unknown command: '$1'. Run with 'help' for usage."
        ;;
esac
