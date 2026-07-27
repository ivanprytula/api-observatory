# ─── DOCTOR / INIT CHECKS ────────────────────────────────────────────────────

# Containerized workflows always wait on the direct ingestor readiness endpoint.
_wait_ready:
    @until curl -fsS http://127.0.0.1:8000/readyz >/dev/null 2>&1; do sleep 1; done

doctor:
    bash scripts/setup/00-doctor.sh

# Recreate .venv with the latest Python 3.14 using uv.
# Steps: update .python-version → remove old .venv → create → sync → verify.
bootstrap-venv:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== bootstrap-venv ==="
    echo "1/6  Checking uv…"
    command -v uv >/dev/null || { echo "uv not found — install it first"; exit 1; }
    echo "2/6  Setting .python-version to 3.14.6…"
    echo "3.14.6" > .python-version
    echo "3/6  Removing old .venv…"
    rm -rf .venv
    echo "4/6  Creating venv with Python 3.14.6…"
    uv venv --python 3.14.6
    echo "5/6  Syncing dependencies…"
    uv sync
    echo "6/6  Verifying…"
    uv run python --version
    echo "=== done ==="

# Check docs for stale Justfile recipe references.
docs-check-just-refs:
    bash scripts/docs/check-just-refs.sh

# Generate or rotate local prod-like credentials in the existing private .env.
generate-secrets:
    uv run python scripts/tools/generate-secrets.py



# ─── DAILY DEV FLOWS ─────────────────────────────────────────────────────────
#
# Primary loops:
#   just dev                        → uvicorn + Compose data-plane (local)
#   just up                         → Compose data-plane only (containerized)
#   CLOUD=azure just sandbox-up     → Azure emulator (floci-az)
#   CLOUD=aws   just sandbox-up     → AWS emulator (floci-aws)
#   CLOUD=gcp   just sandbox-up     → GCP emulator (floci-gcp)
#   CLOUD=aws   just sandbox-dev    → hot-reload dev against emulator
#   TF_ENV=aws-sandbox just tf plan → Terraform against emulator
#
# Emulators start only when you explicitly need cloud-shaped APIs.

# 2a) Local development (uvicorn + live reload)
# ─────────────────────────────────────────────

# Start both ingestor (uvicorn --reload) and dashboard (Streamlit hot-reload) locally.
# Data-plane (db, cache, broker) runs in Compose; both app services reload on file save.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    # Data-plane only — app services run locally with hot reload
    docker compose up -d db cache broker
    docker compose stop ingestor dashboard >/dev/null 2>&1 || true
    docker compose rm -f ingestor dashboard >/dev/null 2>&1 || true
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    # Streamlit hot-reloads .py files on save automatically
    uv run streamlit run services/dashboard/ui/streamlit/app.py \
        --server.port=8501 --server.address=0.0.0.0 --server.headless=true \
        --server.fileWatcherType=auto &
    DASHBOARD_PID=$!
    trap "kill $DASHBOARD_PID 2>/dev/null || true" EXIT INT TERM
    echo "dashboard  → http://localhost:8501  (pid $DASHBOARD_PID, hot-reload on)"
    echo "ingestor   → http://localhost:8000  (uvicorn --reload)"
    uv run uvicorn services.ingestor.main:app --port 8000 --reload --reload-dir services/ingestor

# 2b) Containerized development (Compose data-plane only)
# ─────────────────────────────────────────────────────────

# Start containerized fleet with HTTPS ingress (prod-parity).
up:
    docker compose up -d --build db cache broker ingestor dashboard edge
    just _wait_ready
    echo "stack ready — https://127.0.0.1 (edge)"


# Start full stack with hot-reload via Compose Watch + uvicorn/streamlit reload.
# First builds and starts everything, then watches only the app services.
# Source code is synced into containers (ignoring __pycache__/).
# uvicorn --reload / Streamlit poll watcher restart the process on file change.
# Dependency file changes (pyproject.toml, uv.lock) trigger a full image rebuild.
watch:
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build db cache broker ingestor dashboard
    just _wait_ready
    echo ""
    echo "Watching for file changes — Compose Watch syncs code into containers."
    echo "Stop with Ctrl+C.  Containers keep running in the background."
    echo ""
    docker compose -f docker-compose.yml -f docker-compose.dev.yml watch ingestor dashboard

# Start monitoring stack (Prometheus, Grafana, Loki, Promtail, Tempo, Alertmanager, Mailpit).
up-monitoring:
    docker compose --profile monitoring up -d prometheus grafana loki promtail tempo alertmanager mailpit
    echo "monitoring ready — Grafana http://127.0.0.1:3000, Prometheus http://127.0.0.1:9090, Tempo http://127.0.0.1:3200"



# Start the full stack: data-plane + monitoring. Combines `up` and `up-monitoring`.
up-all: up up-monitoring


# Reset DB and ingestor containers (keep Floci state intact if running).
db-reset:
    docker compose rm -sfv ingestor db || true
    docker compose up -d --build db cache broker ingestor dashboard edge
    just _wait_ready
    echo "stack ready"


# 2c) Sandbox / emulator-backed development
# ─────────────────────────────────────


