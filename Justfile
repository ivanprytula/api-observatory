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

api-check:
    @bash -c 'source scripts/daily/local-url.sh; if curl_local -sf "$(local_api_url /readyz)" > /dev/null; then echo "stack ready"; else echo "stack not ready — run: just up or LOCAL_API_SCHEME=https just up-https" >&2; exit 1; fi'

floci-health:
    @bash -c 'source scripts/daily/local-url.sh; if curl_local -sf "$(local_api_url /health)" > /dev/null; then echo "API: healthy"; else echo "API: not responding"; fi'
    @curl -sf http://127.0.0.1:4566/_floci/health > /dev/null && echo "Floci: healthy" || echo "Floci: not responding"

# ─── DAILY DEV FLOWS ─────────────────────────────────────────────────────────
#
# Primary loops:
#   just dev             → uvicorn + Compose data-plane (local)
#   just up              → Compose data-plane only (containerized)
#   just floci-*         → Full Floci sandbox (training playground)
#   TF_ENV=dev just deploy → Promote to real AWS dev cloud
#
# Floci is only started when you explicitly need S3/SQS/ECS-shaped APIs.

# 2a) Local development (uvicorn + live reload)
# ─────────────────────────────────────────────

# Start uvicorn with live reload against Compose data-plane.
# Set LOCAL_API_SCHEME=https and run just up-https when API clients need edge HTTPS.
dev:
    @just stack-info
    docker compose up -d --build db cache broker dashboard
    docker compose stop ingestor >/dev/null 2>&1 || true
    docker compose rm -f ingestor >/dev/null 2>&1 || true
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# 2b) Containerized development (Compose data-plane only)
# ─────────────────────────────────────────────────────────

# Start Compose data-plane (db, cache, broker, ingestor, dashboard).
# Use LOCAL_API_SCHEME=https just up-https for edge HTTPS parity.
up:
    @just stack-info
    docker compose up -d --build db cache broker ingestor dashboard

# Start Compose data-plane plus edge HTTPS proxy.
up-https:
    @just stack-info
    docker compose --profile https up -d --build db cache broker ingestor dashboard edge

# Stop everything.
down:
    docker compose down
    # docker compose --profile https down edge   # down-https (stops only HTTPS edge)

# Stop HTTPS edge only (data-plane keeps running).
down-https:
    docker compose --profile https down edge

# Start Compose + Floci (on demand).
# Floci service must be uncommented in docker-compose.yml.
up-floci:
    docker compose up -d floci

# Stop Floci only (Compose data-plane keeps running).
down-floci:
    docker compose down floci

# Full containerized stack (db + cache + broker + ingestor + dashboard).
dev-dashboard:
    @just stack-info
    docker compose up -d --build db cache broker ingestor dashboard
    just _local_wait_ready
    echo "stack ready"

# Reset DB and ingestor containers (keep Floci state intact if running).
db-reset:
    @just stack-info
    docker compose rm -sfv ingestor db || true
    docker compose up -d --build db cache broker ingestor dashboard
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
    # docker compose up -d floci   # minimal: Floci-only start (like up-floci)
    for i in $(seq 1 60); do
        if curl -sf http://127.0.0.1:4566/_floci/health > /dev/null 2>&1; then
            source scripts/aws-env.sh
            aws s3 mb s3://api-observatory-local >/dev/null 2>&1 || true
            aws sqs create-queue --queue-name pipeline-events >/dev/null 2>&1 || true
            break
        fi
        sleep 1
    done
    docker compose up -d --build db cache broker ingestor dashboard
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    just _sandbox-seed

# Stop Floci only (Compose data-plane keeps running).
floci-down:
    docker compose down floci

# Restart Floci services only (preserves DB state, no re-seeding).
floci-restart:
    docker compose up -d floci

# Wipe Floci state (buckets, queues, task history) and restart clean.
floci-reset:
    docker compose down floci
    just floci-up

