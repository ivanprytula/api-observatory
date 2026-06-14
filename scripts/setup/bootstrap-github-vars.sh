#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ENV_DIR="${PROJECT_ROOT}/infra/terraform/environments/dev"

usage() {
  cat <<'EOF'
bootstrap-github-vars.sh — provision AWS backend + IaC, then emit GitHub Actions variables.

Creates / ensures:
  - S3 Terraform state bucket
  - Terraform remote backend init
  - Full dev IaC apply (network, ECR, IAM/OIDC, compute, etc.)
  - GitHub Actions variable payload (stdout)

Required tools:
  aws, terraform (>=1.9), jq, gh (optional, for auto-set)

Usage:
  ./scripts/setup/bootstrap-github-vars.sh [--force] [--apply] [--set-gh-vars] [--region REGION] [--bucket BUCKET]

Options:
  --force           Recreate state bucket (warns, then deletes + recreates)
  --apply           Run terraform apply (default: plan-only unless --force or first run)
  --set-gh-vars     Write values to GitHub repo variables via gh CLI (requires auth)
  --region REGION   AWS region (default: eu-central-1)
  --bucket BUCKET   Terraform state bucket name (default: data-zoo-terraform-state-dev)
  --repo OWNER/REPO GitHub repo for gh variable set (default: ivanprytula/api-observatory)
EOF
  exit 1
}

FORCE=0
APPLY=0
SET_GH=0
AWS_REGION="eu-central-1"
BUCKET="data-zoo-terraform-state-dev"
REPO="ivanprytula/api-observatory"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)       FORCE=1; shift ;;
    --apply)       APPLY=1; shift ;;
    --set-gh-vars) SET_GH=1; shift ;;
    --region)      AWS_REGION="$2"; shift 2 ;;
    --bucket)      BUCKET="$2"; shift 2 ;;
    --repo)        REPO="$2"; shift 2 ;;
    *)             usage ;;
  esac
done

echo "=== GitHub Actions bootstrap ==="
echo "Region   : ${AWS_REGION}"
echo "Bucket   : ${BUCKET}"
echo "Repo     : ${REPO}"
echo ""

# ── 1. S3 state bucket ────────────────────────────────────────────────────────
echo "[1/5] Ensuring S3 state bucket: ${BUCKET}"
BUCKET_EXISTS=$(aws s3 ls "s3://${BUCKET}" --region "${AWS_REGION}" 2>/dev/null | wc -l || true)
if [[ "$BUCKET_EXISTS" -gt 0 ]]; then
  if [[ "$FORCE" -eq 1 ]]; then
    echo "  --force: emptying and deleting bucket ${BUCKET}..."
    aws s3 rm "s3://${BUCKET}" --recursive --region "${AWS_REGION}" || true
    aws s3 rb "s3://${BUCKET}" --region "${AWS_REGION}" || true
    BUCKET_EXISTS=0
  else
    echo "  Bucket already exists. Use --force to recreate."
  fi
fi

if [[ "$BUCKET_EXISTS" -eq 0 ]]; then
  aws s3 mb "s3://${BUCKET}" --region "${AWS_REGION}"
  aws s3api put-bucket-versioning --bucket "${BUCKET}" --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption --bucket "${BUCKET}" --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  echo "  Bucket created + versioning + encryption enabled."
else
  echo "  Bucket exists."
fi

# ── 2. Terraform init ─────────────────────────────────────────────────────────
echo ""
echo "[2/5] Terraform init (remote backend)"
cd "${TF_ENV_DIR}"

terraform init -reconfigure \
  -backend-config="bucket=${BUCKET}" \
  -backend-config="key=dev/platform/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="encrypt=true" \
  -backend-config="use_lockfile=true"

# ── 3. Terraform apply ────────────────────────────────────────────────────────
echo ""
echo "[3/5] Terraform apply (dev environment)"
# If not --apply and bucket was just created, run apply once automatically.
# If bucket existed and no --apply, show plan only.
if [[ "$APPLY" -eq 1 ]] || [[ "$BUCKET_EXISTS" -eq 0 ]]; then
  terraform apply -auto-approve -lock-timeout=30m \
    -var-file=terraform.tfvars \
    -var-file=terraform.aws.tfvars
else
  echo "  Skipping apply (use --apply to force). Showing plan instead:"
  terraform plan -lock-timeout=30m \
    -var-file=terraform.tfvars \
    -var-file=terraform.aws.tfvars
  echo ""
  read -r -p "Apply now? [y/N] " CONFIRM
  if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    terraform apply -auto-approve -lock-timeout=30m \
      -var-file=terraform.tfvars \
      -var-file=terraform.aws.tfvars
  else
    echo "  Aborted apply. Re-run with --apply after reviewing plan."
    exit 0
  fi
fi

# ── 4. Resolve outputs ────────────────────────────────────────────────────────
echo ""
echo "[4/5] Reading Terraform outputs"

ROLE_ARN=$(terraform output -raw github_actions_role_arn 2>/dev/null || true)
if [[ -z "${ROLE_ARN}" ]]; then
  echo "ERROR: github_actions_role_arn output missing. Did enable_iam=true in dev/variables.tf?" >&2
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "${AWS_REGION}")
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "  AWS_ROLE_ARN_DEV    : ${ROLE_ARN}"
echo "  DEV_ECR_REGISTRY    : ${ECR_REGISTRY}"
echo "  TERRAFORM_STATE_BUCKET_DEV : ${BUCKET}"

# ── 5. Emit / set GitHub variables ────────────────────────────────────────────
echo ""
echo "[5/5] GitHub Actions variables"

if ! command -v gh >/dev/null 2>&1; then
  echo "  gh CLI not found. Export these manually:"
  echo ""
  echo "    AWS_ROLE_ARN_DEV=${ROLE_ARN}"
  echo "    DEV_ECR_REGISTRY=${ECR_REGISTRY}"
  echo "    TERRAFORM_STATE_BUCKET_DEV=${BUCKET}"
  echo ""
  echo "  Or install gh: https://cli.github.com/"
  exit 0
fi

if [[ "$SET_GH" -eq 1 ]]; then
  echo "  Writing variables to ${REPO}..."
  gh variable set AWS_ROLE_ARN_DEV --repo "${REPO}" --body "${ROLE_ARN}"
  gh variable set DEV_ECR_REGISTRY --repo "${REPO}" --body "${ECR_REGISTRY}"
  gh variable set TERRAFORM_STATE_BUCKET_DEV --repo "${REPO}" --body "${BUCKET}"
  echo "  ✅ Variables set."
else
  echo "  Dry-run mode. Run with --set-gh-vars to write to GitHub:"
  echo ""
  echo "    $0 --set-gh-vars"
  echo ""
  echo "  Or set manually in:"
  echo "    https://github.com/${REPO}/settings/variables/actions"
fi
