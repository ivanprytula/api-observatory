# Cloud Security Checklist — AWS Dev Deployment Readiness

Track: C — Architecture and Platform Strategy

This checklist captures the minimal account, CI, and infrastructure bootstrap steps
required before performing a first real-cloud `just deploy-ecs` into the `dev`
environment (eu-central-1).

Note: this document is intentionally scoped for a solo/MVP development AWS
account. For production or multi-tenant accounts, consult the full security
runbooks and company policies.

## One-time Account Hardening (do these first)

These steps protect the account root and provide basic monitoring. They are
quick, irreversible risk mitigations.

- [ ] Enable MFA on the AWS root account (hardware key or TOTP app).
- [ ] Create billing budgets/alerts (e.g. $20 and $50 thresholds).
- [ ] Create an IAM admin user for daily CLI work (group `admins`,
  policy `AdministratorAccess`) and require MFA for that user.
- [ ] Delete or disable root access keys (IAM → Security credentials).
- [ ] Enable CloudTrail (management events, multi-region) and send logs to an
  encrypted S3 bucket.
- [ ] Enable IAM Access Analyzer on the account.
- [ ] Consider enabling GuardDuty (evaluate cost after trial).

Why: Compromise of the root account or exposed credentials is the highest-risk
failure mode. These seven items are a low-effort, high-impact baseline.

## GitHub Actions → OIDC Role (avoid long-lived secrets)

The repository's workflows expect an OIDC-based role for `develop`/`dev` runs.
Do not use long-lived `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in secrets.

Steps summary:

1. Create an OIDC identity provider in IAM:
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
2. Create role `github-actions-dev` with an OIDC trust policy restricted to
   `sub = repo:<owner>/data-pipeline-async:*`.
3. Grant minimal runtime permissions (ECR push/pull, S3 state access, ECS
   update, ELB describe, `iam:PassRole` for specific roles). Start narrow and
   add permissions from `AccessDenied` events if needed.
4. Set GitHub repo variable `AWS_ROLE_ARN_DEV` = `arn:aws:iam::<account-id>:role/github-actions-dev`.

Minimal example policy (trim and scope to your account/regions):

```json
{
  "Version": "2012-10-17",
  "Statement": [ /* see project docs for full JSON example */ ]
}
```

Notes:

- Terraform runs in CI will require additional permissions for resources that
  Terraform manages (RDS, ElastiCache, VPC, IAM, etc.) — expand the policy only
  after reviewing `TF_ENV=dev just tf plan` and addressing specific needs.

## Infrastructure Bootstrap (before running Terraform)

Create the Terraform backend and ECR repos used by CI and Terraform:

- Create a versioned, encrypted, non-public S3 bucket for Terraform state:

```bash
aws s3api create-bucket \
  --bucket your-terraform-state-bucket \
  --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1

aws s3api put-bucket-versioning --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption --bucket your-terraform-state-bucket \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block --bucket your-terraform-state-bucket \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
```

- Create a DynamoDB lock table if your workflows require state locking (recommended).
- Create ECR repositories used by CI/CD and set GitHub variable `DEV_ECR_REGISTRY`:

  ```bash
  aws ecr create-repository --repository-name data-zoo-ingestor --region eu-central-1
  aws ecr create-repository --repository-name data-zoo-dashboard --region eu-central-1
  ```

- Populate local gitignored backend/config templates:

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example \
  infra/terraform/environments/dev/backend.aws.hcl

cp infra/terraform/environments/dev/terraform.aws.tfvars.example \
  infra/terraform/environments/dev/terraform.aws.tfvars
# Edit values: bucket name, account id, do NOT commit these files.
```

- Verify preflight checks:

```bash
just dev-preflight
# Expect: all checks pass, no [FAIL]
```

## Pre-deploy Checklist (run before `just deploy-ecs`)

- [ ] `just floci-validate` — Floci sandbox healthy
- [ ] `just dev-preflight` — real AWS creds + config files present
- [ ] `just deploy-audit` — image size and CVE checks pass
- [ ] `TF_ENV=dev just tf plan` — review changeset; no unintended destroys
- [ ] No secrets in diff (pre-commit/hook scan)
- [ ] `just deploy-ecs` — apply reviewed plan + ECS rollout

## Post-deploy Verification

