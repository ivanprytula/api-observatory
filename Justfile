# ─── DOCTOR / INIT CHECKS ────────────────────────────────────────────────────

# Shared local URL helpers are implemented in scripts/daily/local-url.sh.
# Use LOCAL_API_SCHEME=http (default) for direct API URLs, or
# LOCAL_API_SCHEME=https to route API calls through the edge proxy at https://127.0.0.1/api.
# LOCAL_API_BASE_URL and LOCAL_DASHBOARD_URL override the computed local values.
_local_api_base_url:
    @bash scripts/daily/local-url.sh api-base-url

_local_api_public_base_url:
    @bash scripts/daily/local-url.sh api-public-base-url

_local_dashboard_url:
    @bash scripts/daily/local-url.sh dashboard-url

_local_wait_ready path="/readyz":
    @bash -c 'source scripts/daily/local-url.sh; until curl_local -sf "$(local_api_url "{{path}}")" >/dev/null 2>&1; do sleep 1; done'

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

# Generate high-entropy secrets for .env configuration (db, redis, jwt, etc.).
generate-secrets:
    uv run python scripts/tools/generate-secrets.py



# ─── DAILY DEV FLOWS ─────────────────────────────────────────────────────────
#
# Primary loops:
#   just dev             → uvicorn + Compose data-plane (local)
#   just up              → Compose data-plane only (containerized)
#   just floci-*         → Full Floci sandbox (training playground)
#   TF_ENV=dev just deploy-ecs → Promote to real AWS dev cloud
#
# Floci is only started when you explicitly need S3/SQS/ECS-shaped APIs.

# 2a) Local development (uvicorn + live reload)
# ─────────────────────────────────────────────

# Start both ingestor (uvicorn --reload) and dashboard (Streamlit hot-reload) locally.
# Data-plane (db, cache, broker) runs in Compose; both app services reload on file save.
# For HTTPS API access from the host (e.g. curl, Bruno), set LOCAL_API_SCHEME=https.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    just stack-info
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
    @just stack-info
    docker compose up -d --build db cache broker ingestor dashboard edge
    just _local_wait_ready
    echo "stack ready — https://127.0.0.1 (edge)"


# Start full stack with hot-reload via Compose Watch + uvicorn/streamlit reload.
# First builds and starts everything, then watches only the app services.
# Source code is synced into containers (ignoring __pycache__/).
# uvicorn --reload / Streamlit poll watcher restart the process on file change.
# Dependency file changes (pyproject.toml, uv.lock) trigger a full image rebuild.
watch:
    @just stack-info
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build db cache broker ingestor dashboard
    just _local_wait_ready
    echo ""
    echo "Watching for file changes — Compose Watch syncs code into containers."
    echo "Stop with Ctrl+C.  Containers keep running in the background."
    echo ""
    docker compose -f docker-compose.yml -f docker-compose.dev.yml watch ingestor dashboard

# Start monitoring stack (Prometheus, Grafana, Loki, Promtail, Alertmanager, Mailpit).
up-monitoring:
    @just stack-info
    docker compose --profile monitoring up -d prometheus grafana loki promtail alertmanager mailpit
    echo "monitoring ready — Grafana http://127.0.0.1:3000, Prometheus http://127.0.0.1:9090"



# Start the full stack: data-plane + monitoring. Combines `up` and `up-monitoring`.
up-all: up up-monitoring


# Reset DB and ingestor containers (keep Floci state intact if running).
db-reset:
    @just stack-info
    docker compose rm -sfv ingestor db || true
    docker compose up -d --build db cache broker ingestor dashboard edge
    just _local_wait_ready
    echo "stack ready"

# 2c) Sandbox / AWS-shaped development
# ─────────────────────────────────────

# Start Floci + Compose data-plane + seed admin + demo.
# Uncomment the single docker compose line for the minimal Floci-only variant.
floci-up:
    #!/usr/bin/env bash
    set -euo pipefail
    just stack-info
    docker compose --profile aws up -d floci floci-ecr-registry
    for i in $(seq 1 60); do
        if curl -sf http://127.0.0.1:4566/_floci/health > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    docker compose up -d --build db cache broker ingestor dashboard edge
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    just _sandbox-seed

