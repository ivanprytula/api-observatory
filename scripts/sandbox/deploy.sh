#!/usr/bin/env bash
set -euo pipefail

# Deploy ingestor + dashboard to Floci sandbox (real containers).
# The project was previously named data-pipeline-async.
#
# prerequisites
#   - Floci running with ECR registry sidecar:
#       docker compose --profile aws up -d floci
#       docker run -d --name floci-ecr-registry \
#         --network api-observatory_api-obs -p 5100:5000 registry:2
#   - Terraform applied with ECR enabled: TF_ENV=sandbox just tf apply
#   - Docker daemon available (Floci mounts /var/run/docker.sock)
#
# Flow:
#   1. Read ECR repository URIs from Terraform output
#   2. Authenticate docker against Floci ECR (aws ecr get-login-password)
#   3. Build images, tag with ECR URI, push to Floci registry
#   4. Re-register task definitions with fresh image digests
#   5. Trigger ECS update-service --force-new-deployment
#   6. Wait for stability + report state

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

AWS_REGION="${AWS_REGION:-eu-central-1}"
ECR_ENDPOINT="${ECR_ENDPOINT:-127.0.0.1:4566}"
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
  fail "Floci is not running. Start it with: just floci-up"
fi

if ! docker ps --filter "name=floci-ecr-registry" --filter "status=running" --format '{{.Names}}' | grep -q .; then
  fail "ECR registry sidecar not running. Start it with:
    docker run -d --name floci-ecr-registry \\
      --network api-observatory_api-obs -p 5100:5000 registry:2"
fi

if ! aws ecs list-clusters "${AWS_ARGS[@]}" 2>/dev/null | grep -q "${CLUSTER}"; then
  fail "ECS cluster '${CLUSTER}' not found. Apply Terraform first: TF_ENV=sandbox just tf plan && TF_ENV=sandbox just tf apply"
fi

# ── Resolve ECR URIs from Terraform output ─────────────────────────────
# Floci ECR returns loopback URIs like:
#   000000000000.dkr.ecr.eu-central-1.localhost:5100/data-zoo/ingestor

info "Reading ECR repository URIs from Terraform output"
ECR_URLS=$(cd "${TF_DIR}" && terraform output -json ecr_repository_urls 2>/dev/null) || \
  fail "Failed to read ecr_repository_urls from Terraform output. Run: TF_ENV=sandbox just tf plan && TF_ENV=sandbox just tf apply"

INGESTOR_URI=$(echo "$ECR_URLS" | jq -r '.ingestor')
DASHBOARD_URI=$(echo "$ECR_URLS" | jq -r '.dashboard')

if [ -z "$INGESTOR_URI" ] || [ "$INGESTOR_URI" = "null" ]; then
  fail "ingestor ECR URL not found in Terraform output"
fi
if [ -z "$DASHBOARD_URI" ] || [ "$DASHBOARD_URI" = "null" ]; then
  fail "dashboard ECR URL not found in Terraform output"
fi

# Replace :latest with IMAGE_TAG
INGESTOR_TAGGED="${INGESTOR_URI/:latest/:${IMAGE_TAG}}"
DASHBOARD_TAGGED="${DASHBOARD_URI/:latest/:${IMAGE_TAG}}"

# Registry host for docker login: strip repo path from URI
REGISTRY_HOST=$(echo "$INGESTOR_URI" | sed 's|/[^/]*$||')

info "Ingestor ECR: ${INGESTOR_TAGGED}"
info "Dashboard ECR: ${DASHBOARD_TAGGED}"
info "Registry: ${REGISTRY_HOST}"

# ── Authenticate docker against Floci ECR ──────────────────────────────

info "Authenticating docker against Floci ECR"
ECR_PASSWORD=$(aws ecr get-login-password "${AWS_ARGS[@]}") || \
  fail "Failed to get ECR login password"
echo "${ECR_PASSWORD}" | docker login --username AWS --password-stdin "${REGISTRY_HOST}" || \
  fail "docker login to ${REGISTRY_HOST} failed"

# ── Build and push images ───────────────────────────────────────────────

info "Building ingestor"
docker build -t "${INGESTOR_TAGGED}" -f Dockerfile .

info "Pushing ingestor to ${INGESTOR_TAGGED}"
docker push "${INGESTOR_TAGGED}" || fail "Failed to push ingestor image"

info "Building dashboard"
docker build -t "${DASHBOARD_TAGGED}" -f services/dashboard/Dockerfile .

