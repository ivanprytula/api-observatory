# Database lifecycle and optional demo initialization.

# Destructive demo reset; invoke only as `just db-reset --confirm DELETE`.
# Never use after recording real observations or API sources.
# For retained data, run and verify `bash infra/scripts/backup.sh` before any reset.
db-reset confirmation_flag="" confirmation="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{confirmation_flag}}" != "--confirm" || "{{confirmation}}" != "DELETE" ]]; then
        echo "Refusing destructive reset. Re-run with: just db-reset --confirm DELETE" >&2
        exit 2
    fi
    docker compose rm -sfv ingestor ingestor-db || true
    docker volume rm -f api-obs-ingestor-postgres-data api-observatory_ingestor_postgres_data || true
    docker compose up -d --build ingestor-db ingestor dashboard
    echo "stack reset — run 'just dev-wait-ready' before using it"

db-migrate:
    docker compose run --rm --no-deps ingestor alembic upgrade head

_cloud-sandbox-seed:
    #!/usr/bin/env bash
    set -euo pipefail
    until curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; do sleep 1; done
    just db-auto-init

db-auto-init:
    #!/usr/bin/env bash
    set -euo pipefail
    API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
    API_BASE_URL="${API_BASE_URL%/}"
    if ! curl -fsS "${API_BASE_URL}/readyz" > /dev/null; then
        echo "API is not ready at ${API_BASE_URL}. Run 'just dev-wait-ready' first." >&2
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
    INTERNAL_TOKEN="$(just db-internal-token)"
    cd "${PROJECT_ROOT}/bruno" && bru run demo -r --env local-dev --env-var "baseUrl=${API_BASE_URL}" --env-var "internal_token=${INTERNAL_TOKEN}"
    echo "auto-init complete — admin/admin123 is a real admin; probe sources run every 10s"

# Print a short-lived internal service JWT (60s TTL) for pasting into the
# Bruno `internal_token` env var or the SwaggerUI Authorize dialog.
db-internal-token:
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
    if [[ -z "${API_OBS_INTERNAL_JWT_SECRET:-}" ]]; then
        echo "internal-token: API_OBS_INTERNAL_JWT_SECRET is empty in .env" >&2
        exit 1
    fi
    cd "${PROJECT_ROOT}" && INTERNAL_JWT_SECRET="${API_OBS_INTERNAL_JWT_SECRET}" uv run python -c 'from libs.platform.auth import generate_internal_token; print(generate_internal_token("local-dev-seed"))'
