# ─── SETUP & HEALTH CHECK ──────────────────────────────────────────────────

# Local environment doctor (requirements + local artifact folders)
doctor:
    bash scripts/setup/00-doctor.sh

# Verify the stack is healthy. Fails fast if not up.
api-check:
    @curl -sf http://localhost:8000/readyz > /dev/null && echo "stack ready" || (echo "stack not ready — run: just up" >&2; exit 1)

# ─── CORE STACK ─────────────────────────────────────────────────────────────

# Core services (database, message broker, API)
up:
    docker compose up -d db redis redpanda ingestor mongodb

# Full stack with all workers and webhooks
up-all:
    docker compose --profile vector --profile monitoring --profile worker --profile webhook up -d

# Vector search stack
up-vector:
    docker compose --profile vector up -d

# Monitoring stack (Prometheus, Grafana, Alertmanager)
up-monitor:
    docker compose --profile monitoring up -d

# Django catalog portal
up-portal:
    docker compose --profile portal up -d portal

# View logs for a specific service
logs svc:
    docker compose logs -f {{svc}}

# Stop all services
down:
    docker compose down

# ─── DATABASE MANAGEMENT ───────────────────────────────────────────────────

# Run database migrations
migrate:
    uv run alembic upgrade head

# Wipe DB to a clean empty state: stop → remove container+volume → restart → wait.
db-reset:
    docker compose rm -sfv ingestor db
    docker compose up -d db
    @bash -c 'until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done'
    just migrate
    docker compose up -d ingestor
    @bash -c 'until curl -sf http://localhost:8000/readyz > /dev/null 2>&1; do sleep 1; done && echo "stack ready"'

# ─── BACKUP & RESTORE ──────────────────────────────────────────────────────

# Run a local-only backup (writes to ./backups/)
backup:
    bash infra/scripts/backup.sh

# Run backup and upload to S3 (uses BACKUP_S3_BUCKET + AWS_ENDPOINT_URL from .env)
backup-s3:
    BACKUP_STORAGE=s3 bash infra/scripts/backup.sh

# Run backup to both local and S3
backup-both:
    BACKUP_STORAGE=both bash infra/scripts/backup.sh

# Restore PostgreSQL from a local file (interactive if no arg)
restore-postgres file="":
    bash infra/scripts/restore.sh postgres {{file}}

# Restore PostgreSQL from an S3 URI  e.g.: just restore-s3-postgres s3://bucket/key
restore-s3-postgres s3uri:
    bash infra/scripts/restore.sh postgres --from-s3 {{s3uri}}

# Restore MongoDB from an S3 URI
restore-s3-mongodb s3uri:
    bash infra/scripts/restore.sh mongodb --from-s3 {{s3uri}}

# ─── INITIALIZATION ────────────────────────────────────────────────────────

# Create the default admin user. After db-reset this is always 201; outside tests 409 is also fine.
create-admin:
    curl -sf -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/register \
      -H "Content-Type: application/json" \
      -d '{"username":"admin","email":"admin@example.com","password":"admin123","role":"admin"}' | \
      grep -qE "^(201|409)" && echo "admin user ready" || (echo "create-admin failed" >&2; exit 1)

# Seed one demo source via API (requires admin to exist first).
# Contracts tests depend on source_id=1 existing before they run.
seed-source:
    #!/usr/bin/env bash
    set -euo pipefail
    TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/token \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -d 'username=admin&password=admin123' | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
    curl -sf -X POST http://localhost:8000/api/v1/sources \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"name":"seed-internal","base_url":"https://httpbin.org","health_check_path":"/get","probe_interval_seconds":60,"is_active":true}' > /dev/null
    echo "seed-source complete"