# ─── CLOUD SANDBOXES (local Floci emulators — $0, no credentials) ────────────
#
# All sandboxes use Floci (wire-compatible with real cloud SDKs/CLIs).
# Switch clouds with CLOUD env var — one set of recipes, three clouds.
#
# Usage:
#   CLOUD=azure just sandbox-up        # start floci-az + data plane (default)
#   CLOUD=aws   just sandbox-up        # start floci-aws + data plane
#   CLOUD=gcp   just sandbox-up        # start floci-gcp + data plane
#   CLOUD=aws   just sandbox-dev       # hot-reload dev against AWS emulator
#   CLOUD=gcp   just sandbox-validate  # health check before promoting to cloud
#   TF_ENV=aws-sandbox just tf plan    # Terraform against emulator
#
# Cloud config table:
#   CLOUD    profile   container          port   TF_ENV
#   azure    azure     api-obs-floci-az   4577   azure-sandbox
#   aws      aws       api-obs-floci-aws  4566   aws-sandbox
#   gcp      gcp       api-obs-floci-gcp  4588   gcp-sandbox

# Start Floci emulator + data-plane services, run migrations.
sandbox-up:
    #!/usr/bin/env bash
    set -euo pipefail
    CLOUD="${CLOUD:-azure}"
    case "$CLOUD" in
        azure) PROFILE=azure; SERVICE=floci-az;  PORT=4577 ;;
        aws)   PROFILE=aws;   SERVICE=floci-aws; PORT=4566 ;;
        gcp)   PROFILE=gcp;   SERVICE=floci-gcp; PORT=4588 ;;
        *)     echo "FAIL: Unknown CLOUD=${CLOUD}. Use: azure, aws, gcp" >&2; exit 1 ;;
    esac
    docker compose --profile "$PROFILE" up -d "$SERVICE"
    echo "  Waiting for ${SERVICE} health on port ${PORT}..."
    for i in $(seq 1 60); do
        if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then break; fi
        sleep 1
    done
    curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1 || { echo "FAIL: ${SERVICE} not healthy after 60s"; exit 1; }
    echo "  [ok] ${SERVICE} healthy"
    docker compose up -d --build db cache broker ingestor dashboard edge
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    just _sandbox-seed

# Stop Floci emulator only (Compose data-plane keeps running).
sandbox-down:
    #!/usr/bin/env bash
    set -euo pipefail
    CLOUD="${CLOUD:-azure}"
    case "$CLOUD" in
        azure) docker compose --profile azure down floci-az  ;;
        aws)   docker compose --profile aws   down floci-aws ;;
        gcp)   docker compose --profile gcp   down floci-gcp ;;
        *)     echo "FAIL: Unknown CLOUD=${CLOUD}. Use: azure, aws, gcp" >&2; exit 1 ;;
    esac

# Start local dev with hot reload against a Floci emulator.
sandbox-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    CLOUD="${CLOUD:-azure}"
    case "$CLOUD" in
        azure)
            export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:4577/devstoreaccount1"
            export AZURE_ENDPOINT_URL="http://127.0.0.1:4577"
            EMULATOR_LABEL="floci-az   → http://localhost:4577  (Azure emulator)"
            ;;
        aws)
            export AWS_ENDPOINT_URL="http://127.0.0.1:4566"
            export AWS_ACCESS_KEY_ID="test"
            export AWS_SECRET_ACCESS_KEY="test"
            export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-central-1}"
            EMULATOR_LABEL="floci-aws  → http://localhost:4566  (AWS emulator)"
            ;;
        gcp)
            export STORAGE_EMULATOR_HOST="http://127.0.0.1:4588"
            export PUBSUB_EMULATOR_HOST="127.0.0.1:4588"
            export FIRESTORE_EMULATOR_HOST="127.0.0.1:4588"
            export DATASTORE_EMULATOR_HOST="127.0.0.1:4588"
            export SECRET_MANAGER_EMULATOR_HOST="127.0.0.1:4588"
            export CLOUDSDK_CORE_PROJECT="${GCP_PROJECT_ID:-floci-local}"
            EMULATOR_LABEL="floci-gcp  → http://localhost:4588  (GCP emulator)"
            ;;
        *)  echo "FAIL: Unknown CLOUD=${CLOUD}. Use: azure, aws, gcp" >&2; exit 1 ;;
    esac
    docker compose up -d db cache broker
    docker compose stop ingestor dashboard >/dev/null 2>&1 || true
    docker compose rm -f ingestor dashboard >/dev/null 2>&1 || true
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    uv run streamlit run services/dashboard/ui/streamlit/app.py \
        --server.port=8501 --server.address=0.0.0.0 --server.headless=true \
        --server.fileWatcherType=auto &
    DASHBOARD_PID=$!
    trap "kill $DASHBOARD_PID 2>/dev/null || true" EXIT INT TERM
    echo "dashboard  → http://localhost:8501  (pid $DASHBOARD_PID, hot-reload on)"
    echo "ingestor   → http://localhost:8000  (uvicorn --reload)"
    echo "${EMULATOR_LABEL}"
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# Validate Floci sandbox health before promoting to real cloud.
sandbox-validate:
    #!/usr/bin/env bash
    set -euo pipefail
    CLOUD="${CLOUD:-azure}"
    case "$CLOUD" in
        azure) CONTAINER=api-obs-floci-az;  PORT=4577 ;;
        aws)   CONTAINER=api-obs-floci-aws; PORT=4566 ;;
        gcp)   CONTAINER=api-obs-floci-gcp; PORT=4588 ;;
        *)     echo "FAIL: Unknown CLOUD=${CLOUD}. Use: azure, aws, gcp" >&2; exit 1 ;;
    esac
    echo "=== Sandbox validation (${CLOUD}) ==="
    if ! docker ps --filter "name=${CONTAINER}" --filter 'status=running' --format '{{{{.Names}}}}' | grep -q .; then
        echo "FAIL: ${CONTAINER} is not running." >&2
        echo "  Start it with: CLOUD=${CLOUD} just sandbox-up" >&2
        exit 1
    fi
    echo "  [ok] ${CONTAINER} running"
    if ! curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
        echo "FAIL: Health endpoint not responding at http://127.0.0.1:${PORT}/health" >&2
        exit 1
    fi
    echo "  [ok] Health endpoint OK"
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  [ok] Application API /health OK"
    else
        echo "  [warn] Application API not responding — Compose stack may not be running."
    fi
    echo "=== Sandbox validated (${CLOUD}) ==="