# Stop Floci only (Compose data-plane keeps running).
floci-down:
    docker compose down floci

# Sync sandbox state after Floci restart: remove ephemeral resources from state
# so Terraform creates them fresh instead of failing on drain-destroy.
floci-sync-state:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh floci
    # Delete ECS services from Floci's in-memory state
    for svc in ingestor dashboard; do
        if aws ecs delete-service --cluster data-zoo-sandbox --service "$svc" --force --endpoint-url http://127.0.0.1:4566 >/dev/null 2>&1; then
            echo "  [del] ecs service $svc (Floci)"
        else
            echo "  [ok] ecs service $svc already absent (Floci)"
        fi
    done
    # Drop from Terraform state so it creates fresh
    DIR="infra/terraform/environments/sandbox"
    cd "$DIR"
    terraform init -reconfigure -backend-config=backend.hcl >/dev/null 2>&1
    for addr in \
        'module.compute.aws_ecs_service.ingestor_fargate[0]' \
        'module.compute.aws_ecs_service.dashboard_fargate[0]' \
        'module.compute.aws_lb_listener.http_redirect[0]' \
        'module.compute.aws_lb_listener_rule.dashboard[0]'; do
        if terraform state rm "$addr" >/dev/null 2>&1; then
            echo "  [rm] $addr (state)"
        else
            echo "  [ok] $addr already absent (state)"
        fi
    done



# Clean destroy for Floci sandbox: rm Floci-broken resources from state, then destroy.
# Uses a timeout to handle Floci VPC deletion hangs, then cleans up any remaining state.
floci-destroy:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh floci
    DIR="infra/terraform/environments/sandbox"
    cd "$DIR"
    terraform init -backend-config=backend.hcl

    for addr in \
        'module.compute.aws_ecs_service.ingestor_fargate[0]' \
        'module.compute.aws_ecs_service.dashboard_fargate[0]' \
        'module.compute.aws_lb_listener.http_redirect[0]' \
        'module.compute.aws_lb_listener_rule.dashboard[0]'; do
        terraform state rm "$addr" 2>/dev/null || true
    done

    # Kill ECS services in Floci's in-memory state to stop the reconciler noise
    for svc in ingestor dashboard; do
        if aws ecs delete-service --cluster data-zoo-sandbox --service "$svc" --force --endpoint-url http://127.0.0.1:4566 >/dev/null 2>&1; then
            echo "  [del] ecs service $svc (Floci)"
        fi
    done

    timeout 120 terraform destroy -auto-approve -lock=false -var-file=terraform.tfvars || \
        echo "  [timeout] terraform destroy exceeded 2m — cleaning up remaining state..."

    for addr in $(terraform state list 2>/dev/null || true); do
        echo "  Cleaning up: $addr"
        r_id=$(terraform state show "$addr" 2>/dev/null | awk '/^\s+id\s+=/{print $3; exit}' | tr -d '"' || true)
        if [ -n "$r_id" ]; then
            case "$addr" in
                *aws_vpc*)             aws ec2 delete-vpc --vpc-id "$r_id"          ;;
                *aws_subnet*)          aws ec2 delete-subnet --subnet-id "$r_id"     ;;
                *aws_lb_target_group*) aws elbv2 delete-target-group --target-group-arn "$r_id" ;;
                *aws_lb.main*)         aws elbv2 delete-load-balancer --load-balancer-arn "$r_id" ;;
                *aws_db_instance*)     aws rds delete-db-instance --db-instance-identifier "$r_id" --skip-final-snapshot ;;
                *aws_elasticache_replication_group*) aws elasticache delete-replication-group --replication-group-id "$r_id" ;;
                *aws_elasticache_cluster*) aws elasticache delete-cache-cluster --cache-cluster-id "$r_id" ;;
                *aws_ecr_repository*)  aws ecr delete-repository --repository-name "$r_id" --force ;;
            esac 2>/dev/null || true
        fi
        terraform state rm "$addr" 2>/dev/null || true
    done
    echo "  [ok] Sandbox destroyed."