# Full destroy: terraform destroy + stop Floci + stop Compose.
cleanup:
    TF_ENV=sandbox just tf-destroy || true
    docker compose down

# Start uvicorn with Floci-shaped env (S3 + SQS + ECS APIs).
floci-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    @just stack-info
    source scripts/aws-env.sh
    docker compose up -d db cache broker dashboard
    docker compose stop ingestor >/dev/null 2>&1 || true
    docker compose rm -f ingestor >/dev/null 2>&1 || true
    until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; do sleep 1; done
    just migrate
    uv run uvicorn services.ingestor.main:app --reload --port 8000

# Run Floci-specific E2E tests (AWS emulator required).
floci-test:
    just _sandbox-infra
    just _sandbox-seed
    source scripts/aws-env.sh
    uv run pytest tests/e2e/test_floci_integration.py -v -m aws --no-cov

# Build + push to Floci ECR + ECS deploy.
floci-deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/aws-env.sh
    bash scripts/sandbox/deploy.sh

# 2d) AWS Deploy (dev → ECS/Fargate)
# ─────────────────────────────────────

# Terraform apply on dev, then ECS service restart.
deploy-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    TF_ENV=dev just tf-apply
    echo "TODO: wire ECS service update here when cluster is provisioned"
    echo "  aws ecs update-service --cluster dev --service ingestor --force-new-deployment"
    echo "  aws ecs wait services-stable --cluster dev --services ingestor"

# ─── STACK AWARENESS ──────────────────────────────────────────────────────────

# Print the active stack configuration based on environment variables and Docker state.
stack-info:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="$(pwd)"
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
    echo "  MinIO endpoint  : ${MINIO_ENDPOINT:-unset}"
    echo "  INGESTOR_URL    : $(local_api_base_url)"
    echo "======================"

# ─── BACKWARD-COMPATIBLE SANDBOX ALIASES ──────────────────────────────────────
# Old sandbox-* names delegate to floci-*. Remove when no longer referenced.

sandbox:        floci-test
sandbox-up:     floci-up
sandbox-down:   floci-down
sandbox-reset:  floci-reset
sandbox-deploy: floci-deploy
sandbox-dev:    floci-dev

# ─── INFRASTRUCTURE & IMAGES ──────────────────────────────────────────────────
#
# 3a) Terraform (unified — sandbox or dev via TF_ENV)
# 3b) Docker Images & Audit
# 3c) Backups & Restore
# 3d) Ansible Automation

# 3a) Terraform
# ───────────────

# Usage:
#   just tf init                   # auto-detects env from TF_ENV or cwd
#   just tf plan                   # same
#   just tf apply                  # same
#   TF_ENV=dev just tf plan        # force dev environment
#   just tf fresh                  # init → plan → apply (sandbox by default)

tf cmd:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    CMD="{{cmd}}"
    if [ "$ENV" = "dev" ]; then
        DIR="infra/terraform/environments/dev"
        source scripts/aws-env.sh 2>/dev/null || true
    else
        DIR="infra/terraform/environments/sandbox"
        source scripts/aws-env.sh
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

# Backward-compatible aliases
tf-init:
    just tf init

tf-validate:
    just tf validate

tf-plan:
    just tf plan

tf-apply:
    just tf apply

tf-show:
    just tf show

tf-destroy:
    just tf destroy

tf-fresh:
    just tf fresh

# ─── TERRAVISION (architecture diagrams from IaC) ──────────────────────────────
#
# Generate professional cloud architecture diagrams from Terraform code.
# Install: `uv sync --group dev` (terravision is in the dev dependency group)
# Docs: https://patrickchugh.github.io/terravision
#
# Usage:
#   just tf-diagram               # PNG by default
#   just tf-diagram svg           # SVG output
#   just tf-diagram png           # PNG output
#   just tf-diagram html          # Interactive HTML output

