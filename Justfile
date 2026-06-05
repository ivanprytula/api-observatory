# ─── SETUP & HEALTH CHECK ──────────────────────────────────────────────────

# Local environment doctor (requirements + local artifact folders)
doctor:
    bash scripts/setup/00-doctor.sh

# Verify the stack is healthy. Fails fast if not up.
api-check:
    @curl -sf http://localhost:8000/readyz > /dev/null && echo "stack ready" || (echo "stack not ready — run: just up" >&2; exit 1)

# ─── FEATURE DEVELOPMENT (real infra containers) ────────────────────────────
# Normal daily workflow: just up → code → just test-unit → just api-test → just down

# Core MVP services (db, redis, redpanda, ingestor)
up:
    docker compose up -d db redis redpanda ingestor

# Security scan stack (Trivy)
up-security:
    docker compose --profile security run --rm trivy image api-observatory:local

# View logs for a specific service
logs svc:
    docker compose logs -f {{svc}}

# Stop all services
down:
    docker compose down

# Start full stack with nginx HTTPS proxy (requires certificates — run 02-setup-local-https.sh first)
up-https:
    #!/usr/bin/env bash
    set -euo pipefail
    # Check if ports 80/443 are in use by another process
    if curl -sf http://localhost:80 >/dev/null 2>&1 || curl -sf https://localhost >/dev/null 2>&1; then
        echo "ERROR: Ports 80 or 443 already in use (Apache/nginx or other service)." >&2
        echo "Stop conflicting services or run: just down" >&2
        exit 1
    fi
    docker compose --profile https up -d

# Stop and remove nginx container
down-https:
    docker compose --profile https down nginx

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
    #!/usr/bin/env bash
    set -euo pipefail
    TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/token \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -d 'username=admin&password=admin123' | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
    for payload in \
        '{"name":"httpbin","base_url":"https://httpbin.org","health_check_path":"/get","probe_interval_seconds":10,"is_active":true}' \
        '{"name":"jsonplaceholder","base_url":"https://jsonplaceholder.typicode.com","health_check_path":"/posts/1","probe_interval_seconds":10,"is_active":true}' \
        '{"name":"postman-echo","base_url":"https://postman-echo.com","health_check_path":"/get","probe_interval_seconds":10,"is_active":true}'; do
        curl -sf -X POST http://localhost:8000/api/v1/sources \
          -H "Authorization: Bearer $TOKEN" \
          -H 'Content-Type: application/json' \
          -d "$payload" > /dev/null
    done
    echo "seed-demo complete"

# Seed probe sources: one healthy (httpbin), one failing (unreachable dead URL).
# Demonstrates success/failure contrast in the Source Health and Drift Events panels.
seed-probes:
    #!/usr/bin/env bash
    set -euo pipefail
    TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/token \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -d 'username=admin&password=admin123' | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
    # Healthy source — should produce reachable=true, low latency
    curl -sf -X POST http://localhost:8000/api/v1/sources \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"name":"probe-ok","base_url":"https://httpbin.org","health_check_path":"/get","probe_interval_seconds":10,"sla_ms":2000,"is_active":true}' > /dev/null
    # Failing source — unreachable host, produces reachable=false and SLA breach
    curl -sf -X POST http://localhost:8000/api/v1/sources \
      -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' \
      -d '{"name":"probe-fail","base_url":"https://this-host-does-not-exist.invalid","health_check_path":"/","probe_interval_seconds":10,"sla_ms":100,"is_active":true}' > /dev/null
    echo "seed-probes complete — wait ~10s for first probe cycle"

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

# Run unit tests only (no DB, no Docker required)
test-unit:
    uv run pytest -m unit -q

# Run integration tests (requires Postgres + Redis; testcontainers auto-provisions if Docker available)
test-integration:
    uv run pytest -m integration -q

# Run e2e tests (requires full stack; skipped by default in CI)
test-e2e:
    uv run pytest -m e2e -q

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
    @docker image inspect {{tag}} --format 'Digest: {{{{index .RepoDigests 0}}}}' 2>/dev/null || \
      docker inspect --format 'ID: {{{{.ID}}}}' {{tag}}

# ─── PRE-DEPLOY SANDBOX (Floci — validate AWS-integrated flows before real cloud) ───
# Use these recipes ONLY when rehearsing AWS service calls (S3, SQS) or Terraform plans.
# Feature development does NOT require the sandbox — use `just up` instead.

# Terraform helper variables
TF_DIR         := "infra/terraform/environments/dev"
TF_SANDBOX_DIR := "infra/terraform/environments/sandbox"

# ─── Preflight checks ───────────────────────────────────────────────────────