# Confirm real cloud credentials are in place before promoting from sandbox.
cloud-preflight:
    #!/usr/bin/env bash
    set -euo pipefail
    CLOUD="${CLOUD:-azure}"
    echo "=== ${CLOUD} preflight ==="
    case "$CLOUD" in
        azure)
            command -v az &>/dev/null || { echo "FAIL: Azure CLI not found. Install: https://aka.ms/installazurecli" >&2; exit 1; }
            echo "  [ok] Azure CLI installed"
            az account show > /dev/null 2>&1 || { echo "FAIL: Not logged in. Run: az login" >&2; exit 1; }
            echo "  [ok] Azure account: $(az account show --query name -o tsv)"
            ;;
        aws)
            command -v aws &>/dev/null || { echo "FAIL: AWS CLI not found." >&2; exit 1; }
            echo "  [ok] AWS CLI installed"
            aws sts get-caller-identity > /dev/null 2>&1 || { echo "FAIL: No valid AWS credentials. Run: aws configure" >&2; exit 1; }
            echo "  [ok] AWS account: $(aws sts get-caller-identity --query Account --output text)"
            ;;
        gcp)
            command -v gcloud &>/dev/null || { echo "FAIL: gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install" >&2; exit 1; }
            echo "  [ok] gcloud CLI installed"
            gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q . || { echo "FAIL: Not logged in. Run: gcloud auth login" >&2; exit 1; }
            echo "  [ok] GCP account: $(gcloud config get-value account 2>/dev/null)"
            echo "  [ok] GCP project: $(gcloud config get-value project 2>/dev/null)"
            ;;
        *)  echo "FAIL: Unknown CLOUD=${CLOUD}. Use: azure, aws, gcp" >&2; exit 1 ;;
    esac
    echo "=== ${CLOUD} preflight passed ==="


# ─── STACK AWARENESS ──────────────────────────────────────────────────────────

# Print the active stack configuration based on environment variables and Docker state.
stack-info:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="$(pwd)"
    set -a; source "${PROJECT_ROOT}/.env"; set +a
    TF="${TF_ENV:-azure-sandbox}"
    if [ -n "${STORAGE_EMULATOR_HOST:-}" ]; then
        CLOUD="Floci-gcp (${STORAGE_EMULATOR_HOST})"
    elif [ -n "${AWS_ENDPOINT_URL:-}" ]; then
        CLOUD="Floci-aws (${AWS_ENDPOINT_URL})"
    elif [ -n "${AZURE_ENDPOINT_URL:-}" ]; then
        CLOUD="Floci-az (${AZURE_ENDPOINT_URL})"
    elif gcloud config get-value project > /dev/null 2>&1 && [ -n "$(gcloud config get-value project 2>/dev/null)" ]; then
        CLOUD="GCP ($(gcloud config get-value project 2>/dev/null))"
    elif aws sts get-caller-identity > /dev/null 2>&1; then
        CLOUD="AWS ($(aws sts get-caller-identity --query Account --output text 2>/dev/null))"
    elif az account show > /dev/null 2>&1; then
        CLOUD="Azure ($(az account show --query name -o tsv 2>/dev/null))"
    else
        CLOUD="Local-Docker"
    fi
    if docker compose ps db >/dev/null 2>&1 && docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1; then
        DB="Local-Compose-Postgres"
    elif [ -n "${DATABASE_URL:-}" ]; then
        DB="External (host=$(echo "$DATABASE_URL" | sed -E 's|.*@([^/:]+).*|\1|'))"
    else
        DB="unknown"
    fi
    if [ -n "${CACHE_URL:-}" ]; then
        CACHE="$(echo "$CACHE_URL" | sed -E 's|.*://([^/]+).*|\1|')"
    else
        CACHE="unset"
    fi
    echo "=== STACK SUMMARY ==="
    echo "  Cloud backend   : ${CLOUD}"
    echo "  Terraform env   : ${TF}"
    echo "  Postgres        : ${DB}"
    echo "  Cache           : ${CACHE}"
    echo "  Event broker    : ${BROKER_URL:-unset}"
    echo "  INGESTOR_URL    : ${API_BASE_URL:-http://127.0.0.1:8000}"
    echo "======================"