tf-diagram format="png":
    #!/usr/bin/env bash
    set -euo pipefail
    FORMAT="${format:-png}"
    ENV="${TF_ENV:-sandbox}"
    if [ "$ENV" = "dev" ]; then
        DIR="infra/terraform/environments/dev"
    else
        DIR="infra/terraform/environments/sandbox"
    fi
    mkdir -p .local-dev/diagrams
    OUTFILE=".local-dev/diagrams/data-zoo-${ENV}"
    PLANFILE=".local-dev/tfplan-${ENV}.json"
    GRAPHFILE=".local-dev/graph-${ENV}.dot"
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
                echo "HCL parsing may fail on complex for loops. Try: just tf-diagram-prepare && just tf-diagram html" >&2
                exit $EXIT_CODE
            fi
            echo "Interactive HTML diagram written to ${OUTFILE}.html"
        else
            set +e
            uv run terravision draw --source "$DIR" --format "$FORMAT" --outfile "$OUTFILE"
            EXIT_CODE=$?
            set -e
            if [ $EXIT_CODE -ne 0 ]; then
                echo "HCL parsing may fail on complex for loops. Try: just tf-diagram-prepare && just tf-diagram ${FORMAT}" >&2
                exit $EXIT_CODE
            fi
            echo "Diagram written to ${OUTFILE}.${FORMAT}"
        fi
    fi

# Generate pre-plan files for terravision (avoids HCL parsing issues).
tf-diagram-prepare:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    PLANDIR="infra/terraform/environments/${ENV}"
    if [ -f "/tmp/tfplan.bin" ]; then
        PLAN_SRC="/tmp/tfplan.bin"
    elif [ -f "${PLANDIR}/tfplan" ]; then
        PLAN_SRC="${PLANDIR}/tfplan"
    else
        echo "No plan binary found. Run 'just tf plan' first to generate a plan." >&2
        exit 1
    fi
    mkdir -p .local-dev
    echo "Extracting plan JSON from $PLAN_SRC..."
    cd "$PLANDIR"
    terraform show -json "$PLAN_SRC" > "${OLDPWD}/.local-dev/tfplan-${ENV}.json"

    echo "Generating graph..."
    if ! terraform graph > "${OLDPWD}/.local-dev/graph-${ENV}.dot" 2>/dev/null; then
        echo "Note: terraform graph failed (backend may not be initialized)." >&2
        echo "To fix: run 'just tf init' first." >&2
        echo 'digraph G {}' > "${OLDPWD}/.local-dev/graph-${ENV}.dot"
    fi
    echo "Plan files generated for terravision in .local-dev/"

tf-diagram-prepare-from-json:
    #!/usr/bin/env bash
    set -euo pipefail
    ENV="${TF_ENV:-sandbox}"
    PLANDIR="infra/terraform/environments/${ENV}"
    PLANFILE=".local-dev/tfplan-${ENV}.json"
    if [ ! -f "$PLANFILE" ]; then
        echo "Plan file not found: $PLANFILE" >&2
        echo "Create it with: cd $PLANDIR && terraform show -json tfplan > ../$PLANFILE" >&2
        exit 1
    fi
    if [ ! -s "$PLANFILE" ]; then
        echo "Plan file is empty: $PLANFILE" >&2
        exit 1
    fi
    if ! uv run python3 -c "import json; json.load(open('$PLANFILE'))" 2>/dev/null; then
        echo "Plan file is not valid JSON: $PLANFILE" >&2
        echo "Regenerate it with: cd $PLANDIR && terraform show -json tfplan > ../$PLANFILE" >&2
        exit 1
    fi
    mkdir -p .local-dev/diagrams
    echo "Plan file ready: $PLANFILE"
    echo "Now run: just tf-diagram html"

tf-diagram-svg:
    just tf-diagram svg

tf-diagram-png:
    just tf-diagram png

tf-diagram-html:
    just tf-diagram html

# 3b) Docker Images & Audit
# ──────────────────────────

# Buildability guards (fail fast with a clear message if Dockerfile is missing).
_check-ingestor-dockerfile:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f Dockerfile ]; then
        echo "Missing ingestor Dockerfile at ./Dockerfile" >&2
        echo "Create it or run from the repo root." >&2
        exit 1
    fi

