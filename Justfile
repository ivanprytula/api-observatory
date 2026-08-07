# Core command order follows the README/setup flow:
#   just doctor → cp .env.example .env → just generate-secrets → just dev-up
#   → just db-migrate → just test-smoke
# Optional local paths: just db-auto-init, just dev-up-cache, just dev-up-broker,
# just dev-up-inference, just dev-up-extended, and just dev-up-monitoring.
# Core test and database-lifecycle commands live in the imported files below.

import? 'just/testing.just'
import? 'just/database-lifecycle.just'

# Focused command map for a first task; run `just --list` only when exploring a specialist area.
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

# Generate or rotate local prod-like credentials in the existing private .env.
generate-secrets:
    uv run python scripts/tools/generate-secrets.py

# ─── 2. LOCAL DEVELOPMENT ────────────────────────────────────────────────────
#
# Primary local loops:
#   just dev-up → Docker PostgreSQL + application
#   just dev    → optional host-process hot reload
# Optional host-process hot reload (Docker-first `just dev-up` remains canonical).
# ─────────────────────────────────────────────

# Run ingestor and dashboard locally with hot reload; Docker PostgreSQL remains required.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    export DATABASE_URL="postgresql+asyncpg://postgres:${API_OBS_INGESTOR_DB_PASSWORD}@127.0.0.1:5432/api_obs_ingestor"
    export CACHE_URL="redis://:${API_OBS_CACHE_PASSWORD}@127.0.0.1:6379/0"
    export CACHE_ENABLED="${API_OBS_CACHE_ENABLED:-false}"
    export BROKER_ENABLED="${API_OBS_BROKER_ENABLED:-false}"
    export OTEL_ENABLED="${API_OBS_OTEL_ENABLED:-false}"
    export OPENAI_ENABLED="${API_OBS_OPENAI_ENABLED:-false}"
    export ANTHROPIC_ENABLED="${API_OBS_ANTHROPIC_ENABLED:-false}"
    export API_V1_BEARER_TOKEN="${API_OBS_API_V1_BEARER_TOKEN}"
    export JWT_SECRET="${API_OBS_JWT_SECRET}"
    export INTERNAL_JWT_SECRET="${API_OBS_INTERNAL_JWT_SECRET}"
    # Data-plane only — app services run locally with hot reload
    docker compose up -d ingestor-db
    docker compose stop ingestor dashboard >/dev/null 2>&1 || true
    docker compose rm -f ingestor dashboard >/dev/null 2>&1 || true
    until docker compose exec -T ingestor-db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    # Streamlit hot-reloads .py files on save automatically
    uv run streamlit run services/dashboard/ui/streamlit/app.py \
        --server.port=8501 --server.address=0.0.0.0 --server.headless=true \
        --server.fileWatcherType=auto &
    DASHBOARD_PID=$!
    trap "kill $DASHBOARD_PID 2>/dev/null || true" EXIT INT TERM
    echo "dashboard  → http://localhost:8501  (pid $DASHBOARD_PID, hot-reload on)"
    echo "ingestor   → http://localhost:8000  (uvicorn --reload)"
    uv run uvicorn services.ingestor.main:app --port 8000 --reload --reload-dir services/ingestor

# Official Docker-first HTTP workflow.
# ─────────────────────────────────────────────────────────

# Start the default containerized HTTP stack; enable the optional `ingress` profile separately for HTTPS.
dev-up:
    docker compose up -d --build --wait ingestor-db ingestor dashboard
    echo "stack ready — run 'just db-migrate' before using http://127.0.0.1:8000 or http://127.0.0.1:8501"

# Enable Redis explicitly after setting API_OBS_CACHE_ENABLED=true in .env.
dev-up-cache:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${API_OBS_CACHE_ENABLED:-false}" != "true" ]]; then
        echo "Set API_OBS_CACHE_ENABLED=true in .env before starting Redis." >&2
        exit 1
    fi
    docker compose --profile cache up -d cache

# Enable Redpanda explicitly after setting API_OBS_BROKER_ENABLED=true in .env.
dev-up-broker:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${API_OBS_BROKER_ENABLED:-false}" != "true" ]]; then
        echo "Set API_OBS_BROKER_ENABLED=true in .env before starting Redpanda." >&2
        exit 1
    fi
    docker compose --profile broker up -d broker

# Start the core stack plus inference and its dedicated database for vector-search work.
dev-up-inference:
    docker compose --profile inference up -d --build --wait ingestor-db ingestor dashboard inference-db inference
    echo "inference stack ready — run 'just db-migrate' and 'just db-inference-migrate' before testing"

# Start cache, broker, and inference together only for a full optional-integration task.
dev-up-extended:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${API_OBS_CACHE_ENABLED:-false}" != "true" ]]; then
        echo "Set API_OBS_CACHE_ENABLED=true in .env before starting the extended stack." >&2
        exit 1
    fi
    if [[ "${API_OBS_BROKER_ENABLED:-false}" != "true" ]]; then
        echo "Set API_OBS_BROKER_ENABLED=true in .env before starting the extended stack." >&2
        exit 1
    fi
    docker compose --profile cache --profile broker --profile inference up -d --build --wait ingestor-db cache broker ingestor dashboard inference-db inference
    echo "extended stack ready — run 'just db-migrate' and 'just db-inference-migrate' before testing"

# Start monitoring stack (Prometheus, Grafana, Loki, Promtail, Tempo, Alertmanager, Mailpit).
dev-up-monitoring:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; source "${PWD}/.env"; set +a
    if [[ "${API_OBS_OTEL_ENABLED:-false}" != "true" ]]; then
        echo "Set API_OBS_OTEL_ENABLED=true in .env, then restart the application services before starting monitoring." >&2
        exit 1
    fi
    docker compose --profile monitoring up -d prometheus grafana loki promtail tempo alertmanager mailpit
    echo "monitoring ready — Grafana http://127.0.0.1:3000, Prometheus http://127.0.0.1:9090, Tempo http://127.0.0.1:3200"