# ─── INFRASTRUCTURE & IMAGES ──────────────────────────────────────────────────
#
# 3a) Terraform (unified — environment via TF_ENV)
# 3b) CVE scan

# 3a) Terraform
# ───────────────

# Sandbox environments (emulators, $0):
#   just tf init                          # defaults to azure-sandbox (floci-az)
#   TF_ENV=aws-sandbox just tf init       # AWS sandbox (floci-aws)
#   TF_ENV=gcp-sandbox just tf init       # GCP sandbox (floci-gcp)
#
# Cloud environments (real infra — see api-observatory-infra repo):
#   TF_ENV=azure-dev just tf plan
#   TF_ENV=aws-dev just tf plan

# Unified Terraform runner — resolves environment from TF_ENV.
tf cmd:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-azure-sandbox}"
    CMD="{{cmd}}"
    DIR="infra/terraform/environments/${ENV}"
    if [ ! -d "$DIR" ]; then
        echo "FAIL: Terraform environment directory not found: ${DIR}" >&2
        echo "  Available: $(ls infra/terraform/environments/)" >&2
        exit 1
    fi
    cd "$DIR"

    case "$CMD" in
        init)
            BACKEND_CFG=$(ls backend.*.hcl 2>/dev/null | head -1)
            if [ -n "${BACKEND_CFG:-}" ]; then
                terraform init -reconfigure -upgrade -backend-config="$BACKEND_CFG"
            else
                terraform init -reconfigure -upgrade
            fi
            ;;
        validate)
            terraform validate
            ;;
        plan)
            export TF_IN_AUTOMATION=1
            terraform plan \
                -input=false \
                -var-file=terraform.tfvars \
                -out=tfplan
            ;;
        apply)
            terraform apply tfplan
            ;;
        show)
            terraform show
            ;;
        destroy)
            terraform destroy \
                -auto-approve \
                -var-file=terraform.tfvars
            ;;
        fresh)
            just tf init
            just tf plan
            just tf apply
            ;;
        *)
            echo "Usage: just tf <init|validate|plan|apply|show|destroy|fresh>"; exit 1
            ;;
    esac

# Destroy Terraform-managed resources with confirmation prompt.
tf-destroy:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-azure-sandbox}"
    EXPECTED="yes-i-really-want-to-destroy-${ENV}"
    read -r -p "DANGER: Type '${EXPECTED}' to destroy ${ENV} infra: " CONFIRM
    if [ "$CONFIRM" != "$EXPECTED" ]; then
        echo "Aborted."
        exit 1
    fi
    just tf destroy



# ─── TERRAVISION (architecture diagrams from IaC) ──────────────────────────────
#
# Generate professional cloud architecture diagrams from Terraform code.
# Install: `uv pip install terravision`
# Docs: https://patrickchugh.github.io/terravision
#
# Usage:
#   just tf-diagram               # PNG by default
#   just tf-diagram svg           # SVG output
#   just tf-diagram png           # PNG output
#   just tf-diagram html          # Interactive HTML output

# Render Terraform architecture diagrams with Terravision.
tf-diagram format="png":
    #!/usr/bin/env bash
    set -euo pipefail
    FORMAT="${format:-png}"
    ENV="${TF_ENV:-azure-sandbox}"
    PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
    LOCAL_DEV="$PROJECT_ROOT/.local-dev"
    DIR="$PROJECT_ROOT/infra/terraform/environments/${ENV}"
    mkdir -p "$LOCAL_DEV/diagrams"
    OUTFILE="$LOCAL_DEV/diagrams/data-zoo-${ENV}"
    PLANFILE="$LOCAL_DEV/tfplan-${ENV}.json"
    GRAPHFILE="$LOCAL_DEV/graph-${ENV}.dot"
    USE_PLAN=false
    if [ -f "$PLANFILE" ] && [ -f "$GRAPHFILE" ]; then
        USE_PLAN=true
    fi
    if [ "$USE_PLAN" = "true" ]; then
        if [ "$FORMAT" = "html" ] || [ "$FORMAT" = "interactive" ]; then
            uv run terravision visualise --planfile "$PLANFILE" --graphfile "$GRAPHFILE" --source "$DIR" --outfile "$OUTFILE"
            echo "Interactive HTML diagram written to ${OUTFILE}.html"
        else
            uv run terravision draw --planfile "$PLANFILE" --graphfile "$GRAPHFILE" --source "$DIR" --format "$FORMAT" --outfile "$OUTFILE"
            echo "Diagram written to ${OUTFILE}.${FORMAT}"
        fi
    else
        if [ "$FORMAT" = "html" ] || [ "$FORMAT" = "interactive" ]; then
            set +e
            uv run terravision visualise --source "$DIR" --outfile "$OUTFILE"
            EXIT_CODE=$?
            set -e
            if [ $EXIT_CODE -ne 0 ]; then
                echo "HCL parsing may fail on complex for loops. Try: terraform show -json tfplan > \"$LOCAL_DEV/tfplan-${ENV}.json\" && just tf-diagram html" >&2
                exit $EXIT_CODE
            fi
            echo "Interactive HTML diagram written to ${OUTFILE}.html"
        else
            set +e
            uv run terravision draw --source "$DIR" --format "$FORMAT" --outfile "$OUTFILE"
            EXIT_CODE=$?
            set -e
            if [ $EXIT_CODE -ne 0 ]; then
                echo "HCL parsing may fail on complex for loops. Try: terraform show -json tfplan > \"$LOCAL_DEV/tfplan-${ENV}.json\" && just tf-diagram ${FORMAT}" >&2
                exit $EXIT_CODE
            fi
            echo "Diagram written to ${OUTFILE}.${FORMAT}"
        fi
    fi