- [ ] `/health` returns `{"status": "ok"}` on ALB DNS
- [ ] `/readyz` returns 200
- [ ] `just smoke-test` passes end-to-end
- [ ] CloudTrail shows only expected IAM calls in the last 10 minutes
- [ ] IAM Access Analyzer: zero public-access findings for new resources

## Ongoing Hygiene (monthly)

- [ ] Review IAM Access Analyzer findings
- [ ] Review CloudTrail for anomalous `AccessDenied` events
- [ ] Run `pip-audit` locally (CI also runs this)
- [ ] Rotate `redis_auth_token` if older than 90 days
- [ ] Check AWS Trusted Advisor / security recommendations

## Key Variables Reference

| Variable                     | Where set             | Note                                                |
| ---------------------------- | --------------------- | --------------------------------------------------- |
| `vars.AWS_ROLE_ARN_DEV`      | GitHub repo variables | `arn:aws:iam::<account-id>:role/github-actions-dev` |
| `vars.DEV_ECR_REGISTRY`      | GitHub repo variables | `<account-id>.dkr.ecr.eu-central-1.amazonaws.com`   |
| `backend.aws.hcl` → `bucket` | local gitignored file | `your-terraform-state-bucket`                       |
| `TF_VAR_redis_auth_token`    | shell env             | keep out of files; set in CI or local env           |

## Related docs

- See `docs/security-architecture.md` for app-level auth and headers.
- See `infra/terraform/STATE_BACKEND_CHECKLIST.md` for Terraform bootstrap details.
- See `docs/deployment/aws-ecs.md` for ECS deployment sequence.

## Cloud Security Checklist — AWS Dev Deployment Readiness

**Track**: C — Architecture and Platform Strategy
**Created**: 2026-06-13
**Status**: Reference document for first AWS deployment

## Prerequisites (Complete Before First Deploy)

This checklist covers account-level and infrastructure-level security. It does **not** duplicate:

- [docs/security-architecture.md](../security-architecture.md) — app-level auth/RBAC/headers
- [docs/setup/pre-production-ingress-checklist.md](../setup/pre-production-ingress-checklist.md) — Nginx/TLS
- [docs/setup/sandbox-aws-profile.md](../setup/sandbox-aws-profile.md) — AWS CLI profile setup
- [infra/terraform/STATE_BACKEND_CHECKLIST.md](../../infra/terraform/STATE_BACKEND_CHECKLIST.md) — Terraform backend bootstrap

---

## Section 1: One-Time AWS Account Hardening (do before anything else)

**Scope**: solo dev, MVP, eu-central-1.

These seven steps take under 30 minutes and are irreversible risk mitigations.

**Why**: Root account compromise = game over.

### Hardening Checklist

- [ ] Enable MFA on root account (hardware key or TOTP app)
- [ ] Create a billing alert at $20 and $50 (Cost Explorer → Budgets)
- [ ] Create an IAM admin user for daily CLI work — do not use root for daily tasks
  - Group: `admins`, policy: `AdministratorAccess`
  - MFA required for this user too
- [ ] Delete or disable root access keys (IAM → Security credentials)
- [ ] Enable CloudTrail (management events, all regions, S3 bucket with encryption)
- [ ] Enable IAM Access Analyzer on the account (free, catches accidental public access)
- [ ] Enable GuardDuty (30-day free trial, then ~$4/month for dev scale — decide whether to keep)

---

## Section 2: GitHub Actions OIDC Role (no long-lived keys in Secrets)

The workflows (`ci.yml`, `cd-dev.yml`) use `vars.AWS_ROLE_ARN_DEV` via OIDC. No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in GitHub Secrets.

### Setup Steps

1. Create OIDC identity provider in IAM:

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

2. Create IAM role `github-actions-dev`:

- Trust policy: OIDC, condition `sub` = `repo:<owner>/data-pipeline-async:*`
- Permission policy: see minimal policy below

3. Set GitHub Actions variable:

Set `vars.AWS_ROLE_ARN_DEV` = `arn:aws:iam::<account-id>:role/github-actions-dev`

### Minimal IAM Policy for `github-actions-dev` (Dev Environment)

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

**Note**: Terraform `plan` and `apply` in `cd-dev.yml` also need RDS, ElastiCache, VPC, ECS task definition, IAM role creation permissions. Expand this policy once you run `TF_ENV=dev just tf plan` and see exactly what resources Terraform wants to manage. Start narrow and add permissions on demand from the CloudTrail `AccessDenied` events.

---

