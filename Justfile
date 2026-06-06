# ─── ONBOARDING ───────────────────────────────────────────────────────────────

doctor:
    bash scripts/setup/00-doctor.sh

api-check:
    @curl -sf http://localhost:8000/readyz > /dev/null && echo "stack ready" || (echo "stack not ready — run: just up" >&2; exit 1)

# ─── DAILY DEV (Docker Compose) ───────────────────────────────────────────────

# Start MVP services (db, redis, redpanda, ingestor, dashboard)
up:
    docker compose up -d db redis redpanda ingestor dashboard

down:
    docker compose down

# HTTPS proxy via nginx (requires mkcert certs — run `bash scripts/setup/02-setup-local-https.sh` first)
up-https:
    docker compose --profile https up -d

down-https:
    docker compose --profile https down nginx

# Single recipe for logs, shell, or restart — pick one mode
ops:
    #!/usr/bin/env bash
    set -euo pipefail
    MODE="${1:-logs}"
    SVC="${2:-ingestor}"
    case "$MODE" in
        logs) docker compose logs -f "$SVC" ;;
        shell) docker compose exec "$SVC" /bin/bash ;;
        restart) docker compose restart "$SVC" ;;
        *) echo "Usage: just ops <logs|shell|restart> [service]"; exit 1 ;;
    esac

# Fresh DB state — idempotent, starts full infra, waits for readyz
db-reset:
    docker compose rm -sfv ingestor db || true
    docker compose up -d db redis redpanda ingestor dashboard
    @bash -c 'until curl -sf http://localhost:8000/readyz > /dev/null 2>&1; do sleep 1; done && echo "stack ready"'

migrate:
    uv run alembic upgrade head

db-shell:
    docker compose exec db psql -U postgres -d api_observatory

create-admin:
    curl -sf -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/register \
      -H "Content-Type: application/json" \
      -d '{"username":"admin","email":"admin@example.com","password":"admin123","role":"admin"}' | \
      grep -qE "^(201|409)" && echo "admin user ready" || (echo "create-admin failed" >&2; exit 1)

# ─── FEATURE DEV (local uvicorn + Docker infra) ───────────────────────────────

# Start Docker infra, then uvicorn with live reload.
# For sandbox AWS mode: source scripts/aws-env.sh first, or set AWS_ENDPOINT_URL etc.
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose up -d db redis redpanda
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# ─── TESTING ──────────────────────────────────────────────────────────────────

test-unit:
    uv run pytest -m unit -q

test-integration:
    uv run pytest -m integration -q

test-e2e:
    uv run pytest -m e2e -q

# E2E smoke: db-reset → admin → seed → Bruno
# Note: db-reset starts the ingestor container, which auto-runs migrations via its CMD.
api-test:
    just db-reset
    just create-admin
    just seed-source
    cd bruno && bru run auth ops sources contracts scorecards websocket -r --env local

# Load test (k6). Requires k6 installed locally.
# Example: just test-load --duration 30s --vus 10
test-load:
    #!/usr/bin/env bash
    set -euo pipefail
    k6 run --duration "${1:-30s}" --vus "${2:-10}" scripts/load/api-smoke.js

# Chaos test (toxiproxy). Requires toxiproxy running on localhost:8474.
test-chaos:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Ensure toxiproxy is running: docker run -p 8474:8474 -p 8475:8475 toxiproxy:latest"
    uv run pytest tests/e2e/test_chaos.py -v --no-cov

# ─── CLOUD-EMULATION (Floci + Docker infra + local uvicorn) ───────────────────

# Start Floci + infra, then run AWS sandbox tests
sandbox:
    #!/usr/bin/env bash
    set -euo pipefail
    just _sandbox-infra
    just _sandbox-seed
    source scripts/aws-env.sh
    uv run pytest tests/e2e/test_floci_integration.py -v -m aws --no-cov

