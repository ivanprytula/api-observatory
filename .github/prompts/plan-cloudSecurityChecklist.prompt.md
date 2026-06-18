# Plan: Cloud Security Checklist — AWS Dev Deployment Readiness

## SDLC Stage Status (evaluated 2026-06-13)

| Stage | Status | Evidence | Blocker |
|-------|--------|----------|---------|
| 1: CI Trust | ✅ Done | `ci.yml` lint→unit→integration→docker lanes; fixtures in `tests/conftest.py`; `just dev/up` work | Coverage gate at 40% (raise later) |
| 2: Release Supply Chain | ✅ Done | `release.yml` has SBOM via Syft, Cosign signing, SLSA provenance, digest-based promotion | None |
| 3: Real Cloud SDLC | ⚠️ Partial | `cd-dev.yml` + Terraform dev env defined; `deploy-runbook.md` exists | S3 state bucket not bootstrapped; OIDC role not created; `backend.aws.hcl` and `terraform.aws.tfvars` are `.example` templates only |
| 4: Observability | ⚠️ Partial | 12+ Prometheus alert rules; circuit breaker metrics in `metrics.py` | SLI/SLO targets not formally documented |
| 5: Performance | ⚠️ Partial | k6 scripts in `scripts/load/`; async SQLAlchemy 2.0 + httpx | No baseline stored; no CI integration |
| 6: Microservice Expansion | ❌ Not Started | Dashboard exists but no separate SDLC gates | Not needed; Stage 3 gate not met |

## AWS Dev Deploy Readiness: NOT READY

Three hard prerequisites missing before first `just deploy-ecs`:

1. AWS account-level hardening (root/IAM — AWS best practices not done per user)
2. S3 state bucket + DynamoDB lock table for Terraform backend
3. OIDC role for GitHub Actions + ECR repos + real `backend.aws.hcl` / `terraform.aws.tfvars` populated

## Files to Create / Update

### Create: `docs/deployment/cloud-security-checklist.md`

Not duplicating:
- `docs/security-architecture.md` — app-level auth/RBAC/headers
- `docs/setup/pre-production-ingress-checklist.md` — Nginx/TLS
- `docs/setup/sandbox-aws-profile.md` — AWS CLI profile setup
- `infra/terraform/STATE_BACKEND_CHECKLIST.md` — Terraform backend bootstrap

### Update: `docs/deployment/aws-ecs.md`

Add one-line link to `cloud-security-checklist.md` in the Prerequisites section.

## Proposed Content for `cloud-security-checklist.md`

Track: C — Architecture and Platform Strategy

### Section 1: One-Time AWS Account Hardening (do before anything else)

Scope: solo dev, MVP, eu-central-1.

Checklist:
- [ ] Enable MFA on root account (hardware key or TOTP app)
- [ ] Create a billing alert at $20 and $50 (Cost Explorer → Budgets)
- [ ] Create an IAM admin user for daily CLI work — do not use root for daily tasks
  - Group: `admins`, policy: `AdministratorAccess`
  - MFA required for this user too
- [ ] Delete or disable root access keys (IAM → Security credentials)
- [ ] Enable CloudTrail (management events, all regions, S3 bucket with encryption)
- [ ] Enable IAM Access Analyzer on the account (free, catches accidental public access)
- [ ] Enable GuardDuty (30-day free trial, then ~$4/month for dev scale — decide whether to keep)

Why: root account compromise = game over. These seven steps take under 30 minutes and are irreversible risk mitigations.

### Section 2: GitHub Actions OIDC Role (no long-lived keys in Secrets)

The workflows (`ci.yml`, `cd-dev.yml`) use `vars.AWS_ROLE_ARN_DEV` via OIDC. No AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in GitHub Secrets.

Steps:
1. Create OIDC identity provider in IAM:
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
2. Create IAM role `github-actions-dev`:
   - Trust policy: OIDC, condition `sub` = `repo:<owner>/api-observatory:*`
   - Permission policy: see minimal policy below
3. Set GitHub Actions variable `AWS_ROLE_ARN_DEV` = `arn:aws:iam::<account-id>:role/github-actions-dev`

Minimal IAM policy for `github-actions-dev` (dev environment):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECRRepoAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:DescribeRepositories",
        "ecr:ListImages"
      ],
      "Resource": "arn:aws:ecr:eu-central-1:<account-id>:repository/data-zoo-*"
    },
    {
      "Sid": "TerraformState",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-terraform-state-bucket",
        "arn:aws:s3:::your-terraform-state-bucket/*"
      ]
    },
    {
      "Sid": "ECSDeployAccess",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:ListTasks",
        "ecs:DescribeTasks"
      ],
      "Resource": "*",
      "Condition": {
        "ArnLike": {
          "ecs:cluster": "arn:aws:ecs:eu-central-1:<account-id>:cluster/data-zoo-dev"
        }
      }
    },
    {
      "Sid": "ELBDescribe",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth"
      ],
      "Resource": "*"
    },
    {
      "Sid": "TerraformIAMPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::<account-id>:role/data-zoo-*"
    }
  ]
}
```

Note: Terraform `plan` and `apply` in `cd-dev.yml` also need RDS, ElastiCache, VPC, ECS task definition, IAM role creation permissions. Expand this policy once you run `TF_ENV=dev just tf plan` and see exactly what resources Terraform wants to manage. Start narrow and add permissions on demand from the CloudTrail `AccessDenied` events.

### Section 3: Infrastructure Bootstrap (one-time, before Terraform)

1. Create S3 state bucket (replace `your-terraform-state-bucket`):

```bash
aws s3api create-bucket \
  --bucket your-terraform-state-bucket \
  --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1