# Seed demo source profiles for probe/scorecard workflows
seed-demo:
        curl -s -X POST http://localhost:8000/api/v1/sources \
            -H "Content-Type: application/json" \
            -d '{"name":"httpbin","base_url":"https://httpbin.org","health_check_path":"/get","probe_interval_seconds":10,"is_active":true}' > /dev/null
        curl -s -X POST http://localhost:8000/api/v1/sources \
            -H "Content-Type: application/json" \
            -d '{"name":"jsonplaceholder","base_url":"https://jsonplaceholder.typicode.com","health_check_path":"/posts/1","probe_interval_seconds":10,"is_active":true}' > /dev/null
        curl -s -X POST http://localhost:8000/api/v1/sources \
            -H "Content-Type: application/json" \
            -d '{"name":"postman-echo","base_url":"https://postman-echo.com","health_check_path":"/get","probe_interval_seconds":10,"is_active":true}' > /dev/null
        @echo "seed-demo complete"

# ─── VALIDATION & TESTING ─────────────────────────────────────────────────

# Smoke deploy against the prod-like compose stack.
smoke-deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    bash scripts/ops/02-compose-profile.sh prod-like up -d db redis redpanda ingestor
    trap 'bash scripts/ops/02-compose-profile.sh prod-like down -v' EXIT

    for _ in $(seq 1 60); do
        if curl -fsS http://localhost:8000/health >/dev/null && curl -fsS http://localhost:8000/readyz >/dev/null; then
            echo "smoke deploy passed"
            exit 0
        fi
        sleep 5
    done

    echo "smoke deploy failed" >&2
    bash scripts/ops/02-compose-profile.sh prod-like logs ingestor
    exit 1

# E2E smoke test: clean DB → seed admin + source → run Bruno collections.
# On failure, reset DB to leave local state clean.
api-test:
    #!/usr/bin/env bash
    set -euo pipefail

    cleanup_on_failure() {
        status=$?
        if [ "$status" -ne 0 ]; then
            echo "[api-test] failed, running cleanup: just db-reset"
            just db-reset
        fi
    }
    trap cleanup_on_failure EXIT

    echo "[api-test] step 1/4: db-reset"
    just db-reset

    echo "[api-test] step 2/4: create-admin"
    just create-admin

    echo "[api-test] step 3/4: seed-source"
    just seed-source

    echo "[api-test] step 4/4: run bruno"
    cd bruno && bru run . -r --env local

    echo "[api-test] success"

# Run Floci integration tests (verifies connectivity + runs tests)
sandbox-test:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    aws s3 ls >/dev/null
    aws sqs list-queues >/dev/null 2>&1 || true
    uv run pytest tests/e2e/test_floci_integration.py -v -m aws --no-cov

# ─── DOCKER & RELEASE ──────────────────────────────────────────────────────

# Build deployment image for release audit
docker-build-image tag="api-observatory:local":
    docker build -t {{tag}} .

# MVP deployment image size audit (informational; functionality first)
docker-audit-size image="api-observatory:local":
    #!/usr/bin/env bash
    set -euo pipefail
    SIZE_BYTES=$(docker image inspect {{image}} | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["Size"])')
    SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
    LIMIT_MB=${DOCKER_IMAGE_SIZE_LIMIT_MB:-1500}
    echo "Image {{image}} size: ${SIZE_MB}MB"
    if (( SIZE_MB > LIMIT_MB )); then
        echo "WARNING: image exceeds ${LIMIT_MB}MB budget (allowed for MVP while functionality is prioritized)" >&2
        exit 0
    fi
    echo "Image size check passed"

# Fail if CRITICAL CVEs are found (requires Trivy compose service)
docker-scan-image image="api-observatory:local":
    docker compose --profile security run --rm trivy image \
        --scanners vuln \
        --severity CRITICAL \
        --ignore-unfixed \
        --timeout 15m \
        --exit-code 1 \
        {{image}}
    echo "No CRITICAL CVEs detected"

# Phase 13a deployment image verification
deploy-audit tag="api-observatory:local":
    just docker-build-image {{tag}}
    just docker-audit-size {{tag}}
    just docker-scan-image {{tag}}

# ─── INFRASTRUCTURE & SANDBOX ──────────────────────────────────────────────

# Terraform helper variables
TF_DIR := "infra/terraform/environments/dev"

# ─── Preflight checks ───────────────────────────────────────────────────────