# Scan an image for CRITICAL vulnerabilities.
docker-scan-image image="api-observatory:local":
    docker compose --profile security run --rm trivy image \
        --scanners vuln \
        --severity CRITICAL \
        --ignore-unfixed \
        --timeout 15m \
        --exit-code 1 \
        {{image}}
    echo "No CRITICAL CVEs detected"


# Scan repo or staged changes for leaked secrets with Gitleaks (Docker).
# Usage:
#   just gitleaks-scan          # full repo
#   just gitleaks-scan staged   # staged changes only
# For pre-commit integration: pre-commit run --hook-stage manual gitleaks
gitleaks-scan scope="repo":
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
    if [ "{{ scope }}" = "staged" ]; then
        echo "=== Gitleaks: scanning staged changes (via pre-commit) ==="
        uv run pre-commit run gitleaks
    elif [ "{{ scope }}" = "repo" ]; then
        echo "=== Gitleaks: scanning full repo (Docker) ==="
        docker compose --profile security run --rm gitleaks detect --verbose --config /repo/.gitleaks.toml
    else
        echo "Usage: just gitleaks-scan [repo|staged]" >&2
        exit 1
    fi

# Audit Python dependencies for known vulnerabilities (runs via pre-commit hook and CI).
pip-audit:
    uv run python scripts/ci/pip_audit_wrapper.py

# Lint Dockerfiles with Hadolint (runs in Docker to avoid native dep issues).
# Usage:
#   just hadolint-scan            # scan all Dockerfiles
#   just hadolint-scan Dockerfile # scan a single file
hadolint-scan target="/repo/Dockerfile /repo/services/dashboard/Dockerfile /repo/infra/database/Dockerfile":
    docker compose --profile security run --rm hadolint {{target}}

# Scan IaC files (Terraform, Docker Compose, K8s) for misconfigurations with Checkov.
# Runs in Docker (like Trivy) to avoid native dependency issues on Python 3.14.
checkov-scan:
    docker compose --profile security run --rm checkov --directory /repo/infra/ --compact --soft-fail



# ─── DATABASE MANAGEMENT ──────────────────────────────────────────────────────

# Safe psql wrapper: blocks accidental connections to AWS RDS hostnames.
psql-safe db-host="db":
    #!/usr/bin/env bash
    set -euo pipefail
    TARGET="${db-host}"
    if [[ "$TARGET" =~ \.(rds|amazonaws\.com|database\.azure\.com|postgres\.database\.azure\.com)$ ]]; then
        echo "BLOCKED: psql-safe refuses to open an interactive shell against a cloud-managed hostname." >&2
        echo "  Target: $TARGET" >&2
        echo "  If you really need this, use: psql \"\$DATABASE_URL\" directly." >&2
        exit 1
    fi
    if [ "$TARGET" = "db" ]; then
        docker compose exec db psql -U postgres -d api_observatory
    else
        psql "postgresql://postgres:${POSTGRES_PASSWORD:-postgres}@${TARGET}:5432/api_observatory"
    fi



# ─── TESTING & UTILITIES ──────────────────────────────────────────────────────

# Uncomment the additional pytest lines to run integration/e2e/chaos variants.
test-unit:
    uv run pytest -m unit -q
    # uv run pytest -m integration -q              # → test-integration
    # uv run pytest -m e2e -q                      # → test-e2e
    # uv run pytest tests/e2e/test_chaos.py -v --no-cov --run-chaos  # → test-chaos

test-integration:
    uv run pytest -m integration -q

test-e2e:
    uv run pytest -m e2e -q

# E2E smoke: db-reset → admin → seed → Bruno
api-test:
    just db-reset
    just _auto-init
    cd bruno && bru run auth ops sources contracts scorecards websocket -r --env local --env-var "baseUrl=${BRUNO_BASE_URL:-http://127.0.0.1:8000}"

