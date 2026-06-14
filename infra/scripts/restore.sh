#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
PG_DB="${PG_DB:-data_pipeline}"

MONGO_HOST="${MONGO_HOST:-localhost}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_DB="${MONGO_DB:-data_zoo}"

# S3 configuration (mirrors backup.sh)
AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-}"

# ─── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $*"; }
error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

# Download a file from S3 to a temp path and print the local path
download_from_s3() {
    local s3_uri="${1}"
    local tmp_file
    tmp_file="$(mktemp /tmp/restore_XXXXXXXXXX.$(basename "${s3_uri}"))"

    local aws_args=()
    if [[ -n "${AWS_ENDPOINT_URL}" ]]; then
        aws_args=(--endpoint-url "${AWS_ENDPOINT_URL}")
    fi

    log "Downloading ${s3_uri} → ${tmp_file}"
    aws "${aws_args[@]}" s3 cp "${s3_uri}" "${tmp_file}"
    log "S3 download complete"
    echo "${tmp_file}"
}

list_backups() {
    echo ""
    echo "Available PostgreSQL backups:"
    ls -lh "${BACKUP_DIR}/postgres/"*.gz 2>/dev/null || echo "  (none found)"
    echo ""
    echo "Available MongoDB backups:"
    ls -lh "${BACKUP_DIR}/mongodb/"*.gz 2>/dev/null || echo "  (none found)"
    echo ""
}

# ─── PostgreSQL restore ─────────────────────────────────────────────────────────
restore_postgres() {
    local backup_file="${1:-}"

    if [[ -z "${backup_file}" ]]; then
        list_backups
        read -r -p "Enter PostgreSQL backup file path: " backup_file
    fi

    if [[ ! -f "${backup_file}" ]]; then
        error "Backup file not found: ${backup_file}"
        exit 1
    fi

    log "Restoring PostgreSQL '${PG_DB}' from: ${backup_file}"
    log "WARNING: This will DROP and recreate the database '${PG_DB}'"
    read -r -p "Type 'yes' to confirm: " confirm
    [[ "${confirm}" != "yes" ]] && { log "Aborted."; exit 0; }

    # Drop and recreate the database
    PGPASSWORD="${PG_PASSWORD}" psql \
        --host="${PG_HOST}" \
        --port="${PG_PORT}" \
        --username="${PG_USER}" \
        --dbname="postgres" \
        -c "DROP DATABASE IF EXISTS ${PG_DB};" \
        -c "CREATE DATABASE ${PG_DB};"

    # Restore from backup (pg_restore reads custom format)
    zcat "${backup_file}" | PGPASSWORD="${PG_PASSWORD}" pg_restore \
        --host="${PG_HOST}" \
        --port="${PG_PORT}" \
        --username="${PG_USER}" \
        --dbname="${PG_DB}" \
        --no-owner \
        --no-acl \
        --verbose

    log "PostgreSQL restore complete."
}

# ─── MongoDB restore ────────────────────────────────────────────────────────────
restore_mongodb() {
    local backup_file="${1:-}"

    if [[ -z "${backup_file}" ]]; then
        list_backups
        read -r -p "Enter MongoDB backup archive path: " backup_file
    fi

    if [[ ! -f "${backup_file}" ]]; then
        error "Backup file not found: ${backup_file}"
        exit 1
    fi

    if ! command -v mongorestore &>/dev/null; then
        error "mongorestore not found. Install mongodb-database-tools."
        exit 1
    fi

    log "Restoring MongoDB '${MONGO_DB}' from: ${backup_file}"
    log "WARNING: This will DROP and recreate the database '${MONGO_DB}'"
    read -r -p "Type 'yes' to confirm: " confirm
    [[ "${confirm}" != "yes" ]] && { log "Aborted."; exit 0; }

    mongorestore \
        --host="${MONGO_HOST}" \
        --port="${MONGO_PORT}" \
        --db="${MONGO_DB}" \
        --archive="${backup_file}" \
        --gzip \
        --drop

    log "MongoDB restore complete."
}

# ─── Main ───────────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 <postgres|mongodb> [backup_file]"
    echo "       $0 <postgres|mongodb> --from-s3 <s3://bucket/key>"
    echo ""
    echo "Examples:"
    echo "  $0 postgres                                   # interactive: lists backups, prompts"
    echo "  $0 postgres backups/postgres/pg_data_pipeline_20260101_120000.sql.gz"
    echo "  $0 postgres --from-s3 s3://my-bucket/backups/postgres/pg_data_pipeline_20260101_120000.sql.gz"
    echo "  $0 mongodb"
    echo "  $0 mongodb backups/mongodb/mongo_data_zoo_20260101_120000.archive.gz"
    echo "  $0 mongodb --from-s3 s3://my-bucket/backups/mongodb/mongo_data_zoo_20260101_120000.archive.gz"
    echo ""
    echo "Environment:"
    echo "  AWS_ENDPOINT_URL  Set to http://localhost:4566 for Floci (default: real AWS)"
    exit 1
}

case "${1:-}" in
    postgres)
        if [[ "${2:-}" == "--from-s3" ]]; then
            [[ -z "${3:-}" ]] && { error "Missing S3 URI after --from-s3"; usage; }
            tmp=$(download_from_s3 "${3}")
            restore_postgres "${tmp}"
            rm -f "${tmp}"
        else
            restore_postgres "${2:-}"
        fi
        ;;
    mongodb)
        if [[ "${2:-}" == "--from-s3" ]]; then
            [[ -z "${3:-}" ]] && { error "Missing S3 URI after --from-s3"; usage; }
            tmp=$(download_from_s3 "${3}")
            restore_mongodb "${tmp}"
            rm -f "${tmp}"
        else
            restore_mongodb "${2:-}"
        fi
        ;;
    list)     list_backups ;;
    *)        usage ;;
esac