# Start both ingestor and dashboard locally with hot reload, using Floci-shaped env (S3 + SQS + ECS APIs).
floci-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    export PYTHONPATH="${PWD}"
    set -a; source "${PWD}/.env"; set +a
    just stack-info
    source scripts/aws-env.sh
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
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# Validate Floci sandbox health before promoting to real AWS.
# Checks: Floci container running, _floci/health reachable, state bucket reachable, API /health OK.
# Run independently before deploy-ecs: just floci-validate
floci-validate:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Floci sandbox validation ==="

    # 1. Floci container must be running
    if ! docker ps --filter 'name=api-obs-floci' --filter 'status=running' --format '{{{{.Names}}}}' | grep -q .; then
        echo "FAIL: Floci container is not running." >&2
        echo "  Start it with: just floci-up" >&2
        exit 1
    fi
    echo "  [ok] Floci container running"

    # 2. Floci health endpoint
    if ! curl -sf http://127.0.0.1:4566/_floci/health > /dev/null 2>&1; then
        echo "FAIL: Floci health endpoint not responding at http://127.0.0.1:4566/_floci/health" >&2
        echo "  Check Floci logs: docker compose logs floci" >&2
        exit 1
    fi
    echo "  [ok] Floci health endpoint OK"

    # 3. Terraform state bucket reachable
    source scripts/aws-env.sh floci
    if ! aws s3 ls s3://s3-native-lock-setup > /dev/null 2>&1; then
        echo "FAIL: Terraform state bucket 's3-native-lock-setup' not found." >&2
        echo "  Run: TF_ENV=sandbox just tf init" >&2
        exit 1
    fi
    echo "  [ok] Terraform state bucket reachable"

    # 4. Application API health (soft-warn only — stack may not be running)
    source scripts/daily/local-url.sh
    if curl_local -sf "$(local_api_url /health)" > /dev/null 2>&1; then
        echo "  [ok] Application API /health OK"
    else
        echo "  [warn] Application API not responding — Compose stack may not be running."
    fi

    echo "=== Floci sandbox validated ==="

# Confirm real AWS credentials and required dev config files are in place.
# Run independently before deploy-ecs: just dev-preflight
dev-preflight:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== AWS dev preflight ==="

    # 1. Must NOT be pointing at an emulator
    if [ -n "${AWS_ENDPOINT_URL:-}" ]; then
        echo "FAIL: AWS_ENDPOINT_URL is set to '${AWS_ENDPOINT_URL}'." >&2
        echo "  Unset it before deploying to real AWS: unset AWS_ENDPOINT_URL" >&2
        exit 1
    fi
    echo "  [ok] AWS_ENDPOINT_URL not set (real AWS mode)"

    # 2. AWS identity must resolve (real credentials present)
    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        echo "FAIL: Cannot resolve AWS identity. Check your credentials/profile." >&2
        echo "  Hint: set AWS_PROFILE or run 'aws configure'" >&2
        exit 1
    fi
    IDENTITY=$(aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null)
    echo "  [ok] AWS identity: ${IDENTITY}"

    # 3. backend.aws.hcl must exist (contains real S3 state bucket)
    if [ ! -f infra/terraform/environments/dev/backend.aws.hcl ]; then
        echo "FAIL: infra/terraform/environments/dev/backend.aws.hcl not found." >&2
        echo "  Copy from example: cp infra/terraform/environments/dev/backend.aws.hcl.example infra/terraform/environments/dev/backend.aws.hcl" >&2
        exit 1
    fi
    echo "  [ok] backend.aws.hcl present"

    # 4. terraform.aws.tfvars must exist (dev-specific variable overrides)
    if [ ! -f infra/terraform/environments/dev/terraform.aws.tfvars ]; then
        echo "FAIL: infra/terraform/environments/dev/terraform.aws.tfvars not found." >&2
        echo "  Copy from example: cp infra/terraform/environments/dev/terraform.aws.tfvars.example infra/terraform/environments/dev/terraform.aws.tfvars" >&2
        exit 1
    fi
    echo "  [ok] terraform.aws.tfvars present"

    echo "=== AWS dev preflight passed ==="

