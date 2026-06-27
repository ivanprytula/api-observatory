#!/usr/bin/env bash
set -euo pipefail

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
PG_DB="${PG_DB:-data_pipeline}"

# MongoDB connection
MONGO_HOST="${MONGO_HOST:-localhost}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_DB="${MONGO_DB:-data_zoo}"

# Cloud storage configuration
# BACKUP_STORAGE: local | blob | both  (default: local)
BACKUP_STORAGE="${BACKUP_STORAGE:-local}"
BACKUP_BLOB_CONTAINER="${BACKUP_BLOB_CONTAINER:-backups}"
BACKUP_BLOB_PREFIX="${BACKUP_BLOB_PREFIX:-}"
# AZURE_STORAGE_CONNECTION_STRING: set for floci-az emulator or real Azure Storage

# ─── Setup ─────────────────────────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}/postgres" "${BACKUP_DIR}/mongodb"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

# ─── Blob Storage upload helper ─────────────────────────────────────────────────
upload_to_blob() {
    local local_file="${1}"
    local blob_name="${2}"

    if [[ -z "${AZURE_STORAGE_CONNECTION_STRING:-}" ]]; then
        error "AZURE_STORAGE_CONNECTION_STRING is not set; cannot upload to Blob Storage"
        return 1
    fi

    log "Uploading ${local_file} → ${BACKUP_BLOB_CONTAINER}/${BACKUP_BLOB_PREFIX}${blob_name}"
    az storage blob upload \
        --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
        --container-name "${BACKUP_BLOB_CONTAINER}" \
        --name "${BACKUP_BLOB_PREFIX}${blob_name}" \
        --file "${local_file}" \
        --overwrite \
        --output none
    log "Blob upload complete: ${BACKUP_BLOB_CONTAINER}/${BACKUP_BLOB_PREFIX}${blob_name}"
}

# ─── PostgreSQL backup ──────────────────────────────────────────────────────────
backup_postgres() {
    local out="${BACKUP_DIR}/postgres/pg_${PG_DB}_${TIMESTAMP}.sql.gz"
    log "Backing up PostgreSQL database '${PG_DB}' → ${out}"

    PGPASSWORD="${PG_PASSWORD}" pg_dump \
        --host="${PG_HOST}" \
        --port="${PG_PORT}" \
        --username="${PG_USER}" \
        --format=custom \
        --compress=9 \
        --no-owner \
        --no-acl \
        "${PG_DB}" | gzip > "${out}"

    local size
    size=$(du -sh "${out}" | cut -f1)
    log "PostgreSQL backup complete: ${out} (${size})"

    if [[ "${BACKUP_STORAGE}" == "blob" || "${BACKUP_STORAGE}" == "both" ]]; then
        upload_to_blob "${out}" "postgres/$(basename "${out}")"
    fi

    echo "${out}"
}

# ─── MongoDB backup ─────────────────────────────────────────────────────────────
backup_mongodb() {
    if ! command -v mongodump &>/dev/null; then
        log "mongodump not found, skipping MongoDB backup"
        return 0
    fi

    local out="${BACKUP_DIR}/mongodb/mongo_${MONGO_DB}_${TIMESTAMP}"
    log "Backing up MongoDB '${MONGO_DB}' → ${out}.archive.gz"

    mongodump \
        --host="${MONGO_HOST}" \
        --port="${MONGO_PORT}" \
        --db="${MONGO_DB}" \
        --archive="${out}.archive.gz" \
        --gzip

    local size
    size=$(du -sh "${out}.archive.gz" | cut -f1)
    log "MongoDB backup complete: ${out}.archive.gz (${size})"

    if [[ "${BACKUP_STORAGE}" == "blob" || "${BACKUP_STORAGE}" == "both" ]]; then
        upload_to_blob "${out}.archive.gz" "mongodb/$(basename "${out}.archive.gz")"
    fi

    echo "${out}.archive.gz"
}

# ─── Rotate old backups ─────────────────────────────────────────────────────────
rotate_backups() {
    log "Rotating backups older than ${RETENTION_DAYS} days..."
    find "${BACKUP_DIR}" -name "*.gz" -mtime "+${RETENTION_DAYS}" -delete
    local remaining
    remaining=$(find "${BACKUP_DIR}" -name "*.gz" | wc -l)
    log "Rotation complete. ${remaining} backup(s) retained."
}

# ─── Main ───────────────────────────────────────────────────────────────────────
main() {
    log "Starting Data Zoo backup (timestamp: ${TIMESTAMP})"

    local pg_file mongo_file
    pg_file=$(backup_postgres)
    mongo_file=$(backup_mongodb) || true

    rotate_backups

    log ""
    log "Backup summary:"
    log "  PostgreSQL : ${pg_file}"
    [[ -n "${mongo_file:-}" ]] && log "  MongoDB    : ${mongo_file}"
    log "  Backup dir : ${BACKUP_DIR}"
    log "Done."
}

main "$@"