# Start Floci emulator + Docker infra (interactive dev)
sandbox-up:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose up -d floci
    for i in $(seq 1 30); do
        if curl -sf http://localhost:4566/_floci/health > /dev/null 2>&1; then
            source scripts/aws-env.sh
            aws s3 mb s3://data-pipeline-local >/dev/null 2>&1 || true
            aws sqs create-queue --queue-name pipeline-events >/dev/null 2>&1 || true
            exit 0
        fi
        sleep 1
    done
    echo "Floci failed to start within 30s" >&2
    docker compose down floci
    exit 1

sandbox-down:
    docker compose down floci

sandbox-reset:
    docker compose down floci
    just sandbox-up

# Build + push images to Floci ECR, then trigger ECS deployment for both services.
# Requires: Floci running, Terraform applied (just tf-apply), Docker daemon available.
# Images are tagged to match Terraform task-definitions and Floci ECS finds them
# in the local Docker daemon via the mounted /var/run/docker.sock.
sandbox-deploy:
    bash scripts/sandbox/deploy.sh

sandbox-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# ─── SEEDS & INIT ─────────────────────────────────────────────────────────────

_get_token:
    #!/usr/bin/env bash
    curl -sf -X POST http://localhost:8000/api/v1/auth/token \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -d 'username=admin&password=admin123' | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"

seed-source:
    #!/usr/bin/env bash
    TOKEN=$(just _get_token)
    bash .local-dev/scripts/seed-sources.sh "$TOKEN" \
      .local-dev/payloads/source-seed-internal.json
    echo "seed-source complete"

seed-demo:
    #!/usr/bin/env bash
    TOKEN=$(just _get_token)
    bash .local-dev/scripts/seed-sources.sh "$TOKEN" \
      .local-dev/payloads/source-httpbin.json \
      .local-dev/payloads/source-jsonplaceholder.json \
      .local-dev/payloads/source-postman-echo.json
    echo "seed-demo complete"

seed-probes:
    #!/usr/bin/env bash
    TOKEN=$(just _get_token)
    bash .local-dev/scripts/seed-sources.sh "$TOKEN" \
      .local-dev/payloads/source-probe-ok.json \
      .local-dev/payloads/source-probe-fail.json
    echo "seed-probes complete — wait ~10s for first probe cycle"

# Private: start Floci + Docker infra for sandbox workflows
_sandbox-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    just sandbox-up
    docker compose up -d db redis redpanda
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done

# Private: wait for API, then seed admin + demo sources
_sandbox-seed:
    #!/usr/bin/env bash
    set -euo pipefail
    until curl -sf http://localhost:8000/health > /dev/null 2>&1; do sleep 1; done
    just create-admin
    just seed-demo

# ─── DOCKER & RELEASE ─────────────────────────────────────────────────────────

docker-build-image tag="api-observatory:local":
    docker build -t {{tag}} .

# One-shot audit: build → size check → CRITICAL CVE scan
deploy-audit tag="api-observatory:local":
    just docker-build-image {{tag}}
    just docker-audit-size {{tag}}
    just docker-scan-image {{tag}}
    @docker image inspect {{tag}} --format 'Digest: {{{{index .RepoDigests 0}}}}' 2>/dev/null || \
      docker inspect --format 'ID: {{{{.ID}}}}' {{tag}}

docker-audit-size image="api-observatory:local":
    #!/usr/bin/env bash
    set -euo pipefail
    SIZE_BYTES=$(docker image inspect {{image}} --format='{{{{.Size}}}}')
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
    LIMIT_MB=${DOCKER_IMAGE_SIZE_LIMIT_MB:-1500}
    echo "Image {{image}} size: ${SIZE_MB}MB"
    if (( SIZE_MB > LIMIT_MB )); then
        echo "WARNING: image exceeds ${LIMIT_MB}MB budget (allowed for MVP while functionality is prioritized)" >&2
        exit 0
    fi
    echo "Image size check passed"