# Run Floci-specific E2E tests (AWS emulator required).
floci-test:
    #!/usr/bin/env bash
    set -euo pipefail
    just _sandbox-infra
    just _sandbox-seed
    source scripts/aws-env.sh floci
    uv run pytest tests/e2e/test_floci_integration.py -v -m aws --no-cov

# Build + push to Floci ECR + ECS deploy.
floci-deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh floci
    bash scripts/sandbox/deploy.sh

# 2d) AWS Deploy (dev → ECS/Fargate)
# ─────────────────────────────────────
# Recommended manual loop before calling deploy-ecs:
#   just floci-validate              # confirm Floci sandbox is healthy
#   just dev-preflight               # confirm real AWS creds + config files
#   docker build -t api-observatory:local . && just docker-scan-image  # build image + CVE scan
#   just gitleaks-scan               # scan repo for leaked secrets
#   just checkov-scan                # scan IaC for misconfigurations
#   TF_ENV=dev just tf init          # init backend (first time or after provider change)
#   TF_ENV=dev just tf validate      # check HCL syntax
#   TF_ENV=dev just tf plan          # review the changeset
#   TF_ENV=dev just tf-diagram       # optional: visualise new architecture
#   # tweak tfvars / modules as needed, re-plan until satisfied
#   just deploy-ecs                  # apply reviewed plan + ECS update

# Apply the reviewed tfplan.aws, then trigger ECS rolling update + smoke test.
# Assumes TF_ENV=dev just tf plan has already been run and tfplan.aws is current.
# Usage:
#   just deploy-ecs                          # cluster=data-zoo-dev, region from AWS config
#   IMAGE_TAG=sha-abc1234 just deploy-ecs    # report a specific image tag in summary
#   AWS_PROFILE=my-profile just deploy-ecs   # explicit AWS profile
infra-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    TF_ENV=dev just tf apply

# Manual AWS ECS deploy wrapper; assumes reviewed tfplan.aws exists.
deploy-ecs:
    #!/usr/bin/env bash
    set -euo pipefail
    IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse HEAD^{tree} | cut -c1-7)}"
    CLUSTER="${ECS_CLUSTER:-data-zoo-dev}"

    just infra-dev

    aws ecs update-service \
        --cluster "${CLUSTER}" \
        --service ingestor \
        --force-new-deployment \
        --output text --query 'service.serviceName'
    echo "Waiting for ingestor to stabilize..."
    aws ecs wait services-stable \
        --cluster "${CLUSTER}" \
        --services ingestor
    echo "  [ok] ingestor stable"

    aws ecs update-service \
        --cluster "${CLUSTER}" \
        --service dashboard \
        --force-new-deployment \
        --output text --query 'service.serviceName'
    echo "Waiting for dashboard to stabilize..."
    aws ecs wait services-stable \
        --cluster "${CLUSTER}" \
        --services dashboard
    echo "  [ok] dashboard stable"

    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --query 'LoadBalancers[?contains(LoadBalancerName, `data-zoo-dev`)].DNSName | [0]' \
        --output text 2>/dev/null || true)
    if [ -n "${ALB_DNS:-}" ] && [ "${ALB_DNS}" != "None" ]; then
        echo "--- Smoke test via ALB: http://${ALB_DNS} ---"
        bash scripts/smoke-test.sh "http://${ALB_DNS}" 60 || \
            echo "WARNING: smoke test failed — inspect ALB and ECS tasks above" >&2
    else
        echo "WARNING: ALB DNS not found — skipping smoke test. Check ALB provisioning." >&2
    fi

    echo ""
    echo "=== deploy-ecs complete ==="
    echo "  Cluster : ${CLUSTER}"
    echo "  Image   : api-observatory:${IMAGE_TAG}"
    echo "  ALB     : ${ALB_DNS:-<not found>}"

# ─── STACK AWARENESS ──────────────────────────────────────────────────────────