## Section 3: Infrastructure Bootstrap (one-time, before Terraform)

### 3.1: Create S3 State Bucket

Replace `your-terraform-state-bucket` with your actual bucket name:

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

### 3.2: Create ECR Repositories

```bash
aws ecr create-repository --repository-name data-zoo-ingestor --region eu-central-1
aws ecr create-repository --repository-name data-zoo-dashboard --region eu-central-1
```

Record the registry URL (format: `<account-id>.dkr.ecr.eu-central-1.amazonaws.com`) and set GitHub variable `vars.DEV_ECR_REGISTRY`.

### 3.3: Populate Config Files from Templates

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example \
   infra/terraform/environments/dev/backend.aws.hcl
# Edit: set bucket = "your-terraform-state-bucket"

cp infra/terraform/environments/dev/terraform.aws.tfvars.example \
   infra/terraform/environments/dev/terraform.aws.tfvars
# Edit: set TF_VAR_redis_auth_token via env var, not in file
```

Both files are gitignored. **Never commit them.**

### 3.4: Verify Bootstrap

Run:

```bash
just dev-preflight
# Expected: all [ok] lines, no [FAIL]
```

---

## Section 4: Pre-Deploy Checklist (before each `just deploy-ecs`)

Run in order:

- [ ] `just floci-validate` — Floci sandbox healthy
- [ ] `just dev-preflight` — real AWS creds + config files present
- [ ] `just deploy-audit` — image builds, size < 1.5GB, no CRITICAL CVEs
- [ ] `TF_ENV=dev just tf plan` — review changeset, no unintended destroys
- [ ] No secrets in diff (`git diff` scan or pre-commit hook)
- [ ] `just deploy-ecs` — apply reviewed plan + ECS rollout

---

## Section 5: Post-Deploy Verification

After `just deploy-ecs` completes:

- [ ] `/health` returns `{"status": "ok"}` on ALB DNS
- [ ] `/readyz` returns 200 (all health gates passed)
- [ ] `just smoke-test` passes end-to-end
- [ ] CloudTrail shows expected IAM calls in last 10 minutes (no `AccessDenied` errors)
- [ ] IAM Access Analyzer findings: zero public access findings for new resources
- [ ] Cost Explorer: no unexpected service usage (check within 24h of first deploy)

---

## Section 6: Ongoing Security Hygiene (monthly, ~10 minutes)

Recurring tasks to maintain security posture:

- [ ] Review IAM Access Analyzer findings
- [ ] Review CloudTrail for any `AccessDenied` anomalies
- [ ] `pip-audit` on local venv (CI runs this too, but confirm locally before PRs)
- [ ] Rotate `redis_auth_token` if it has been in use for >90 days
- [ ] Check AWS Trusted Advisor security tab (free checks: exposed keys, MFA on root, open security groups)

---

## Key Variables Reference

| Variable                     | Where Set                | Value                                               |
| ---------------------------- | ------------------------ | --------------------------------------------------- |
| `vars.AWS_ROLE_ARN_DEV`      | GitHub repo vars         | `arn:aws:iam::<account-id>:role/github-actions-dev` |
| `vars.DEV_ECR_REGISTRY`      | GitHub repo vars         | `<account-id>.dkr.ecr.eu-central-1.amazonaws.com`   |
| `AWS_REGION`                 | `cd-dev.yml` env         | `eu-central-1`                                      |
| `backend.aws.hcl` → `bucket` | local gitignored file    | `your-terraform-state-bucket`                       |
| `backend.aws.hcl` → `key`    | local gitignored file    | `dev/platform/terraform.tfstate`                    |
| `TF_VAR_redis_auth_token`    | shell env, never in file | strong random string                                |

---

## Related Documentation

- [docs/security-architecture.md](../security-architecture.md) — app-level auth, RBAC, headers
- [docs/setup/pre-production-ingress-checklist.md](../setup/pre-production-ingress-checklist.md) — Nginx/TLS
- [docs/setup/sandbox-aws-profile.md](../setup/sandbox-aws-profile.md) — AWS CLI profile setup
- [infra/terraform/STATE_BACKEND_CHECKLIST.md](../../infra/terraform/STATE_BACKEND_CHECKLIST.md) — Terraform state backend details
- [docs/deployment/aws-ecs.md](aws-ecs.md) — ECS deploy sequence
- [docs/deployment/deploy-runbook.md](deploy-runbook.md) — full deploy runbook
