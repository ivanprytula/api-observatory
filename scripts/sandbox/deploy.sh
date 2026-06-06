#!/usr/bin/env bash
set -euo pipefail

# Deploy ingestor + dashboard to local Floci/ECS sandbox.
#
# Prerequisites:
#   - Floci running:  docker compose --profile aws up -d floci
#   - Terraform applied: just tf-apply
#
# Sandbox mode skips ECR and data-plane modules (Floci mock + rootless limits).
# ECS_MOCK=true makes tasks go straight to RUNNING — no real containers.
# This script validates the Terraform→Floci IaC pipeline, not runtime behavior.

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
# ECS_MOCK=true means tasks go straight to RUNNING without pulling.
# --force-new-deployment triggers a new task set revision.

info "Triggering ingestor deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service ingestor \
  --force-new-deployment \
  "${AWS_ARGS[@]}" || warn "update-service ingestor failed"

info "Triggering dashboard deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service dashboard \
  --force-new-deployment \
  "${AWS_ARGS[@]}" || warn "update-service dashboard failed"

# ── Report Floci state ────────────────────────────────────────────────
# ecs wait hangs in mock mode (returns null fields), so skip it.
# Report what Floci has instead of trying to smoke-test non-existent backends.

info "Floci resource state"

ALB_DNS=$(aws elbv2 describe-load-balancers \
  "${AWS_ARGS[@]}" \
  --query 'LoadBalancers[0].DNSName' \
  --output text 2>/dev/null || true)

SERVICES=$(aws ecs describe-services \
  --cluster "${CLUSTER}" \
  --services ingestor dashboard \
  "${AWS_ARGS[@]}" \
  --query 'services[].{Name:serviceName,Running:runningCount,Desired:desiredCount,TaskDef:taskDefinition}' \
  --output table 2>/dev/null || true)

echo ""
echo "ALB:   ${ALB_DNS:-<not found>}"
echo ""
echo "ECS services:"
echo "${SERVICES:-<not found>}"
echo ""

# ── Summary ────────────────────────────────────────────────────────────

info "Sandbox deploy complete"
echo ""
echo "What this validates:"
echo "  - Terraform compiles against Floci AWS API"
echo "  - ECS task definitions registered (ingestor + dashboard)"
echo "  - ALB + target groups + listener rules created"
echo "  - Image tags recorded in task definitions"
echo ""
echo "Limits of mock mode:"
echo "  - No real containers run behind ALB (ECS_MOCK=true)"
echo "  - ALB DNS (.elb.localhost) only resolves inside Docker"
echo "  - Use 'just up' for real runtime testing with compose services"
echo ""
echo "Next:"
echo "  just tf-destroy   # clean up sandbox state"
echo "  just up           # real dev environment with compose"