_check-dashboard-dockerfile:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f services/dashboard/Dockerfile ]; then
        echo "Missing dashboard Dockerfile at services/dashboard/Dockerfile" >&2
        echo "Run the dashboard move or restore from git history." >&2
        exit 1
    fi

docker-build-image tag="api-observatory:local":
    @just _check-ingestor-dockerfile
    docker build -t {{tag}} .

docker-build-dashboard tag="api-observatory-dashboard:local":
    @just _check-dashboard-dockerfile
    docker build -t {{tag}} -f services/dashboard/Dockerfile .

# One-shot audit: build → size check → CRITICAL CVE scan
# Comment out the steps you don't need, or keep all three for a full audit.
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

# 3c) Backups & Restore
# ──────────────────────

# Uncomment the variant to change storage target (local is default).
backup:
    bash infra/scripts/backup.sh
    # BACKUP_STORAGE=s3 bash infra/scripts/backup.sh       # → backup-s3
    # BACKUP_STORAGE=both bash infra/scripts/backup.sh      # → backup-both

backup-s3:
    BACKUP_STORAGE=s3 bash infra/scripts/backup.sh

backup-both:
    BACKUP_STORAGE=both bash infra/scripts/backup.sh

# For S3 restore, use restore-s3-postgres instead (different CLI signature).
restore-postgres file="":
    bash infra/scripts/restore.sh postgres {{file}}

restore-s3-postgres s3uri:
    bash infra/scripts/restore.sh postgres --from-s3 {{s3uri}}

# 3d) Ansible Automation
# ───────────────────────

ansible-requirements:
    cd infra/ansible && ansible-galaxy collection install -r requirements.yml

ansible-bootstrap:
    cd infra/ansible && ansible-playbook playbooks/bootstrap.yml -i inventory/hosts.yml \
      --ask-vault-pass --limit dev

ansible-provision-ec2:
    cd infra/ansible && ansible-playbook playbooks/provision-ec2.yml -inventory/aws_ec2.yml \
      --limit dev --ask-become-pass --ask-vault-pass

ansible-sandbox-host:
    cd infra/ansible && ansible-playbook playbooks/sandbox-host.yml -i inventory/hosts.yml \
      --limit dev --ask-become-pass

ansible-local-dev:
    cd infra/ansible && ansible-playbook playbooks/local-dev.yml -i inventory/hosts.yml \
      --limit dev --ask-become-pass

ansible-ecs-host:
    cd infra/ansible && ansible-playbook playbooks/ecs-host.yml -i inventory/aws_ec2.yml \
      --limit dev --ask-become-pass --ask-vault-pass

# Drift check (read-only, safe to run repeatedly)
ansible-drift:
    cd infra/ansible && ansible-playbook playbooks/drift-check.yml -i inventory/hosts.yml \
      --ask-vault-pass --limit dev

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

# Deprecated: use psql-safe instead to avoid accidental prod shell access.
# To re-enable the old unsafe path, uncomment below and comment psql-safe.
# db-shell:
#     @echo "WARNING: db-shell opens an interactive shell without safety checks." >&2
#     @echo "  Use 'just psql-safe' instead — it blocks accidental prod shells." >&2
#     docker compose exec db psql -U postgres -d api_observatory

db-shell:
    @echo "WARNING: db-shell opens an interactive shell without safety checks." >&2
    @echo "  Use 'just psql-safe' instead — it blocks accidental prod shells." >&2
    docker compose exec db psql -U postgres -d api_observatory

# Dump the local Compose DB to a timestamped SQL file (default: .local-dev/dumps/).
pg-dump file=".local-dev/dumps/api-observatory-$(date +%Y%m%d-%H%M%S).sql":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$(dirname "{{file}}")"
    docker compose exec -T db pg_dump -U postgres api_observatory > "{{file}}"
    echo "Dumped to {{file}} ($(wc -c < "{{file}}") bytes)"