# Print the active stack configuration based on environment variables and Docker state.
stack-info:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="$(pwd)"
    set -a; source "${PROJECT_ROOT}/.env"; set +a
    source "${PROJECT_ROOT}/scripts/daily/local-url.sh"
    TF="${TF_ENV:-sandbox}"
    if [ -n "${AWS_PROFILE:-}" ] && [ "$AWS_PROFILE" != "sandbox" ]; then
        CLOUD="AWS (profile=${AWS_PROFILE})"
    elif [ -n "${AWS_ENDPOINT_URL:-}" ]; then
        CLOUD="Floci (${AWS_ENDPOINT_URL})"
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
    echo "  INGESTOR_URL    : $(local_api_base_url)"
    echo "======================"



# ─── INFRASTRUCTURE & IMAGES ──────────────────────────────────────────────────
#
# 3a) Terraform (unified — sandbox or dev via TF_ENV)
# 3b) CVE scan

# 3a) Terraform
# ───────────────

# Usage:
#   just tf init                   # auto-detects env from TF_ENV or cwd
#   just tf plan                   # same
#   just tf apply                  # same
#   TF_ENV=dev just tf plan        # force dev environment
#   just tf fresh                  # init → plan → apply (sandbox by default)

# Unified Terraform runner for sandbox/dev.
tf cmd:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    CMD="{{cmd}}"
    if [ "$ENV" = "dev" ]; then
        DIR="infra/terraform/environments/dev"
    else
        DIR="infra/terraform/environments/sandbox"
        source scripts/aws-env.sh floci
    fi
    cd "$DIR"

    case "$CMD" in
        init)
            if [ "$ENV" = "dev" ]; then
                terraform init -reconfigure -upgrade -backend-config=backend.aws.hcl
            else
                BACKEND_BUCKET=$(grep -E '^\s*bucket\s*=' backend.hcl | head -n1 | sed -E 's/^\s*bucket\s*=\s*"([^\"]+)".*/\1/')
                if [ -n "$BACKEND_BUCKET" ]; then
                    aws s3 ls "s3://$BACKEND_BUCKET" >/dev/null 2>&1 || aws s3 mb "s3://$BACKEND_BUCKET"
                fi
                terraform init -reconfigure -upgrade -backend-config=backend.hcl
            fi
            ;;
        validate)
            terraform validate
            ;;
        plan)
            export TF_IN_AUTOMATION=1
            if [ "$ENV" = "dev" ]; then
                terraform plan \
                    -input=false \
                    -lock-timeout=30m \
                    -var-file=terraform.tfvars \
                    -var-file=terraform.aws.tfvars \
                    -out=tfplan.aws
            else
                terraform plan \
                    -input=false \
                    -var-file=terraform.tfvars \
                    -out=tfplan
            fi
            ;;
        apply)
            if [ "$ENV" = "dev" ]; then
                terraform apply -lock-timeout=30m tfplan.aws
            else
                terraform apply tfplan
            fi
            ;;
        show)
            terraform show
            ;;
        destroy)
            if [ "$ENV" = "dev" ]; then
                terraform destroy \
                    -auto-approve \
                    -lock-timeout=30m \
                    -var-file=terraform.tfvars \
                    -var-file=terraform.aws.tfvars
            else
                terraform destroy \
                    -auto-approve \
                    -lock=false \
                    -var-file=terraform.tfvars
            fi
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

# Destroy Terraform-managed resources with confirmation.
tf-destroy:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        EXPECTED="yes-i-really-want-to-destroy-dev"
    else
        EXPECTED="yes-i-really-want-to-destroy-sandbox"
    fi
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
    ENV="${TF_ENV:-sandbox}"
    PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
    LOCAL_DEV="$PROJECT_ROOT/.local-dev"
    if [ "$ENV" = "dev" ]; then
        DIR="$PROJECT_ROOT/infra/terraform/environments/dev"
    else
        DIR="$PROJECT_ROOT/infra/terraform/environments/sandbox"
    fi
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
    if [[ "$TARGET" =~ \.(rds|amazonaws\.com)$ ]]; then
        echo "BLOCKED: psql-safe refuses to open an interactive shell against an AWS hostname." >&2
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
    BRUNO_BASE_URL="$(just _local_api_base_url)"
    cd bruno && bru run auth ops sources contracts scorecards websocket -r --env local --env-var "baseUrl=${BRUNO_BASE_URL}"

