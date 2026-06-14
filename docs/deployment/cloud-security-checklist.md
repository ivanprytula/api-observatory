# Cloud Security Checklist — AWS Dev Deployment Readiness

Track: C — Architecture and Platform Strategy

This checklist captures the minimal manual steps required before the first
real-cloud `just deploy-ecs` into the `dev` environment (eu-central-1).

Scope: solo dev, MVP account. Intentionally minimal — the S3 state bucket and
OIDC role are the only manual prerequisites; everything else is Terraform-managed.

> **Not duplicated here**: app-level auth ([security-architecture.md](../security-architecture.md)),
> Nginx/TLS ([pre-production-ingress-checklist.md](../setup/pre-production-ingress-checklist.md)),
> AWS CLI profile setup ([sandbox-aws-profile.md](../setup/sandbox-aws-profile.md)),
> backend locking details ([STATE_BACKEND_CHECKLIST.md](../../infra/terraform/STATE_BACKEND_CHECKLIST.md)).

---

## Step 0 — One-Time AWS Account Hardening (do before anything else)

These seven steps take under 30 minutes and are irreversible risk mitigations.
Root account compromise = game over.

- [ ] Enable MFA on the AWS root account (hardware key or TOTP app).
- [ ] Create billing budgets at $20 and $50 (Cost Explorer → Budgets).
- [ ] Create an IAM admin user for daily CLI work — **do not use root for
  daily tasks**.
  - Group: `admins`, policy: `AdministratorAccess`, MFA required.
- [ ] Delete or disable root access keys (IAM → Security credentials).
- [ ] Enable CloudTrail (management events, all regions, encrypted S3 bucket).
- [ ] Enable IAM Access Analyzer on the account (free).
- [ ] Enable GuardDuty (30-day free trial; ~$4/month at dev scale — decide
  after trial).

---

## Step 1 — Bootstrap: S3 State Bucket + ECR Repos (manual, one-time)

This must be done **before** running Terraform, because Terraform needs the
S3 bucket to store state.

**No DynamoDB table needed.** All backends use `use_lockfile = true`
(Terraform ≥ 1.9 S3-native locking — a `.tflock` object in S3).

Replace `your-terraform-state-bucket` with your chosen bucket name (must be
globally unique). Use the same name in `backend.aws.hcl`.

```bash
BUCKET="your-terraform-state-bucket"
REGION="eu-central-1"

# Create bucket (LocationConstraint required for all regions except us-east-1)
aws s3api create-bucket \
  --bucket "${BUCKET}" \
  --region "${REGION}" \
  --create-bucket-configuration LocationConstraint="${REGION}"

# Enable versioning (required for state recovery)
aws s3api put-bucket-versioning \
  --bucket "${BUCKET}" \
  --versioning-configuration Status=Enabled

# Enable default encryption (AES-256 / SSE-S3)
aws s3api put-bucket-encryption \
  --bucket "${BUCKET}" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Block all public access
aws s3api put-public-access-block \
  --bucket "${BUCKET}" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Verify
aws s3api get-bucket-versioning --bucket "${BUCKET}"
aws s3api get-bucket-encryption --bucket "${BUCKET}"
aws s3api get-public-access-block --bucket "${BUCKET}"
```

Create ECR repositories and enable image scanning on push:

```bash
for REPO in data-zoo-ingestor data-zoo-dashboard; do
  aws ecr create-repository --repository-name "${REPO}" --region "${REGION}"
  aws ecr put-image-scanning-configuration \
    --repository-name "${REPO}" \
    --region "${REGION}" \
    --image-scanning-configuration scanOnPush=true
done
```

Record the registry URL for the GitHub variable:

```bash
# Output format: <account-id>.dkr.ecr.eu-central-1.amazonaws.com
aws ecr describe-repositories --region "${REGION}" \
  --query 'repositories[0].repositoryUri' --output text | sed 's|/.*||'
```

---

## Step 2 — Populate Local Config Files

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example \
   infra/terraform/environments/dev/backend.aws.hcl
# Edit: set bucket = "your-terraform-state-bucket"

cp infra/terraform/environments/dev/terraform.aws.tfvars.example \
   infra/terraform/environments/dev/terraform.aws.tfvars
# Edit if needed; set TF_VAR_redis_auth_token via shell env, not in file
```

Both files are gitignored. **Never commit them.**

---

## Step 3 — First Local Terraform Apply (bootstraps OIDC role)

The OIDC identity provider and IAM role are **Terraform-managed**
([`modules/iam/main.tf`](../../infra/terraform/modules/iam/main.tf)).
Run this once with your IAM admin credentials to create them.

```bash
# Use your admin IAM user profile (not root, not a CI role)
export AWS_PROFILE=your-admin-profile

