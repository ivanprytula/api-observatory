#!/usr/bin/env bash
set -euo pipefail

# Deploy ingestor + dashboard to local Floci/ECS sandbox.
#
# Prerequisites:
#   - Floci running:  docker compose --profile aws up -d floci
#   - Terraform applied: just tf-apply
#   - Docker daemon available
#
# Sandbox mode skips ECR and data-plane modules (db/redis/redpanda come from compose).
# ECS_MOCK=true makes tasks go straight to RUNNING without pulling images,
# so tags are metadata only. Smoke tests hit localhost URLs (real compose services).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

AWS_REGION="${AWS_REGION:-eu-central-1}"
ECR_ENDPOINT="${ECR_ENDPOINT:-localhost:4566}"
IMAGE_TAG="${IMAGE_TAG:-develop}"
CLUSTER="${CLUSTER:-data-zoo-sandbox}"

# Hardcoded Floci ECR loopback URIs (ECR module disabled in sandbox tfvars).
# With ECS_MOCK=true these are metadata only — no actual pull happens.
INGESTOR_IMAGE="000000000000.dkr.ecr.eu-central-1.localhost:5100/data-zoo/ingestor:${IMAGE_TAG}"
DASHBOARD_IMAGE="000000000000.dkr.ecr.eu-central-1.localhost:5100/data-zoo/dashboard:${IMAGE_TAG}"

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }

AWS_ARGS=(--endpoint-url "http://${ECR_ENDPOINT}" --region "${AWS_REGION}")

# ── Preflight ──────────────────────────────────────────────────────────

info "Preflight checks"
require_cmd docker
require_cmd aws

if ! docker ps --filter "name=api-obs-floci" --filter "status=running" --format '{{.Names}}' | grep -q .; then
  fail "Floci is not running. Start it with: docker compose --profile aws up -d floci"
fi

if ! aws ecs list-clusters "${AWS_ARGS[@]}" 2>/dev/null | grep -q "${CLUSTER}"; then
  fail "ECS cluster '${CLUSTER}' not found. Apply Terraform first: just tf-apply"
fi

# ── Build and tag images ───────────────────────────────────────────────

info "Building ingestor: ${INGESTOR_IMAGE}"
docker build -t "${INGESTOR_IMAGE}" -f Dockerfile .

info "Building dashboard: ${DASHBOARD_IMAGE}"
docker build -t "${DASHBOARD_IMAGE}" -f services/dashboard/Dockerfile .

# ── Deploy to ECS ──────────────────────────────────────────────────────
# ECS_MOCK=true in docker-compose.yml means tasks go straight to RUNNING.
# --force-new-deployment triggers a new task set.

info "Triggering ingestor deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service ingestor \
  --force-new-deployment \
  "${AWS_ARGS[@]}" || warn "update-service ingestor failed"

# Note: aws ecs wait services-stable hangs with Floci mock mode
# (returns null fields the CLI can't parse). Skip it.

info "Triggering dashboard deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service dashboard \
  --force-new-deployment \
  "${AWS_ARGS[@]}" || warn "update-service dashboard failed"

# ── Smoke tests ────────────────────────────────────────────────────────
# In mock mode there are no real containers behind the ALB, so smoke tests
# hit the compose services directly on localhost (the actual running code).

info "Smoke tests (compose services on localhost)"

if curl --fail --max-time 5 http://localhost:8000/health 2>/dev/null; then
  info "Ingestor /health OK (localhost:8000)"
elif curl --fail --max-time 5 http://localhost:8000/readyz 2>/dev/null; then
  info "Ingestor /readyz OK (localhost:8000)"
else
  warn "Ingestor not reachable on localhost:8000 — is 'just up' running?"
fi

if curl --fail --max-time 5 http://localhost:8501/_stcore/health 2>/dev/null; then
  info "Dashboard /_stcore/health OK (localhost:8501)"
else
  warn "Dashboard not reachable on localhost:8501 — is it running?"
fi

info "Sandbox deploy complete"
echo ""
echo "Access:"
echo "  API (compose):      http://localhost:8000   (just up)"
echo "  Dashboard (compose): http://localhost:8501 (just up)"
echo ""
echo "ECS service status (mock mode — no real containers):"
echo "  aws ecs describe-services --cluster ${CLUSTER} --services ingestor,dashboard \\"
echo "    --endpoint-url http://${ECR_ENDPOINT} --region ${AWS_REGION}"
