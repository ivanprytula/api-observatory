#!/usr/bin/env bash

set -o errexit -o pipefail -o nounset -o errtrace

# ─── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# PostgreSQL connection (override via env vars)
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
PG_DB="${PG_DB:-api_obs_ingestor}"

# ─── Setup ─────────────────────────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}/postgres"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ─── PostgreSQL backup ──────────────────────────────────────────────────────────
backup_postgres() {
    local out="${BACKUP_DIR}/postgres/pg_${PG_DB}_${TIMESTAMP}.dump"
    log "Backing up PostgreSQL database '${PG_DB}' → ${out}"

    PGPASSWORD="${PG_PASSWORD}" pg_dump \
        --host="${PG_HOST}" \
        --port="${PG_PORT}" \
        --username="${PG_USER}" \
        --format=custom \
        --compress=9 \
        --no-owner \
        --no-acl \
        --file="${out}" \
        "${PG_DB}"

    local size
    size=$(du -sh "${out}" | cut -f1)
    log "PostgreSQL backup complete: ${out} (${size})"

    echo "${out}"
}

# ─── Rotate old backups ─────────────────────────────────────────────────────────
rotate_backups() {
    log "Rotating backups older than ${RETENTION_DAYS} days..."
    find "${BACKUP_DIR}" -name "*.dump" -mtime "+${RETENTION_DAYS}" -delete
    local remaining
    remaining=$(find "${BACKUP_DIR}" -name "*.dump" | wc -l)
    log "Rotation complete. ${remaining} backup(s) retained."
}

# ─── Main ───────────────────────────────────────────────────────────────────────
main() {
    log "Starting API Observatory local backup (timestamp: ${TIMESTAMP})"

    local pg_file
    pg_file=$(backup_postgres)

    rotate_backups

    log ""
    log "Backup summary:"
    log "  PostgreSQL : ${pg_file}"
    log "  Backup dir : ${BACKUP_DIR}"
    log "Done."
}

main "$@"