# Load test (k6). Requires k6 installed locally. Realistic CRUD scenario.
# Usage:
#   just test-load                    # defaults from scripts/daily/local-url.sh
#   just test-load BASE_URL=https://127.0.0.1 VUS=20 DURATION=60s
test-load:
    #!/usr/bin/env bash
    set -euo pipefail
    BASE_URL="${BASE_URL:-$(just __local_api_public_base_url)}"
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
    docker compose down
    # docker compose --profile ingress down
    # docker compose up -d floci
    # docker compose --profile aws down
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
    # ─── S3 (aws) ─────────────────────────────────────────────────
    # aws s3 ls s3://api-observatory-local
    # aws s3 cp s3://api-observatory-local .local-dev/dumps/ --recursive
    # aws s3 cp .local-dev/dumps/ s3://api-observatory-local/ --recursive
    # aws s3 mb s3://api-observatory-local
    # aws sqs get-queue-url --queue-name pipeline-events
    # aws sqs create-queue --queue-name pipeline-events
    #
    # ─── Health checks ────────────────────────────────────────────
    # curl -sf http://127.0.0.1:8000/readyz
    # curl -sf http://127.0.0.1:4566/_floci/health
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
    # cd infra/ansible && ansible-playbook playbooks/provision-ec2.yml -i inventory/aws_ec2.yml --limit dev --ask-become-pass --ask-vault-pass
    # cd infra/ansible && ansible-playbook playbooks/sandbox-host.yml -i inventory/hosts.yml --limit dev --ask-become-pass
    # cd infra/ansible && ansible-playbook playbooks/local-dev.yml -i inventory/hosts.yml --limit dev --ask-become-pass
    # cd infra/ansible && ansible-playbook playbooks/ecs-host.yml -i inventory/aws_ec2.yml --limit dev --ask-become-pass --ask-vault-pass
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
    # cd infra/terraform/environments/sandbox && terraform destroy -auto-approve -lock=false -var-file=terraform.tfvars
    #
    # ─── Terraform diagram prep ───────────────────────────────────
    # cd infra/terraform/environments/sandbox && terraform show -json tfplan > "$(git rev-parse --show-toplevel)/.local-dev/tfplan-sandbox.json"
    # cd infra/terraform/environments/sandbox && terraform graph > "$(git rev-parse --show-toplevel)/.local-dev/graph-sandbox.dot"
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
    source scripts/daily/local-url.sh
    until curl_local -sf "$(local_api_url /health)" > /dev/null 2>&1; do sleep 1; done
    just _auto-init

# Private: start Floci + Docker infra for sandbox workflows
_sandbox-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    just floci-up
    docker compose up -d db cache broker ingestor dashboard
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done

# ─── SEEDS & INIT ─────────────────────────────────────────────────────────────

_get_token:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/daily/local-url.sh
    TOKEN_URL="$(local_api_url /api/v1/auth/token)"
    for attempt in 1 2 3; do
        set +e
        HTTP_CODE=$(curl_local -s -o /tmp/get_token_body.$$ -w "%{http_code}" \
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
    source scripts/daily/local-url.sh
    REGISTER_URL="$(local_api_url /api/v1/auth/register)"
    curl_local -sf -X POST "$REGISTER_URL" \
      -H 'Content-Type: application/json' \
      -d '{"username":"admin","password":"admin123","email":"admin@example.com","role":"admin"}' \
      >/dev/null 2>&1 || true
    TOKEN=$(just _get_token)
    BASE_URL="$(local_api_url)" \
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
    helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
    helm repo add redpanda https://charts.vectorized.io 2>/dev/null || true
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
smoke-test base-url="{{_local_api_base_url}}" dashboard-url="{{__local_dashboard_url}}":
    bash scripts/smoke-test.sh {{base-url}} {{dashboard-url}}
