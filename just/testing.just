# Test recipes. Unit tests need no runtime stack. PostgreSQL integration tests use
# testcontainers when Docker is available; smoke, API, and E2E tests use the local stack.

test-smoke base-url="http://127.0.0.1:8000" dashboard-url="http://127.0.0.1:8501":
    bash scripts/smoke-test.sh {{base-url}} {{dashboard-url}}

test-unit:
    cd "{{justfile_directory()}}" && uv run pytest tests/unit services/ingestor/tests/unit -m unit -q

test-integration:
    uv run pytest -m integration -q

test-e2e:
    uv run pytest -m e2e -q

# Manual API collection workflow. It does not reset or seed the local database.
# Prepare a disposable demo explicitly with `just db-reset --confirm DELETE` and `just db-auto-init` when needed.
test-api:
    cd bruno && bru run auth ops sources contracts scorecards websocket -r --env local --env-var "baseUrl=${BRUNO_BASE_URL:-http://127.0.0.1:8000}"

test-load:
    #!/usr/bin/env bash
    set -euo pipefail
    BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
    VUS="${VUS:-5}"
    DURATION="${DURATION:-90s}"
    echo "Running k6 — BASE_URL=${BASE_URL}, VUS=${VUS}, DURATION=${DURATION}"
    k6 run --vus "${VUS}" --duration "${DURATION}" \
      --env "BASE_URL=${BASE_URL}" --env "BEARER_TOKEN=${BEARER_TOKEN:-}" \
      scripts/load/k6-observations-load.js

test-chaos:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Chaos tests mutate running containers. Ensure stack is healthy first."
    uv run pytest tests/e2e/test_chaos.py -v --no-cov --run-chaos