# Preflight: verify Terraform files exist
tf-preflight:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v terraform &> /dev/null; then
        echo "❌ Terraform CLI not installed. Install via: brew install terraform" >&2
        exit 1
    fi
    # Ensure at least one backend file exists (local or aws)
    if [ ! -f {{TF_DIR}}/backend.local.hcl ] && [ ! -f {{TF_DIR}}/backend.aws.hcl ]; then
        echo "Missing backend file in {{TF_DIR}} (backend.local.hcl or backend.aws.hcl)." >&2
        echo "Create one from the corresponding example before running terraform commands." >&2
        exit 1
    fi
    # Ensure at least one tfvars file exists
    if [ ! -f {{TF_DIR}}/terraform.tfvars ] && [ ! -f {{TF_DIR}}/terraform.aws.tfvars ] && [ ! -f {{TF_DIR}}/terraform.floci.tfvars ]; then
        echo "Missing terraform var files in {{TF_DIR}} (terraform.tfvars, terraform.aws.tfvars, or terraform.floci.tfvars)." >&2
        echo "Create one from the corresponding example before running terraform commands." >&2
        exit 1
    fi

# ─── Floci / AWS Sandbox (Docker-based) ─────────────────────────────────────

# Start Floci compose service
floci-start:
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

# Stop Floci compose service and ECR registry
floci-stop:
    #!/usr/bin/env bash
    docker compose down floci
    docker stop floci-ecr-registry 2>/dev/null || true
    docker rm floci-ecr-registry 2>/dev/null || true

# Check Floci status
floci-status:
    docker ps --filter "name=floci"

# Full sandbox startup
sandbox-up: floci-start

# Tear down sandbox
sandbox-down: floci-stop

# Reset sandbox to a clean state
sandbox-reset: floci-stop floci-start

# ─── Terraform: Floci (local backend) ────────────────────────────────────────

# Terraform init for Floci (local backend)
tf-init: tf-preflight
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    unset AWS_PROFILE
    cd {{TF_DIR}}
    export TF_IN_AUTOMATION=1
    BACKEND_BUCKET=$(grep -E '^\s*bucket\s*=' backend.local.hcl | head -n1 | sed -E 's/^\s*bucket\s*=\s*"([^\"]+)".*/\1/')
    if [ -n "$BACKEND_BUCKET" ]; then
        aws s3 mb "s3://$BACKEND_BUCKET" >/dev/null 2>&1 || true
    fi
    terraform init -reconfigure -upgrade -backend-config=backend.local.hcl

# Terraform plan (Floci environment). Run 'just tf-init' once before first plan.
tf-plan-local:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    export TF_IN_AUTOMATION=1
    cd {{TF_DIR}}
    terraform validate
    terraform plan \
      -input=false \
      -var-file=terraform.tfvars \
      -var-file=terraform.floci.tfvars \
      -out=tfplan

# Terraform apply (Floci). Requires tfplan from 'just tf-plan-local'.
tf-apply-local:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_DIR}}
    terraform apply tfplan

# Show current Terraform state (Floci backend)
tf-show-local:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_DIR}}
    terraform show

# Show list of resources in Terraform state (Floci backend)
tf-state-list:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_DIR}}
    terraform state list

# Terraform destroy (Floci)
tf-destroy-local:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_DIR}}
    export TF_IN_AUTOMATION=1
    terraform destroy -auto-approve -lock=false \
      -var-file=terraform.tfvars \
      -var-file=terraform.floci.tfvars

# Fresh end-to-end local infra loop (clean sandbox -> plan -> apply)
tf-apply-local-fresh: sandbox-reset
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    just tf-plan-local
    just tf-apply-local

# ─── Terraform: AWS Dev (profile-driven) ────────────────────────────────────

# Terraform plan for AWS dev
tf-plan-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{TF_DIR}}
    export TF_IN_AUTOMATION=1
    terraform init -reconfigure -upgrade -backend-config=backend.aws.hcl
    terraform validate
    terraform plan \
      -input=false \
      -lock-timeout=30m \
      -var-file=terraform.tfvars \
      -var-file=terraform.aws.tfvars \
      -out=tfplan.aws

# Terraform apply for AWS dev
tf-apply-dev: tf-plan-dev
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{TF_DIR}}
    export TF_IN_AUTOMATION=1
    terraform apply -lock-timeout=30m tfplan.aws