# Load test (k6). Requires k6 installed locally. Realistic CRUD scenario.
# Usage:
#   just test-load                    # defaults to http://127.0.0.1:8000
#   just test-load BASE_URL=https://127.0.0.1 VUS=20 DURATION=60s
test-load:
    #!/usr/bin/env bash
    set -euo pipefail
    BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
    VUS="${VUS:-5}"
    DURATION="${DURATION:-90s}"
    echo "Running k6 — BASE_URL=${BASE_URL}, VUS=${VUS}, DURATION=${DURATION}"
    k6 run \
      --vus "${VUS}" \
      --duration "${DURATION}" \
      --env "BASE_URL=${BASE_URL}" \
      --env "BEARER_TOKEN=${BEARER_TOKEN:-}" \
      scripts/load/k6-observations-load.js

# Chaos test (Docker kill + restart scenarios). Requires local Compose stack.
test-chaos:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Chaos tests mutate running containers. Ensure stack is healthy first:"
    echo "  just db-reset"
    echo ""
    uv run pytest tests/e2e/test_chaos.py -v --no-cov --run-chaos

# One recipe to hold all thin CLI wrappers as commented lines.
# Uncomment the line you need, save, and run: just ops
ops:
    #!/usr/bin/env bash
    set -euo pipefail
    # ─── Container lifecycle ─────────────────────────────────────
    # docker compose down
    docker compose --profile ingress down
    # docker compose up -d floci
    # docker compose --profile azure down
    # docker compose logs -f ingestor
    # docker compose exec ingestor /bin/bash
    # docker compose restart ingestor
    # docker compose ps --filter 'name=api-obs-floci' --filter 'status=running'
    #
    # ─── DB / psql ────────────────────────────────────────────────
    # docker compose exec db psql -U postgres -d api_observatory
    # docker compose exec -T db pg_dump -U postgres api_observatory > .local-dev/dumps/dump.sql
    # docker compose exec -T db psql -U postgres -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" api_observatory
    # docker compose exec -T db psql -U postgres -d api_observatory < dump.sql
    # docker compose rm -sfv ingestor db && docker compose up -d --build db cache broker ingestor dashboard edge
    #
    # ─── Security scans ──────────────────────────────────────────
    # pre-commit run --hook-stage manual gitleaks   # staged secret scan (via pre-commit)
    # just gitleaks-scan                 # full repo secret scan
    # just gitleaks-scan staged          # staged changes only
    # just checkov-scan                  # IaC misconfiguration scan (via Docker)
    #
    # ─── Docker images ────────────────────────────────────────────
    # test -f Dockerfile
    # test -f services/dashboard/Dockerfile
    # docker build -t api-observatory:local .
    # docker build -t api-observatory-dashboard:local -f services/dashboard/Dockerfile .
    # docker image inspect api-observatory:local --format='{{ "{{" }}.Size{{ "}}" }}'
    # docker compose --profile security run --rm trivy image --scanners vuln --severity CRITICAL --ignore-unfixed --timeout 15m --exit-code 1 api-observatory:local
    #
    # ─── Blob / Queue Storage (az cli) ──────────────────────────
    # az storage blob list --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --container-name backups
    # az storage blob upload --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --container-name backups --name dump.sql.gz --file dump.sql.gz
    # az storage blob download --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --container-name backups --name dump.sql.gz --file dump.sql.gz
    # az storage container create --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --name backups
    # az storage queue list --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
    # az storage queue create --connection-string "$AZURE_STORAGE_CONNECTION_STRING" --name drift-events
    #
    # ─── Health checks ────────────────────────────────────────────
    # curl -sf http://127.0.0.1:8000/readyz
    # curl -sf http://127.0.0.1:4577/health
    # curl -sf http://127.0.0.1:8000/health
    #
    # ─── Backup / Restore ─────────────────────────────────────────
    # bash infra/scripts/backup.sh
    # BACKUP_STORAGE=s3 bash infra/scripts/backup.sh
    # BACKUP_STORAGE=both bash infra/scripts/backup.sh
    # bash infra/scripts/restore.sh postgres <file>
    # bash infra/scripts/restore.sh postgres --from-s3 s3://bucket/path/dump.sql.gz
    #
    # ─── Ansible ──────────────────────────────────────────────────
    # cd infra/ansible && ansible-galaxy collection install -r requirements.yml
    # cd infra/ansible && ansible-playbook playbooks/bootstrap.yml -i inventory/hosts.yml --ask-vault-pass --limit dev
    # cd infra/ansible && ansible-playbook playbooks/drift-check.yml -i inventory/hosts.yml --ask-vault-pass --limit dev
    # cd infra/ansible && ansible-playbook playbooks/sandbox-host.yml -i inventory/hosts.yml --limit dev --ask-become-pass
    # cd infra/ansible && ansible-playbook playbooks/local-dev.yml -i inventory/hosts.yml --limit dev --ask-become-pass
    #
    # ─── Terraform shortcuts ──────────────────────────────────────
    # just tf init
    # just tf plan
    # just tf apply
    # just tf show
    # TF_ENV=dev just tf plan
    # just tf fresh
    # just tf-diagram png
    # just tf-diagram svg
    # just tf-diagram html
    #
    # ─── Terraform destroy (with confirmation) ────────────────────
    # cd infra/terraform/environments/azure-sandbox && terraform destroy -auto-approve -var-file=terraform.tfvars
    #
    # ─── Terraform diagram prep ───────────────────────────────────
    # cd infra/terraform/environments/azure-sandbox && terraform show -json tfplan > "$(git rev-parse --show-toplevel)/.local-dev/tfplan-azure-sandbox.json"
    # cd infra/terraform/environments/azure-sandbox && terraform graph > "$(git rev-parse --show-toplevel)/.local-dev/graph-azure-sandbox.dot"
    #
    # ─── Full destroy ─────────────────────────────────────────────
    # TF_ENV=sandbox just tf destroy || true; docker compose down
    echo "Edit Justfile recipe 'ops': uncomment the line you need and run again."

