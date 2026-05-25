# Core services (database, message broker, API)
up:
    docker compose up -d db redis redpanda ingestor mongodb

# Vector search stack
up-vector:
    docker compose --profile vector up -d

# Monitoring stack (Prometheus, Grafana, Alertmanager)
up-monitor:
    docker compose --profile monitoring up -d

# Full stack with all workers and webhooks
up-all:
    docker compose --profile vector --profile monitoring --profile worker --profile webhook up -d

# Django catalog portal
up-portal:
    docker compose --profile portal up -d portal

# View logs for a specific service
logs svc:
    docker compose logs -f {{svc}}

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

# Run database migrations
migrate:
    uv run alembic upgrade head

# Create the default admin user. After db-reset this is always 201; outside tests 409 is also fine.
create-admin:
    curl -sf -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/register \
      -H "Content-Type: application/json" \
      -d '{"username":"admin","email":"admin@example.com","password":"admin123","role":"admin"}' | \
      grep -qE "^(201|409)" && echo "admin user ready" || (echo "create-admin failed" >&2; exit 1)

# Stop all services
down:
    docker compose down

# Local environment doctor (requirements + local artifact folders)
doctor:
    bash scripts/setup/00-doctor.sh

# Floci AWS sandbox
up-aws:
    docker compose --profile aws up -d floci
    @echo "⏳ Waiting for Floci to be ready..."
    @bash -c 'for i in $(seq 1 30); do curl -sf http://localhost:4566/_floci/health > /dev/null 2>&1 && exit 0 || sleep 1; done; echo "⚠️  Floci health check timed out after 30s" >&2; exit 1'
    awslocal s3 mb s3://data-pipeline-local || true
    awslocal sqs create-queue --queue-name pipeline-events || true
    awslocal dynamodb create-table --table-name records --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH --billing-mode PAY_PER_REQUEST || true
    @echo "✅ Floci up and configured"

# Test Floci connectivity
test-aws-connectivity:
    awslocal s3 ls
    awslocal sqs list-queues
    awslocal dynamodb list-tables
    @echo "✅ AWS connectivity verified"

# Terraform initialization (Floci)
tf-init:
    cd infra/terraform && terraform init -upgrade

# Terraform plan for Floci environment
tf-plan-local:
    cd infra/terraform && TF_VAR_environment=floci tflocal plan -out=tfplan

# Terraform apply for Floci environment
tf-apply-local:
    cd infra/terraform && TF_VAR_environment=floci tflocal apply tfplan

# Terraform destroy for Floci environment
tf-destroy-local:
    cd infra/terraform && TF_VAR_environment=floci tflocal destroy -auto-approve

# Full sandbox startup
sandbox-up: up-aws
    @echo "✅ Sandbox ready. Run: just sandbox-test"

# Run Floci integration tests
sandbox-test: test-aws-connectivity
    @echo "Running Floci integration tests..."
    uv run pytest tests/e2e/test_floci_integration.py -v -m aws

# Tear down sandbox
sandbox-down:
    docker compose --profile aws down -v
    @echo "✅ Sandbox torn down"

# ─── Backup & Restore ──────────────────────────────────────────────────────────

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

# ─── API Testing (Bruno) ───────────────────────────────────────────────────────

# Verify the stack is healthy. Fails fast if not up.
api-check:
    @curl -sf http://localhost:8000/readyz > /dev/null && echo "stack ready" || (echo "stack not ready — run: just up" >&2; exit 1)

# Wipe DB to a clean empty state: stop → remove container+volume → restart → wait.
db-reset:
    docker compose rm -sfv ingestor db
    docker compose up -d db
    @bash -c 'until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done'
    docker compose up -d ingestor
    @bash -c 'until curl -sf http://localhost:8000/readyz > /dev/null 2>&1; do sleep 1; done && echo "stack ready"'

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

# E2E smoke test: clean DB → seed admin + source → run Bruno collections → clean DB.
api-test:
    #!/usr/bin/env bash
    set -eo pipefail
    trap 'just db-reset' EXIT
    just db-reset
    just create-admin
    just seed-source
    cd bruno && bru run . -r --env local