# Preflight: verify Terraform files exist
tf-preflight:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v terraform &> /dev/null; then
        echo "❌ Terraform CLI not installed. Install via: brew install terraform" >&2
        exit 1
    fi
    # Ensure at least one backend file exists (sandbox or aws)
    if [ ! -f {{TF_DIR}}/backend.aws.hcl ]; then
        echo "Missing backend.aws.hcl in {{TF_DIR}}." >&2
        echo "Create one from backend.aws.hcl.example before running terraform commands." >&2
        exit 1
    fi
    # Ensure tfvars file exists
    if [ ! -f {{TF_DIR}}/terraform.tfvars ] && [ ! -f {{TF_DIR}}/terraform.aws.tfvars ]; then
        echo "Missing tfvars in {{TF_DIR}} (terraform.tfvars or terraform.aws.tfvars)." >&2
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

# ─── End-to-End Sandbox Testing (Floci + Ingestor + Streamlit) ─────────────

# Start ingestor service locally with Floci AWS endpoints (live reload).
# Run AFTER sandbox-with-ingestor-prep has completed in Terminal 1.
# Usage: just ingestor-start (Terminal 2)
ingestor-start:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    echo "Starting ingestor with Floci endpoints..."
    echo "AWS_ENDPOINT_URL=$AWS_ENDPOINT_URL"
    echo "AWS_PROFILE=$AWS_PROFILE"
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# Start streamlit dashboard (requires ingestor running on localhost:8000)
# Usage: just streamlit-start (run in a separate terminal)
streamlit-start:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting streamlit dashboard..."
    streamlit run streamlit_app.py --server.port=8501

# End-to-end Floci sandbox workflow: Setup for probe → S3 → drift analysis
# Workflow:
#   Terminal 1: just sandbox-with-ingestor-prep  ← infrastructure only (this recipe)
#   Terminal 2: just ingestor-start              ← migrate + local uvicorn with live reload
#   Terminal 1: just sandbox-seed                ← create-admin + seed-demo (after ingestor is up)
#   Terminal 3: just streamlit-start             ← Streamlit dashboard
sandbox-with-ingestor-prep:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting Floci AWS emulator..."
    just sandbox-up
    echo "Starting infrastructure (db, redis, redpanda)..."
    docker compose up -d db redis redpanda
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    echo ""
    echo "Infrastructure ready. Next steps:"
    echo "  Terminal 2:  just ingestor-start"
    echo "  Then here:   just sandbox-seed"
    echo "  Terminal 3:  just streamlit-start"
    echo ""

# Seed admin user and demo sources. Waits for ingestor readiness then seeds.
sandbox-seed:
    #!/usr/bin/env bash
    set -euo pipefail
    until curl -sf http://localhost:8000/health > /dev/null 2>&1; do sleep 1; done
    just create-admin
    just seed-demo


# ─── Terraform: Sandbox (local emulator) ────────────────────────────────────

# Init sandbox backend. Requires: sandbox-up.
tf-sandbox-init:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    unset AWS_PROFILE
    cd {{TF_SANDBOX_DIR}}
    export TF_IN_AUTOMATION=1
    BACKEND_BUCKET=$(grep -E '^\s*bucket\s*=' backend.hcl | head -n1 | sed -E 's/^\s*bucket\s*=\s*"([^\"]+)".*/\1/')
    if [ -n "$BACKEND_BUCKET" ]; then
        if ! aws s3 ls "s3://$BACKEND_BUCKET" >/dev/null 2>&1; then
            echo "Creating S3 bucket: $BACKEND_BUCKET"
            aws s3 mb "s3://$BACKEND_BUCKET" || { echo "ERROR: Failed to create bucket (ensure sandbox-up is running)"; exit 1; }
        else
            echo "Bucket $BACKEND_BUCKET exists"
        fi
    fi
    terraform init -reconfigure -upgrade -backend-config=backend.hcl

# Terraform plan for sandbox. Run 'just tf-sandbox-init' once first.
tf-sandbox-plan:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    export TF_IN_AUTOMATION=1
    cd {{TF_SANDBOX_DIR}}
    terraform validate
    terraform plan \
      -input=false \
      -var-file=terraform.tfvars \
      -out=tfplan

# Apply saved sandbox plan.
tf-sandbox-apply:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_SANDBOX_DIR}}
    terraform apply tfplan

# Show current sandbox Terraform state.
tf-sandbox-show:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_SANDBOX_DIR}}
    terraform show

# List resources in sandbox Terraform state.
tf-sandbox-state-list:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_SANDBOX_DIR}}
    terraform state list

# Destroy all sandbox resources.
tf-sandbox-destroy:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    cd {{TF_SANDBOX_DIR}}
    export TF_IN_AUTOMATION=1
    terraform destroy -auto-approve -lock=false -var-file=terraform.tfvars

# Fresh end-to-end sandbox loop: clean emulator -> init -> plan -> apply.
tf-sandbox-fresh: sandbox-reset
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    just tf-sandbox-init
    just tf-sandbox-plan
    just tf-sandbox-apply

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