info "Pushing dashboard to ${DASHBOARD_TAGGED}"
docker push "${DASHBOARD_TAGGED}" || fail "Failed to push dashboard image"

# ── Re-register task definitions with fresh images ─────────────────────
# Terraform static task-defs reference a fixed image URI without digest.
# Re-register copies the task def but swaps in the freshly-pushed image,
# so ECS pulls the exact image we just built.

info "Re-registering ingestor task definition"
INGESTOR_TDEF=$(aws ecs describe-task-definition \
  --cluster "${CLUSTER}" \
  --task-definition data-zoo-sandbox-ingestor \
  "${AWS_ARGS[@]}" \
  --query 'taskDefinition' 2>/dev/null) || INGESTOR_TDEF=""

if [ -n "$INGESTOR_TDEF" ] && [ "$INGESTOR_TDEF" != "null" ]; then
  INGESTOR_TDEF=$(echo "$INGESTOR_TDEF" | jq --arg IMG "${INGESTOR_TAGGED}" \
    '.containerDefinitions[0].image = $IMG | del(.taskDefinitionArn) | del(.revision) | del(.status) | del(.requiresAttributes) | del(.compatibilities) | del(.registeredAt) | del(.registeredBy)')
  aws ecs register-task-definition \
    --cli-input-json "$INGESTOR_TDEF" \
    "${AWS_ARGS[@]}" || warn "Failed to re-register ingestor task def"
fi

info "Re-registering dashboard task definition"
DASHBOARD_TDEF=$(aws ecs describe-task-definition \
  --cluster "${CLUSTER}" \
  --task-definition data-zoo-sandbox-dashboard \
  "${AWS_ARGS[@]}" \
  --query 'taskDefinition' 2>/dev/null) || DASHBOARD_TDEF=""

if [ -n "$DASHBOARD_TDEF" ] && [ "$DASHBOARD_TDEF" != "null" ]; then
  DASHBOARD_TDEF=$(echo "$DASHBOARD_TDEF" | jq --arg IMG "${DASHBOARD_TAGGED}" \
    '.containerDefinitions[0].image = $IMG | del(.taskDefinitionArn) | del(.revision) | del(.status) | del(.requiresAttributes) | del(.compatibilities) | del(.registeredAt) | del(.registeredBy)')
  aws ecs register-task-definition \
    --cli-input-json "$DASHBOARD_TDEF" \
    "${AWS_ARGS[@]}" || warn "Failed to re-register dashboard task def"
fi

# ── Deploy to ECS ──────────────────────────────────────────────────────

info "Triggering ingestor deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service ingestor \
  --force-new-deployment \
  "${AWS_ARGS[@]}" || warn "update-service ingestor failed"

info "Waiting for ingestor stability"
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services ingestor \
  "${AWS_ARGS[@]}" || warn "ingestor did not stabilize"

info "Triggering dashboard deployment"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service dashboard \
  --force-new-deployment \
  "${AWS_ARGS[@]}" || warn "update-service dashboard failed"

info "Waiting for dashboard stability"
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services dashboard \
  "${AWS_ARGS[@]}" || warn "dashboard did not stabilize"

# ── Post-deploy smoke test ───────────────────────────────────────────

info "Running post-deploy smoke test"
ALB_DNS=$(aws elbv2 describe-load-balancers \
  "${AWS_ARGS[@]}" \
  --query 'LoadBalancers[0].DNSName' \
  --output text 2>/dev/null || true)

BASE_URL="http://${ALB_DNS:-127.0.0.1:8000}"
if [ -n "$ALB_DNS" ] && [ "$ALB_DNS" != "<not found>" ]; then
  BASE_URL="http://${ALB_DNS}"
fi
bash scripts/smoke-test.sh "$BASE_URL" 60 || warn "Smoke test failed — check endpoints above"

# ── Report Floci state ────────────────────────────────────────────────

info "Floci resource state"

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
echo "  - Terraform creates ECR repos, RDS, ElastiCache, ALB, ECS cluster"
echo "  - Images built, pushed to Floci ECR, task defs re-registered"
echo "  - ECS services deployed with new task definitions"
echo ""
echo "Access via ALB (task containers reachable inside Docker network):"
echo "  ALB DNS: ${ALB_DNS:-pending}"
echo ""
echo "Next:"
echo "  TF_ENV=sandbox just tf destroy   # clean up sandbox state"