aws s3api put-bucket-versioning \
  --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket your-terraform-state-bucket \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket your-terraform-state-bucket \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

2. Create ECR repositories:

```bash
aws ecr create-repository --repository-name data-zoo-ingestor --region eu-central-1
aws ecr create-repository --repository-name data-zoo-dashboard --region eu-central-1
```

Record the registry URL (format: `<account-id>.dkr.ecr.eu-central-1.amazonaws.com`) and set GitHub variable `DEV_ECR_REGISTRY`.

3. Populate config files from templates:

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example \
   infra/terraform/environments/dev/backend.aws.hcl
# Edit: set bucket = "your-terraform-state-bucket"

cp infra/terraform/environments/dev/terraform.aws.tfvars.example \
   infra/terraform/environments/dev/terraform.aws.tfvars
# Edit: set TF_VAR_redis_auth_token via env var, not in file
```

Both files are gitignored. Never commit them.

4. Verify `just dev-preflight` passes:

```bash
just dev-preflight
# Expected: all [ok] lines, no [FAIL]
```

### Section 4: Pre-Deploy Checklist (before each `just deploy-ecs`)

Run in order:

- [ ] `just floci-validate` — Floci sandbox healthy
- [ ] `just dev-preflight` — real AWS creds + config files present
- [ ] `just deploy-audit` — image builds, size < 1.5GB, no CRITICAL CVEs
- [ ] `TF_ENV=dev just tf plan` — review changeset, no unintended destroys
- [ ] No secrets in diff (`git diff` scan or pre-commit hook)
- [ ] `just deploy-ecs` — apply reviewed plan + ECS rollout

### Section 5: Post-Deploy Verification

- [ ] `/health` returns `{"status": "ok"}` on ALB DNS
- [ ] `/readyz` returns 200 (all health gates passed)
- [ ] `just smoke-test` passes end-to-end
- [ ] CloudTrail shows expected IAM calls in last 10 minutes (no `AccessDenied` errors)
- [ ] IAM Access Analyzer findings: zero public access findings for new resources
- [ ] Cost Explorer: no unexpected service usage (check within 24h of first deploy)

### Section 6: Ongoing Security Hygiene (monthly, ~10 minutes)

- [ ] Review IAM Access Analyzer findings
- [ ] Review CloudTrail for any `AccessDenied` anomalies
- [ ] `pip-audit` on local venv (CI runs this too, but confirm locally before PRs)
- [ ] Rotate `redis_auth_token` if it has been in use for >90 days
- [ ] Check AWS Trusted Advisor security tab (free checks: exposed keys, MFA on root, open security groups)

## Key Variables Reference

| Variable | Where set | Value |
|----------|-----------|-------|
| `vars.AWS_ROLE_ARN_DEV` | GitHub repo vars | `arn:aws:iam::<account-id>:role/github-actions-dev` |
| `vars.DEV_ECR_REGISTRY` | GitHub repo vars | `<account-id>.dkr.ecr.eu-central-1.amazonaws.com` |
| `AWS_REGION` | `cd-dev.yml` env | `eu-central-1` |
| `backend.aws.hcl` → `bucket` | local gitignored file | `your-terraform-state-bucket` |
| `backend.aws.hcl` → `key` | local gitignored file | `dev/platform/terraform.tfstate` |
| `TF_VAR_redis_auth_token` | shell env, never in file | strong random string |

## Related Docs

- [docs/security-architecture.md](docs/security-architecture.md) — app-level auth, RBAC, headers
- [docs/setup/pre-production-ingress-checklist.md](docs/setup/pre-production-ingress-checklist.md) — Nginx/TLS
- [docs/setup/sandbox-aws-profile.md](docs/setup/sandbox-aws-profile.md) — AWS CLI profile setup
- [infra/terraform/STATE_BACKEND_CHECKLIST.md](infra/terraform/STATE_BACKEND_CHECKLIST.md) — Terraform state backend details
- [docs/deployment/aws-ecs.md](docs/deployment/aws-ecs.md) — ECS deploy sequence
- [docs/deployment/deploy-runbook.md](docs/deployment/deploy-runbook.md) — full deploy runbook
