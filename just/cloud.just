# Cloud/Terraform command facade.
#
# These names keep cloud work visibly separate from the core local workflow while
# preserving the existing recipe implementations during the migration.

# Cloud development loops:
#   CLOUD=azure just cloud-sandbox-up    # Azure emulator (floci-az)
#   CLOUD=aws   just cloud-sandbox-up    # AWS emulator (floci-aws)
#   CLOUD=gcp   just cloud-sandbox-up    # GCP emulator (floci-gcp)
#   CLOUD=aws   just cloud-sandbox-dev   # hot-reload against AWS emulator
#   TF_ENV=aws-sandbox just cloud-tf plan # Terraform against emulator
#
# Emulators start only when cloud-shaped APIs are explicitly needed.
# `cloud-sandbox-up` intentionally includes migration and demo seeding because this
# is a disposable cloud-emulator lab; core/extended local workflows remain explicit.

# Start Floci emulator + data-plane services, run migrations.
cloud-sandbox-up:
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
    docker compose up -d --build ingestor-db cache broker ingestor dashboard edge
    until docker compose exec -T ingestor-db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just db-migrate
    just _cloud-sandbox-seed

# Stop Floci emulator only (Compose data-plane keeps running).
cloud-sandbox-down:
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
cloud-sandbox-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    CLOUD="${CLOUD:-azure}"
    case "$CLOUD" in
        azure)
            export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:4577/devstoreaccount1" # gitleaks:allow — documented Azure Storage emulator key
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
    docker compose up -d ingestor-db cache broker
    docker compose stop ingestor dashboard >/dev/null 2>&1 || true
    docker compose rm -f ingestor dashboard >/dev/null 2>&1 || true
    until docker compose exec -T ingestor-db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just db-migrate
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
cloud-sandbox-validate:
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
        echo "  Start it with: CLOUD=${CLOUD} just cloud-sandbox-up" >&2
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

# Unified Terraform runner — resolves the environment from TF_ENV.
cloud-tf cmd:
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
        validate) terraform validate ;;
        plan)
            export TF_IN_AUTOMATION=1
            terraform plan -input=false -var-file=terraform.tfvars -out=tfplan
            ;;
        apply) terraform apply tfplan ;;
        show) terraform show ;;
        destroy) terraform destroy -auto-approve -var-file=terraform.tfvars ;;
        fresh)
            just cloud-tf init
            just cloud-tf plan
            just cloud-tf apply
            ;;
        *) echo "Usage: just cloud-tf <init|validate|plan|apply|show|destroy|fresh>"; exit 1 ;;
    esac

# Destroy Terraform-managed resources with confirmation prompt.
cloud-tf-destroy:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-azure-sandbox}"
    EXPECTED="yes-i-really-want-to-destroy-${ENV}"
    read -r -p "DANGER: Type '${EXPECTED}' to destroy ${ENV} infra: " CONFIRM
    if [ "$CONFIRM" != "$EXPECTED" ]; then
        echo "Aborted."
        exit 1
    fi
    just cloud-tf destroy

# Render Terraform architecture diagrams with Terravision.
cloud-tf-diagram format="png":
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
    if [ -f "$PLANFILE" ] && [ -f "$GRAPHFILE" ]; then USE_PLAN=true; fi
    if [ "$USE_PLAN" = "true" ]; then
        if [ "$FORMAT" = "html" ] || [ "$FORMAT" = "interactive" ]; then
            uv run terravision visualise --planfile "$PLANFILE" --graphfile "$GRAPHFILE" --source "$DIR" --outfile "$OUTFILE"
            echo "Interactive HTML diagram written to ${OUTFILE}.html"
        else
            uv run terravision draw --planfile "$PLANFILE" --graphfile "$GRAPHFILE" --source "$DIR" --format "$FORMAT" --outfile "$OUTFILE"
            echo "Diagram written to ${OUTFILE}.${FORMAT}"
        fi
    elif [ "$FORMAT" = "html" ] || [ "$FORMAT" = "interactive" ]; then
        uv run terravision visualise --source "$DIR" --outfile "$OUTFILE" || {
            echo "HCL parsing may fail on complex for loops; generate plan and graph JSON first." >&2
            exit 1
        }
        echo "Interactive HTML diagram written to ${OUTFILE}.html"
    else
        uv run terravision draw --source "$DIR" --format "$FORMAT" --outfile "$OUTFILE" || {
            echo "HCL parsing may fail on complex for loops; generate plan and graph JSON first." >&2
            exit 1
        }
        echo "Diagram written to ${OUTFILE}.${FORMAT}"
    fi

# Print the active stack configuration based on environment variables and Docker state.
cloud-stack-info:
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
    if docker compose ps ingestor-db >/dev/null 2>&1 && docker compose exec -T ingestor-db pg_isready -U postgres >/dev/null 2>&1; then
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
