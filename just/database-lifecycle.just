# Database lifecycle and optional demo initialization.

# Destructively reset the demo stack; invoke only as `just db-reset --confirm DELETE`.
db-reset confirmation_flag="" confirmation="":
    #!/usr/bin/env bash
    set -euo pipefail
    # For retained data, run and verify `just db-backup` before any reset.
    if [[ "{{confirmation_flag}}" != "--confirm" || "{{confirmation}}" != "DELETE" ]]; then
        echo "Refusing destructive reset. Re-run with: just db-reset --confirm DELETE" >&2
        exit 2
    fi
    docker compose rm -sfv ingestor ingestor-db cache || true
    docker volume rm -f api-obs-ingestor-postgres-data api-observatory_ingestor_postgres_data || true
    docker compose up -d --build --wait ingestor-db cache ingestor dashboard
    echo "stack reset and ready — run 'just db-init' (migrate + seed admin) before using it"

db-migrate:
    docker compose run --rm --no-deps ingestor alembic upgrade head

# Seed the initial admin + global superadmin (idempotent; no-op if credentials
# are unset). Decoupled from app startup — run after `db-migrate`. See
# scripts/seed_admin.py.
seed-admin:
    docker compose run --rm --no-deps ingestor python scripts/seed_admin.py

# Ordered pre-serving init: apply schema migrations, then seed admin accounts.
# Chained so seed never runs against a pre-migration (empty) schema.
db-init: db-migrate seed-admin

db-backup:
    bash infra/scripts/backup.sh

# Retention management (see docs/02-architecture/engineering-topics.md).
retention-dry-run:
    uv run python scripts/run-retention.py --dry-run

retention-apply:
    uv run python scripts/run-retention.py --apply

db-auto-init:
    #!/usr/bin/env bash
    set -euo pipefail
    API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
    API_BASE_URL="${API_BASE_URL%/}"
    if ! curl -fsS "${API_BASE_URL}/readyz" > /dev/null; then
        echo "API is not ready at ${API_BASE_URL}. Start it with 'just dev-up' first." >&2
        exit 1
    fi
    if ! docker compose run --rm --no-deps ingestor alembic current --check-heads > /dev/null; then
        echo "Database migrations are not current. Run 'just db-migrate' first." >&2
        exit 1
    fi
    PROJECT_ROOT="{{justfile_directory()}}"
    if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
        echo "auto-init: ${PROJECT_ROOT}/.env not found — run 'just generate-secrets' first" >&2
        exit 1
    fi
    INTERNAL_TOKEN="$(just --justfile "${PROJECT_ROOT}/Justfile" _dev-internal-token local-dev-seed)"
    cd "${PROJECT_ROOT}/bruno" && bru run demo -r --env local-dev --env-var "baseUrl=${API_BASE_URL}" --env-var "internal_token=${INTERNAL_TOKEN}"
    echo "auto-init complete — admin/admin123 is a real admin; probe sources run every 10s"

# Private helper for local automation that calls internal-only service endpoints.
# This token is not a user JWT and must not be used in Swagger's Authorize dialog.
_dev-internal-token service_name="local-dev":
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="{{justfile_directory()}}"
    if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
        echo "internal-token: ${PROJECT_ROOT}/.env not found — run 'just generate-secrets' first" >&2
        exit 1
    fi
    set -a
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env"
    set +a
    if [[ -z "${INTERNAL_JWT_SECRET:-}" ]]; then
        echo "internal-token: INTERNAL_JWT_SECRET is empty in .env" >&2
        exit 1
    fi
    cd "${PROJECT_ROOT}" && INTERNAL_JWT_SECRET="${INTERNAL_JWT_SECRET}" uv run python -c 'from libs.platform.auth import generate_internal_token; import sys; print(generate_internal_token(sys.argv[1]))' "{{service_name}}"