# Restore a SQL dump into the local Compose DB (wipes public schema first).
pg-restore file="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{file}}" ] || [ ! -f "{{file}}" ]; then
        echo "Usage: just pg-restore <dump.sql>" >&2
        exit 1
    fi
    docker compose exec -T db psql -U postgres -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" api_observatory
    docker compose exec -T db psql -U postgres -d api_observatory < "{{file}}"
    echo "Restored from {{file}}"

# Restore a gzipped SQL dump from S3 into the local Compose DB.
pg-restore-from-s3 s3-uri="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{s3-uri}}" ]; then
        echo "Usage: just pg-restore-from-s3 s3://bucket/path/dump.sql.gz" >&2
        exit 1
    fi
    TMP="/tmp/api-obs-restore-$$.sql.gz"
    aws s3 cp "{{s3-uri}}" "$TMP"
    gunzip -c "$TMP" | docker compose exec -T db psql -U postgres -d api_observatory
    rm -f "$TMP"
    echo "Restored from {{s3-uri}}"

# Inject --endpoint-url when an AWS emulator is configured (Floci/localstack).
_aws-flags:
    @if [ -n "${AWS_ENDPOINT_URL:-}" ]; then echo --endpoint-url "$AWS_ENDPOINT_URL"; fi

# Mirror an S3 bucket (local or remote) to a local directory for offline browsing.
s3-dump-local bucket="api-observatory-local" dest=".local-dev/dumps/s3-$(date +%Y%m%d-%H%M%S)":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{dest}}"
    aws $(just _aws-flags) s3 cp "s3://{{bucket}}" "{{dest}}" --recursive
    echo "S3 mirrored to {{dest}} ($(find {{dest}} -type f | wc -l) files)"

# Upload a local directory to an S3 bucket (local or remote).
s3-restore-to-remote bucket="api-observatory-local" src=".local-dev/dumps/s3-YYYYMMDD-HHMMSS":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d "{{src}}" ]; then
        echo "Source directory {{src}} does not exist" >&2
        exit 1
    fi
    aws $(just _aws-flags) s3 cp "{{src}}" "s3://{{bucket}}/" --recursive

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
    just create-admin
    just seed-source
    BRUNO_BASE_URL="$(just _local_api_base_url)"
    cd bruno && bru run auth ops sources contracts scorecards websocket -r --env local --env-var "baseUrl=${BRUNO_BASE_URL}"

# Load test (k6). Requires k6 installed locally. Realistic CRUD scenario.
# Usage:
#   just test-load                    # defaults from scripts/daily/local-url.sh
#   just test-load BASE_URL=https://127.0.0.1 VUS=20 DURATION=60s
test-load:
    #!/usr/bin/env bash
    set -euo pipefail
    BASE_URL="${BASE_URL:-$(just _local_api_public_base_url)}"
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

# Logs / shell / restart for any Compose service.
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

migrate:
    uv run alembic upgrade head

# Private: wait for API, then seed admin + demo sources
_sandbox-seed:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/daily/local-url.sh
    until curl_local -sf "$(local_api_url /health)" > /dev/null 2>&1; do sleep 1; done
    just create-admin
    just seed-demo

# Private: start Floci + Docker infra for sandbox workflows
_sandbox-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    just sandbox-up
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

create-admin:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/daily/local-url.sh
    REGISTER_URL="$(local_api_url /api/v1/auth/register)"
    curl_local -sf -X POST "$REGISTER_URL" \
      -H 'Content-Type: application/json' \
      -d '{"username":"admin","password":"admin123","email":"admin@example.com","role":"admin"}' \
      >/dev/null 2>&1 || true
    if just _get_token >/dev/null 2>&1; then
        echo "admin user registered and verified"
    else
        echo "WARNING: admin registration completed but token verification failed" >&2
    fi

smoke-test base-url="{{_local_api_base_url}}" dashboard-url="{{_local_dashboard_url}}":
    bash scripts/smoke-test.sh {{base-url}} {{dashboard-url}}