migrate:
    uv run alembic upgrade head

# Private: wait for API, then seed admin + demo sources
_sandbox-seed:
    #!/usr/bin/env bash
    set -euo pipefail
    until curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; do sleep 1; done
    just _auto-init

# Private: start emulator + Docker infra for sandbox workflows
_sandbox-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    just floci-az-up
    docker compose up -d db cache broker ingestor dashboard
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done

# ─── SEEDS & INIT ─────────────────────────────────────────────────────────────

_get_token:
    #!/usr/bin/env bash
    set -euo pipefail
    API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
    TOKEN_URL="${API_BASE_URL%/}/api/v1/auth/token"
    for attempt in 1 2 3; do
        set +e
        HTTP_CODE=$(curl -s -o /tmp/get_token_body.$$ -w "%{http_code}" \
            -X POST "$TOKEN_URL" \
            -H 'Content-Type: application/x-www-form-urlencoded' \
            -d 'username=admin&password=admin123')
        CURL_EXIT=$?
        BODY=$(cat /tmp/get_token_body.$$ 2>/dev/null || true)
        rm -f /tmp/get_token_body.$$
        set -e
        if [ "$CURL_EXIT" -eq 0 ] && [ "$HTTP_CODE" = "200" ] && [ -n "$BODY" ]; then
            TOKEN=$(printf '%s' "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || true)
            if [ -n "$TOKEN" ]; then
                printf '%s\n' "$TOKEN"
                exit 0
            fi
        fi
        sleep $((attempt * 2))
    done
    echo "ERROR: failed to obtain auth token after 3 attempts (last HTTP=${HTTP_CODE:-?} body=${BODY:-}${BODY:+...})" >&2
    exit 1

# Print copy-pasteable curl commands for manual bootstrap.
# Run after `just up` or `just dev`.
# Alternatively, open Bruno Desktop → run auth/1-register.bru then auth/2-login.bru.
init:
    @echo ""
    @echo "--- Bruno Desktop alternative ---"
    @echo "  Just open bruno/ in Bruno Desktop, then:"
    @echo "    1. Select env 'local' (right sidebar)"
    @echo '    2. Run "auth/1-register.bru"'
    @echo '    3. Run "auth/2-login.bru"  (auto-sets token)'
    @echo '    4. Run "sources/2-create-source.bru"  (auto-sets source_id)'
    @echo ""
    @echo "--- Or use curl ---"
    @echo "1. Register as admin"
    @echo ""
    @echo '  curl -X POST http://127.0.0.1:8000/api/v1/auth/register \'
    @echo "    -H 'Content-Type: application/json' \\"
    @echo "    -d '{\"username\":\"admin\",\"password\":\"admin123\",\"email\":\"admin@example.com\",\"role\":\"admin\"}'"
    @echo ""
    @echo "2. Sign in, save token"
    @echo ""
    @echo "  TOKEN=\$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \\"
    @echo "    -H 'Content-Type: application/x-www-form-urlencoded' \\"
    @echo "    -d 'username=admin&password=admin123' | python3 -c \"import sys,json; print(json.load(sys.stdin)['access_token'])\")"
    @echo ""
    @echo "3. Register a source"
    @echo ""
    @echo '  curl -X POST http://127.0.0.1:8000/api/v1/sources \'
    @echo "    -H \"Authorization: Bearer \$TOKEN\" \\"
    @echo "    -H 'Content-Type: application/json' \\"
    @echo "    -d '{\"name\":\"httpbin\",\"base_url\":\"https://httpbin.org\",\"health_check_path\":\"/get\",\"probe_interval_seconds\":10}'"
    @echo ""
    @echo "4. Verify"
    @echo ""
    @echo '  curl http://127.0.0.1:8000/api/v1/sources \'
    @echo "    -H \"Authorization: Bearer \$TOKEN\""
    @echo ""

# Private: auto-create admin + seed demo sources (used by CI and sandbox).
# Equivalent to running the 4 curl commands from `just init` programmatically.
_auto-init:
    #!/usr/bin/env bash
    set -euo pipefail
    API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
    API_BASE_URL="${API_BASE_URL%/}"
    REGISTER_URL="${API_BASE_URL}/api/v1/auth/register"
    curl -sf -X POST "$REGISTER_URL" \
      -H 'Content-Type: application/json' \
      -d '{"username":"admin","password":"admin123","email":"admin@example.com","role":"admin"}' \
      >/dev/null 2>&1 || true
    TOKEN=$(just _get_token)
    BASE_URL="${API_BASE_URL}" \
      bash .local-dev/scripts/seed-sources.sh "$TOKEN" \
        .local-dev/payloads/source-*.json
    echo "auto-init complete — probe sources run every 10s"

# Backward compat: old recipe names delegate to _auto-init.
create-admin: _auto-init
seed: init

# ─── K3Sc / K8S LOCAL SANDBOX ──────────────────────────────────────────────────
#
# Prerequisites: k3d, helm, kubectl, docker.
#   brew install k3d helm kubectl  # macOS
#   or: curl -sfL https://get.k3s.io | sh -
# Full lifecycle: just k3s-up → wait → just k3s-status → just k3s-down

# Create the k3d cluster for local sandbox.
k3s-cluster-create:
    k3d cluster create --config infra/kubernetes/k3d.yaml \
      --kubeconfig-update-default --kubeconfig-switch-context
    echo "cluster data-zoo created — context: k3d-data-zoo"

# Delete the k3d cluster.
k3s-cluster-delete:
    k3d cluster delete data-zoo

# Build Docker images for ingestor and dashboard, tagged for k3d.
k3s-build:
    docker build -t data-zoo/ingestor:latest .
    docker build -t data-zoo/dashboard:latest -f services/dashboard/Dockerfile .
    echo "images built: data-zoo/ingestor:latest, data-zoo/dashboard:latest"

# Import locally-built images into the k3d cluster.
k3s-load-images:
    k3d image import -c data-zoo \
      data-zoo/ingestor:latest \
      data-zoo/dashboard:latest

# Install infrastructure services (PostgreSQL, Redis, Redpanda) via Helm.
k3s-deploy-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    helm repo add --force-update bitnami https://charts.bitnami.com/bitnami
    helm repo add --force-update redpanda https://charts.redpanda.com
    helm repo update
    kubectl create namespace data-zoo --dry-run=client -o yaml | kubectl apply -f -
    for chart in postgresql redis; do
      helm upgrade --install "$chart" "bitnami/$chart" \
        --namespace data-zoo \
        --values "infra/kubernetes/helm-values/${chart}.yaml" \
        --wait
    done
    helm upgrade --install redpanda redpanda/redpanda \
      --namespace data-zoo \
      --values infra/kubernetes/helm-values/redpanda.yaml \
      --wait

# Apply the secret (from example — edit secret.example.yaml first for real secrets).
k3s-secret:
    kubectl apply -n data-zoo -f infra/kubernetes/overlays/local/secret.example.yaml

# Run alembic migrations as a one-off Job (schema is empty on a fresh cluster).
k3s-migrate:
    kubectl delete job/ingestor-migrate -n data-zoo --ignore-not-found
    kubectl apply -f infra/kubernetes/overlays/local/migrate-job.yaml
    kubectl -n data-zoo wait --for=condition=complete job/ingestor-migrate --timeout=60s

# Deploy app services via kustomize overlay.
k3s-deploy:
    kubectl apply -k infra/kubernetes/overlays/local
    echo "kustomize applied — waiting for rollout..."
    kubectl -n data-zoo rollout status deployment/ingestor --timeout=120s
    kubectl -n data-zoo rollout status deployment/dashboard --timeout=120s
    echo "all deployments ready"

# Show cluster status: pods, deployments, services, ingress.
k3s-status:
    @echo "=== Pods ==="
    @kubectl -n data-zoo get pods -o wide
    @echo ""
    @echo "=== Deployments ==="
    @kubectl -n data-zoo get deployments
    @echo ""
    @echo "=== Services ==="
    @kubectl -n data-zoo get services
    @echo ""
    @echo "=== Ingress ==="
    @kubectl -n data-zoo get ingress

# Tail logs for a service (e.g. just k3s-logs ingestor).
k3s-logs service="":
    @kubectl -n data-zoo logs "deployment/{{service}}" --tail=50 -f

# Port-forward a service port to localhost.
k3s-port-forward service="" local-port="" remote-port="":
    kubectl -n data-zoo port-forward "deployment/{{service}}" {{local-port}}:{{remote-port}}

# Full lifecycle: create cluster → build images → load → deploy infra → deploy apps.
k3s-up:
    @just k3s-cluster-create
    @just k3s-build
    @just k3s-load-images
    @just k3s-deploy-infra
    @just k3s-secret
    @just k3s-migrate
    @just k3s-deploy
    @echo ""
    @echo "=== k3s-up complete ==="
    @just k3s-status
    @echo ""
    @echo "Ingress:  http://ingestor.127.0.0.1.nip.io:8080"
    @echo "          http://dashboard.127.0.0.1.nip.io:8080"

# Tear down the entire k3d cluster.
k3s-down:
    k3d cluster delete data-zoo

# Run post-deploy smoke checks.
smoke-test base-url="http://127.0.0.1:8000" dashboard-url="http://127.0.0.1:8501":
    bash scripts/smoke-test.sh {{base-url}} {{dashboard-url}}