docker-scan-image image="api-observatory:local":
    docker compose --profile security run --rm trivy image \
        --scanners vuln \
        --severity CRITICAL \
        --ignore-unfixed \
        --timeout 15m \
        --exit-code 1 \
        {{image}}
    echo "No CRITICAL CVEs detected"

# ─── BACKUP & RESTORE ─────────────────────────────────────────────────────────

backup:
    bash infra/scripts/backup.sh

backup-s3:
    BACKUP_STORAGE=s3 bash infra/scripts/backup.sh

backup-both:
    BACKUP_STORAGE=both bash infra/scripts/backup.sh

restore-postgres file="":
    bash infra/scripts/restore.sh postgres {{file}}

restore-s3-postgres s3uri:
    bash infra/scripts/restore.sh postgres --from-s3 {{s3uri}}

# ─── TERRAFORM (unified — sandbox or dev via TF_ENV) ──────────────────────────

# Usage:
#   just tf-init              # auto-detects env from TF_ENV or cwd
#   just tf-plan              # same
#   just tf-apply             # same
#   TF_ENV=dev just tf-plan   # force dev environment


tf-init:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        DIR="infra/terraform/environments/dev"
        source scripts/aws-env-dev.sh 2>/dev/null || true
        unset AWS_PROFILE
        terraform init -reconfigure -upgrade -backend-config=backend.aws.hcl
    else
        DIR="infra/terraform/environments/sandbox"
        source scripts/aws-env.sh
        unset AWS_PROFILE
        BACKEND_BUCKET=$(grep -E '^\s*bucket\s*=' "$DIR/backend.hcl" | head -n1 | sed -E 's/^\s*bucket\s*=\s*"([^\"]+)".*/\1/')
        if [ -n "$BACKEND_BUCKET" ]; then
            aws s3 ls "s3://$BACKEND_BUCKET" >/dev/null 2>&1 || aws s3 mb "s3://$BACKEND_BUCKET"
        fi
        terraform init -reconfigure -upgrade -backend-config=backend.hcl
    fi

tf-validate:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        cd infra/terraform/environments/dev
    else
        source scripts/aws-env.sh
        cd infra/terraform/environments/sandbox
    fi
    terraform validate

tf-plan:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    export TF_IN_AUTOMATION=1
    just tf-validate
    if [ "$ENV" = "dev" ]; then
        cd infra/terraform/environments/dev
        terraform plan -input=false -lock-timeout=30m -var-file=terraform.tfvars -var-file=terraform.aws.tfvars -out=tfplan.aws
    else
        source scripts/aws-env.sh
        cd infra/terraform/environments/sandbox
        terraform plan -input=false -var-file=terraform.tfvars -out=tfplan
    fi

tf-apply:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        cd infra/terraform/environments/dev
        terraform apply -lock-timeout=30m tfplan.aws
    else
        source scripts/aws-env.sh
        cd infra/terraform/environments/sandbox
        terraform apply tfplan
    fi

tf-show:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        cd infra/terraform/environments/dev && terraform show
    else
        source scripts/aws-env.sh
        cd infra/terraform/environments/sandbox && terraform show
    fi

tf-destroy:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        cd infra/terraform/environments/dev
        terraform destroy -auto-approve -lock-timeout=30m -var-file=terraform.tfvars -var-file=terraform.aws.tfvars
    else
        source scripts/aws-env.sh
        cd infra/terraform/environments/sandbox
        terraform destroy -auto-approve -lock=false -var-file=terraform.tfvars
    fi

# One-click: init → plan → apply (sandbox by default)
tf-fresh:
    just tf-init
    just tf-plan
    just tf-apply

# ─── AWS DEPLOY (dev → ECS/Fargate) ──────────────────────────────────────────

# Terraform apply on dev, then ECS service restart.
deploy-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    TF_ENV=dev just tf-apply
    echo "TODO: wire ECS service update here when cluster is provisioned"
    echo "  aws ecs update-service --cluster dev --service ingestor --force-new-deployment"
    echo "  aws ecs wait services-stable --cluster dev --services ingestor"
