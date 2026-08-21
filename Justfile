
import? 'just/testing.just'
import? 'just/database-lifecycle.just'


help-core:
    @echo "Core: just doctor → cp .env.example .env → just generate-secrets → just dev-up → just db-migrate"
    @echo "Proof: just test-unit (isolated) | just test-smoke (running core stack) | just test-smoke-auth (authenticated API path)"
    @echo "Optional: just dev-up-inference (vector search) | just dev-up-cache | just dev-up-broker | just dev-up-extended (all three)"

# ─── 1. ENVIRONMENT CHECKS ───────────────────────────────────────────────────

db-inference-migrate:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! docker compose exec -T inference-db pg_isready -U postgres >/dev/null 2>&1; then
        echo "inference-db is not healthy. Start it with 'just dev-up-inference' or 'just dev-up-extended' first." >&2
        exit 1
    fi
    docker compose run --rm --no-deps inference alembic upgrade head

doctor:
    bash scripts/setup/03-verify-system-requirements.sh

generate-secrets:
    uv run python scripts/tools/generate-secrets.py

# ─── 2. LOCAL DEVELOPMENT ────────────────────────────────────────────────────

dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    export DATABASE_URL="postgresql+asyncpg://postgres:${INGESTOR_DB_PASSWORD}@127.0.0.1:5432/api_obs_ingestor"
    # Data-plane only — app services run locally with hot reload
    docker compose up -d ingestor-db cache
    docker compose stop ingestor dashboard >/dev/null 2>&1 || true
    docker compose rm -f ingestor dashboard >/dev/null 2>&1 || true
    until docker compose exec -T ingestor-db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just db-migrate
    # Streamlit hot-reloads .py files on save automatically
    # uv run streamlit run services/dashboard/ui/streamlit/app.py \
    #     --server.port=8501 --server.address=0.0.0.0 --server.headless=true \
    #     --server.fileWatcherType=auto &
    # DASHBOARD_PID=$!
    # trap "kill $DASHBOARD_PID 2>/dev/null || true" EXIT INT TERM
    # echo "dashboard  → http://localhost:8501  (pid $DASHBOARD_PID, hot-reload on)"
    # echo "ingestor   → http://localhost:8000  (uvicorn --reload)"
    # uv run uvicorn services.ingestor.main:app --port 8000 --reload --reload-dir services/ingestor

dev-up:
    docker compose up -d --build --wait --pull=always ingestor-db cache ingestor dashboard
    echo "stack ready — run 'just db-init' (migrate + seed admin) before using http://127.0.0.1:8000 or http://127.0.0.1:8501"

dev-up-cache:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${CACHE_ENABLED:-false}" != "true" ]]; then
        echo "Set CACHE_ENABLED=true in .env before starting Redis." >&2
        exit 1
    fi
    docker compose --profile cache up -d cache

dev-up-broker:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${BROKER_ENABLED:-false}" != "true" ]]; then
        echo "Set BROKER_ENABLED=true in .env before starting Redpanda." >&2
        exit 1
    fi
    docker compose --profile broker up -d broker

dev-up-inference:
    docker compose --profile inference up -d --build --pull --wait ingestor-db ingestor dashboard inference-db inference
    echo "inference stack ready — run 'just db-init' and 'just db-inference-migrate' before testing"

dev-up-extended:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${CACHE_ENABLED:-false}" != "true" ]]; then
        echo "Set CACHE_ENABLED=true in .env before starting the extended stack." >&2
        exit 1
    fi
    if [[ "${BROKER_ENABLED:-false}" != "true" ]]; then
        echo "Set BROKER_ENABLED=true in .env before starting the extended stack." >&2
        exit 1
    fi
    docker compose --profile cache --profile broker --profile inference up -d --build --pull --wait ingestor-db cache broker ingestor dashboard inference-db inference
    echo "extended stack ready — run 'just db-init' and 'just db-inference-migrate' before testing"

dev-up-monitoring:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${OTEL_ENABLED:-false}" != "true" ]]; then
        echo "Set OTEL_ENABLED=true in .env, then restart the application services before starting monitoring." >&2
        exit 1
    fi
    docker compose --profile monitoring up -d prometheus grafana loki promtail tempo alertmanager mailpit
    echo "monitoring ready — Grafana http://127.0.0.1:3000, Prometheus http://127.0.0.1:9090, Tempo http://127.0.0.1:3200"

dev-up-ingress-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="{{justfile_directory()}}"
    CERT_DIR="${PROJECT_ROOT}/infra/certs"
    if [[ ! -f "${PROJECT_ROOT}/.env" ]] || ! grep -Eq '^LOCAL_HTTPS=true([[:space:]]*)$' "${PROJECT_ROOT}/.env"; then
        echo "Set LOCAL_HTTPS=true in .env before enabling local HTTPS." >&2
    if ! command -v mkcert >/dev/null 2>&1; then
        echo "mkcert not found. Install: brew install mkcert / sudo apt-get install mkcert / sudo dnf install mkcert" >&2
        exit 1
    fi
    if [[ -f "${CERT_DIR}/localhost+2.pem" && -f "${CERT_DIR}/localhost+2-key.pem" ]]; then
        read -r -p "Certificates already exist at ${CERT_DIR}. Regenerate? (y/n) " -n 1 response
        echo
        if [[ "${response}" != "y" && "${response}" != "Y" ]]; then
            echo "Using existing certificates."
            exit 0
        fi
        rm -f "${CERT_DIR}/localhost+2.pem" "${CERT_DIR}/localhost+2-key.pem"
    fi
    mkdir -p "${CERT_DIR}"
    mkcert -install
    (cd "${CERT_DIR}" && mkcert localhost 127.0.0.1 "*.local")
    echo "Certificates generated:"
    echo "  ${CERT_DIR}/localhost+2.pem"
    echo "  ${CERT_DIR}/localhost+2-key.pem"
    echo "Next: docker compose --profile ingress up -d --build"

update-base-image-digest:
    bash scripts/update-base-image-digest.sh

mcp-register-user:
    #!/usr/bin/env bash
    set -euo pipefail
    : "${MCP_SERVICE_PASSWORD:?Set MCP_SERVICE_PASSWORD}"
    uv run python scripts/register_mcp_service_user.py --password "${MCP_SERVICE_PASSWORD}"
