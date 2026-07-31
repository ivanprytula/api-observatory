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

_cloud-sandbox-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    just floci-az-up
    docker compose up -d ingestor-db cache broker ingestor dashboard
    until docker compose exec -T ingestor-db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done

_db-get-token:
    #!/usr/bin/env bash
    set -euo pipefail
    API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
    TOKEN_URL="${API_BASE_URL%/}/api/v1/auth/token"
    for attempt in 1 2 3; do
        set +e
        HTTP_CODE=$(curl -s -o /tmp/get_token_body.$$ -w "%{http_code}" -X POST "$TOKEN_URL" -H 'Content-Type: application/x-www-form-urlencoded' -d 'username=admin&password=admin123')
        CURL_EXIT=$?
        BODY=$(cat /tmp/get_token_body.$$ 2>/dev/null || true)
        rm -f /tmp/get_token_body.$$
        set -e
        if [ "$CURL_EXIT" -eq 0 ] && [ "$HTTP_CODE" = "200" ] && [ -n "$BODY" ]; then
            TOKEN=$(printf '%s' "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || true)
            if [ -n "$TOKEN" ]; then printf '%s\n' "$TOKEN"; exit 0; fi
        fi
        sleep $((attempt * 2))
    done
    echo "ERROR: failed to obtain auth token after 3 attempts" >&2
    exit 1

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
    curl -sf -X POST "${API_BASE_URL}/api/v1/auth/register" -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123","email":"admin@example.com","role":"admin"}' >/dev/null 2>&1 || true
    TOKEN=$(just _db-get-token)
    BASE_URL="${API_BASE_URL}" bash .local-dev/scripts/seed-sources.sh "$TOKEN" .local-dev/payloads/source-*.json
    echo "auto-init complete — probe sources run every 10s"
