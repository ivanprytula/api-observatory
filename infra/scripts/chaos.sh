#!/usr/bin/env bash

# Script: chaos.sh
# Description: Inject a disposable local PostgreSQL blackout and restore the database on exit.
# Usage: infra/scripts/chaos.sh db

set -o errexit -o pipefail -o nounset -o errtrace

# Local-only PostgreSQL blackout exercise for the current Compose stack.
# It intentionally stops api-obs-ingestor-db and verifies the ingestor readiness
# endpoint degrades and then recovers. It does not exercise archived services.

DB_CONTAINER="${DB_CONTAINER:-api-obs-ingestor-db}"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
CHAOS_DURATION="${CHAOS_DURATION:-30}"
MAX_RECOVERY_SECONDS="${MAX_RECOVERY_SECONDS:-60}"
database_stopped=false

log() { echo "[$(date '+%H:%M:%S')] [CHAOS] $*"; }
die() { echo "[$(date '+%H:%M:%S')] [CHAOS] $*" >&2; exit 1; }

cleanup() {
    if [[ "${database_stopped}" == true ]]; then
        log "Recovery cleanup: restarting '${DB_CONTAINER}'"
        if docker start "${DB_CONTAINER}" >/dev/null 2>&1; then
            database_stopped=false
        else
            log "Recovery cleanup could not restart '${DB_CONTAINER}'"
        fi
    fi
}

trap cleanup EXIT

wait_for_postgres() {
    local elapsed=0
    while ! docker exec "${DB_CONTAINER}" pg_isready -U postgres >/dev/null 2>&1; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [[ "${elapsed}" -ge "${MAX_RECOVERY_SECONDS}" ]]; then
            die "PostgreSQL did not recover within ${MAX_RECOVERY_SECONDS}s"
        fi
    done
}

wait_for_readiness() {
    local elapsed=0
    while ! curl --fail --max-time 5 --silent "${API_BASE_URL}/readyz" >/dev/null; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [[ "${elapsed}" -ge "${MAX_RECOVERY_SECONDS}" ]]; then
            die "Ingestor readiness did not recover within ${MAX_RECOVERY_SECONDS}s"
        fi
    done
}

run_db_blackout() {
    docker inspect --format='{{.State.Running}}' "${DB_CONTAINER}" 2>/dev/null | grep -qx 'true' \
        || die "Database container '${DB_CONTAINER}' is not running"

    log "Stopping '${DB_CONTAINER}' for ${CHAOS_DURATION}s"
    docker stop "${DB_CONTAINER}" >/dev/null
    database_stopped=true

    local readiness_status
    readiness_status="$(curl --max-time 5 --silent --output /dev/null --write-out '%{http_code}' "${API_BASE_URL}/readyz" || true)"
    if [[ "${readiness_status}" == '200' ]]; then
        die "Ingestor readiness remained healthy while PostgreSQL was stopped"
    fi
    log "Readiness degraded while PostgreSQL was unavailable (HTTP ${readiness_status:-000})"

    sleep "${CHAOS_DURATION}"

    log "Restarting '${DB_CONTAINER}'"
    docker start "${DB_CONTAINER}" >/dev/null
    database_stopped=false
    wait_for_postgres
    wait_for_readiness
    log "PostgreSQL and ingestor readiness recovered"
}

usage() {
    cat <<EOF
Usage: $0 db

Runs a local PostgreSQL blackout against the current Compose service.

Environment variables:
  CHAOS_DURATION=30          Seconds PostgreSQL remains stopped
  API_BASE_URL=http://127.0.0.1:8000
  DB_CONTAINER=api-obs-ingestor-db
  MAX_RECOVERY_SECONDS=60
EOF
}

case "${1:-}" in
    db) run_db_blackout ;;
    *) usage; exit 1 ;;
esac