TF_ENV=dev just tf init    # -backend-config=backend.aws.hcl
TF_ENV=dev just tf plan    # review — expect VPC, IAM, ECR, ECS resources
TF_ENV=dev just tf apply   # creates data-zoo-github-actions role + OIDC provider
```

After apply, capture the role ARN from outputs:

```bash
cd infra/terraform/environments/dev
terraform output github_actions_role_arn
# arn:aws:iam::<account-id>:role/data-zoo-github-actions
```

**Note:** The ECS deploy IAM policy is commented out in `modules/iam/main.tf`
(lines ~95-120). Uncomment the `ecs_deploy` policy block before the first
`just deploy-ecs` run, then re-apply Terraform.

---

## Step 4 — Set GitHub Repository Variables

Go to **Settings → Secrets and variables → Actions → Variables** and create:

| Variable name                  | Value                                                   |
| ------------------------------ | ------------------------------------------------------- |
| `AWS_ROLE_ARN_DEV`             | `arn:aws:iam::<account-id>:role/data-zoo-github-actions` |
| `DEV_ECR_REGISTRY`             | `<account-id>.dkr.ecr.eu-central-1.amazonaws.com`       |
| `TERRAFORM_STATE_BUCKET_DEV`   | `your-terraform-state-bucket`                           |

> These are **variables** (not secrets) — no sensitive values, just ARNs and
> bucket names. The OIDC token itself is never stored.

---

## Step 5 — Verify Preflight

```bash
just dev-preflight
# Expect: all [ok] lines, no [FAIL]
```

---

## Pre-deploy Checklist (run before each `just deploy-ecs`)

- [ ] `just floci-validate` — Floci sandbox healthy
- [ ] `just dev-preflight` — real AWS creds + local config files present
- [ ] `just deploy-audit` — image builds, size < 1.5 GB, no CRITICAL CVEs
- [ ] `TF_ENV=dev just tf plan` — review changeset; no unintended destroys
- [ ] No secrets in diff (pre-commit scan)
- [ ] `just deploy-ecs` — apply reviewed plan + ECS rollout

---

## Post-deploy Verification

- [ ] `/health` returns `{"status": "ok"}` on ALB DNS
- [ ] `/readyz` returns 200
- [ ] `just smoke-test` passes end-to-end
- [ ] CloudTrail: only expected IAM calls in last 10 minutes, no `AccessDenied`
- [ ] IAM Access Analyzer: zero public-access findings for new resources
- [ ] Cost Explorer: no unexpected service usage (check within 24 h)

---

## Ongoing Hygiene (monthly)

- [ ] Review IAM Access Analyzer findings
- [ ] Review CloudTrail for `AccessDenied` anomalies
- [ ] Run `pip-audit` locally
- [ ] Rotate `redis_auth_token` if older than 90 days
- [ ] Check AWS Trusted Advisor security tab

---

## Prod Hardening Checklist (skip for dev, required before prod)

These items are intentionally deferred. Track them before promoting to
production:

- [ ] S3 state bucket — add deny-non-TLS bucket policy
- [ ] S3 state bucket — add S3 access logging to a separate audit bucket
- [ ] S3 state bucket — add lifecycle policy to expire noncurrent versions
- [ ] IAM role — replace SSE-S3 with KMS CMK for state encryption
- [ ] IAM role — tighten OIDC sub condition to specific workflow refs
  (currently allows `main` + `develop` push; restrict to release tag if needed)
- [ ] `cd-prod.yml` — fill in the TODO OIDC block (currently commented out)
- [ ] `github-actions-prod` role — separate prod role with narrower permissions
- [ ] Enable AWS Config for drift detection
- [ ] Enable Security Hub for aggregated findings
- [ ] Add `terraform force-unlock` emergency `workflow_dispatch` workflow

---

## Key Variables Reference

| Variable                       | Where set               | Value / note                                            |
| ------------------------------ | ----------------------- | ------------------------------------------------------- |
| `vars.AWS_ROLE_ARN_DEV`        | GitHub repo variables   | `arn:aws:iam::<account-id>:role/data-zoo-github-actions` |
| `vars.DEV_ECR_REGISTRY`        | GitHub repo variables   | `<account-id>.dkr.ecr.eu-central-1.amazonaws.com`       |
| `vars.TERRAFORM_STATE_BUCKET_DEV` | GitHub repo variables | `your-terraform-state-bucket`                           |
| `AWS_REGION`                   | `cd-dev.yml` env        | `eu-central-1`                                          |
| `backend.aws.hcl` → `bucket`   | local gitignored file   | `your-terraform-state-bucket`                           |
| `backend.aws.hcl` → `key`      | local gitignored file   | `dev/platform/terraform.tfstate`                        |
| `TF_VAR_redis_auth_token`      | shell env, never in file | strong random string                                   |

---

## Related Documentation

- [docs/security-architecture.md](../security-architecture.md) — app-level auth, RBAC, headers
- [docs/setup/pre-production-ingress-checklist.md](../setup/pre-production-ingress-checklist.md) — Nginx/TLS
- [docs/setup/sandbox-aws-profile.md](../setup/sandbox-aws-profile.md) — AWS CLI profile setup
- [infra/terraform/STATE_BACKEND_CHECKLIST.md](../../infra/terraform/STATE_BACKEND_CHECKLIST.md) — Terraform state backend details
- [docs/deployment/aws-ecs.md](aws-ecs.md) — ECS deploy sequence
- [docs/deployment/deploy-runbook.md](deploy-runbook.md) — full deploy runbook
