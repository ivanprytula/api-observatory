#!/usr/bin/env bash
set -euo pipefail

# Deploy ingestor + dashboard to local Floci/ECS sandbox.
#
# Prerequisites:
#   - Floci running:  docker compose --profile aws up -d floci
#   - Terraform applied: just tf-apply
#   - Docker daemon available (Floci mounts /var/run/docker.sock)
#
# How it works:
#   1. Read ECR repository URIs from Terraform output (Floci returns
#      loopback addresses like 000000000000.dkr.ecr.eu-central-1.localhost:5100/...)
#   2. Build images and tag them with the exact URI Terraform's task
#      definitions reference
#   3. Authenticate docker against Floci's real OCI registry
#   4. Push images (optional but validates the full push→pull path)
#   5. Trigger ECS update-service --force-new-deployment for both services
#   6. Wait for stability + smoke test the ALB

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

AWS_REGION="${AWS_REGION:-eu-central-1}"
ECR_ENDPOINT="${ECR_ENDPOINT:-localhost:4566}"
TF_DIR="infra/terraform/environments/sandbox"
IMAGE_TAG="${IMAGE_TAG:-develop}"
CLUSTER="${CLUSTER:-data-zoo-sandbox}"

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }

AWS_ARGS=(--endpoint-url "http://${ECR_ENDPOINT}" --region "${AWS_REGION}")

# ── Preflight ──────────────────────────────────────────────────────────

info "Preflight checks"
require_cmd docker
require_cmd aws
require_cmd terraform
require_cmd jq

if ! docker ps --filter "name=api-obs-floci" --filter "status=running" --format '{{.Names}}' | grep -q .; then
  fail "Floci is not running. Start it with: docker compose --profile aws up -d floci"
fi

if ! aws ecs list-clusters "${AWS_ARGS[@]}" 2>/dev/null | grep -q "${CLUSTER}"; then
  fail "ECS cluster '${CLUSTER}' not found. Apply Terraform first: just tf-apply"
fi

# ── Resolve ECR URIs ───────────────────────────────────────────────────
# Terraform output e.g.:
#   "ingestor": "000000000000.dkr.ecr.eu-central-1.localhost:5100/data-zoo/ingestor"

info "Reading ECR repository URIs from Terraform output"
ECR_URLS=$(cd "${TF_DIR}" && terraform output -json ecr_repository_urls 2>/dev/null) || \
  fail "Failed to read ecr_repository_urls. Run: just tf-apply"

INGESTOR_URI=$(echo "$ECR_URLS" | jq -r '.ingestor')
DASHBOARD_URI=$(echo "$ECR_URLS" | jq -r '.dashboard')

# Replace :latest tag with IMAGE_TAG
INGESTOR_TAGGED="${INGESTOR_URI/:latest/:${IMAGE_TAG}}"
DASHBOARD_TAGGED="${DASHBOARD_URI/:latest/:${IMAGE_TAG}}"

# Registry host for docker login: strip repo path from URI
# e.g. 000000000000.dkr.ecr.eu-central-1.localhost:5100
REGISTRY_HOST=$(echo "$INGESTOR_URI" | sed 's|/[^/]*$||')

info "Ingestor: ${INGESTOR_TAGGED}"
info "Dashboard: ${DASHBOARD_TAGGED}"
info "Registry: ${REGISTRY_HOST}"

# ── Authenticate docker against Floci ECR ──────────────────────────────
# Floci ECR implements a real OCI registry (backed by registry:2).
# get-login-password returns "AWS:floci" — any credentials work.

info "Authenticating docker against Floci ECR"
ECR_PASSWORD=$(aws ecr get-login-password "${AWS_ARGS[@]}") || \
  fail "Failed to get ECR login password"
echo "${ECR_PASSWORD}" | docker login --username AWS --password-stdin "${REGISTRY_HOST}"

# ── Build and tag images ───────────────────────────────────────────────

info "Building ingestor"
docker build -t "${INGESTOR_TAGGED}" -f Dockerfile .

info "Building dashboard"
docker build -t "${DASHBOARD_TAGGED}" -f services/dashboard/Dockerfile services/dashboard

# ── Push to Floci ECR (validates full push→pull path) ──────────────────

info "Pushing ingestor"
docker push "${INGESTOR_TAGGED}" || warn "Push failed — falling back to local Docker daemon"

info "Pushing dashboard"
docker push "${DASHBOARD_TAGGED}" || warn "Push failed — falling back to local Docker daemon"

# ── Deploy to ECS ──────────────────────────────────────────────────────
# --force-new-deployment causes ECS to pull the latest image from the
# registry. Floci ECS uses the mounted Docker socket, so it finds the
# image either in Floci's registry (if push succeeded) or local daemon.

info "Triggering ingestor deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service ingestor \
  --force-new-deployment \
  "${AWS_ARGS[@]}"

info "Waiting for ingestor stability"
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services ingestor \
  "${AWS_ARGS[@]}"

info "Triggering dashboard deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service dashboard \
  --force-new-deployment \
  "${AWS_ARGS[@]}"

info "Waiting for dashboard stability"
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services dashboard \
  "${AWS_ARGS[@]}"

# ── Smoke tests ────────────────────────────────────────────────────────

ALB_DNS=$(aws elbv2 describe-load-balancers \
  "${AWS_ARGS[@]}" \
  --query 'LoadBalancers[0].DNSName' \
  --output text 2>/dev/null || true)

if [ -n "${ALB_DNS}" ] && [ "${ALB_DNS}" != "None" ]; then
  info "Smoke testing ALB: ${ALB_DNS}"

  if curl --fail --max-time 15 "http://${ALB_DNS}/health" 2>/dev/null; then
    info "Ingestor /health OK"
  elif curl --fail --max-time 15 "http://${ALB_DNS}/readyz" 2>/dev/null; then
    info "Ingestor /readyz OK"
  else
    warn "Ingestor smoke check failed — tasks may still be starting"
  fi

  if curl --fail --max-time 15 "http://${ALB_DNS}/dashboard/_stcore/health" 2>/dev/null; then
    info "Dashboard /dashboard/_stcore/health OK"
  else
    warn "Dashboard smoke check failed — tasks may still be starting"
  fi
else
  warn "ALB DNS not found — skipping smoke tests"
fi

info "Sandbox deploy complete"
echo ""
echo "Access:"
echo "  API (local):       http://localhost:8000"
echo "  Dashboard (local): http://localhost:8501"
if [ -n "${ALB_DNS}" ] && [ "${ALB_DNS}" != "None" ]; then
  echo "  API (via ALB):     http://${ALB_DNS}"
  echo "  Dashboard (ALB):   http://${ALB_DNS}/dashboard"
fi
