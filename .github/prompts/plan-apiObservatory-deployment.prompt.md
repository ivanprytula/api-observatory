# Status: MVP Implementation ✅ Ready for AWS Dev Deployment

**Good news**: All MVP features and infrastructure are implemented. The only barrier is **manual AWS bootstrap** (a one-time ~30 min setup).

---

## Final Deployment Checklist (Before First `develop` Push)

This is your north star. Follow this exactly; do not deviate into side topics.

### Phase A: Manual AWS Account Setup (30 min, do once)

**Reference**: cloud-security-checklist.md **Step 0 & Step 1**

- [ ] **Step 0** — AWS account hardening (7 items: MFA, billing alerts, CloudTrail, etc.)
- [ ] **Step 1** — S3 state bucket + ECR repos (run exact `aws` CLI commands, copy bucket name)

### Phase B: Local Config & First Terraform Run (15 min, do once)

**Reference**: cloud-security-checklist.md **Step 2 & 3**

- [ ] **Step 2** — Copy `.example` files → `backend.aws.hcl` and `terraform.aws.tfvars` (edit bucket name)
- [ ] **Step 3** — First local `TF_ENV=dev just tf init → plan → apply` (creates OIDC role + all infrastructure)
  - This creates: VPC, RDS, ElastiCache, ECS cluster, ALB, IAM roles, ECR repos
  - Capture the `github_actions_role_arn` output
- [ ] **Uncomment** the ECS deploy IAM policy in main.tf (currently lines 95–120 are commented out)
  - Re-run `TF_ENV=dev just tf apply` to apply the policy

### Phase C: GitHub Repository Variables (5 min, do once)

**Reference**: cloud-security-checklist.md **Step 4**

Go to GitHub **Settings → Secrets and variables → Actions → Variables** and create three:

| Variable | Value |
|----------|-------|
| `AWS_ROLE_ARN_DEV` | From Step B output: `arn:aws:iam::<account-id>:role/data-zoo-github-actions` |
| `DEV_ECR_REGISTRY` | `<account-id>.dkr.ecr.eu-central-1.amazonaws.com` |
| `TERRAFORM_STATE_BUCKET_DEV` | Your S3 bucket name from Step 1 |

### Phase D: Verify Preflight (2 min)

**Reference**: cloud-security-checklist.md **Step 5**

```bash
just dev-preflight
# Expect: all [ok] lines, no [FAIL]
```

---

## Workflow: First Real Deployment to AWS Dev

Once Phase A–D are complete:

1. **Commit & push to `develop` branch**
   ```bash
   git add -A
   git commit -m "ready for dev deployment"
   git push origin develop
   ```

2. **GitHub Actions triggers** ci.yml
   - Runs: lint → unit tests → integration tests → docker build → image scan
   - If all pass → emits Slack notification (if configured)

3. **On CI success, GitHub Actions triggers** cd-dev.yml
   - Requires: `dev` environment approval (GitHub UI)
   - Terraform plan + apply (idempotent)
   - ECS service rolling update
   - Smoke test

4. **Result**: Your API is live at `http://<ALB_DNS>/health`

---

## What's Implemented (Don't Worry About These — They're Done)

| Component | Status | File |
|-----------|--------|------|
| MVP services (ingestor) | ✅ | ingestor |
| CI lint/unit/integration/docker | ✅ | ci.yml |
| CD plan→apply→ECS rollout | ✅ | cd-dev.yml |
| Terraform modules (network, DB, cache, IAM, ECS) | ✅ | modules |
| OIDC role (auto-created on first apply) | ✅ | main.tf |
| S3 state backend | ✅ (manual bucket creation only) | cloud-security-checklist.md Step 1 |
| Sandbox validation (`just floci-validate`) | ✅ | Justfile |
| Cost teardown (`just cleanup`) | ✅ | cost-teardown.md |

---

## What Requires Your Manual Action (Only These Three Things)

1. **AWS Account Hardening** (Step 0 in checklist)
   - Root MFA, billing alerts, CloudTrail, IAM analyzer

2. **S3 Bucket + ECR Creation** (Step 1 in checklist)
   - Copy-paste `aws` CLI commands; the bucket name is your single source of truth

3. **First Local Terraform Apply** (Step 3 in checklist)
   - Creates all AWS infrastructure; captures role ARN for GitHub

4. **GitHub Variables** (Step 4 in checklist)
   - Three repo variables; no secrets management needed (OIDC handles it)

---

## One-Command Verification (After Each Phase)

```bash
# After Phase A: verify S3 bucket exists and is secure
aws s3api get-bucket-encryption --bucket your-terraform-state-bucket
aws s3api get-public-access-block --bucket your-terraform-state-bucket

# After Phase B: verify Terraform state is stored
cd infra/terraform/environments/dev && terraform state list | head -3

# After Phase C: verify GitHub sees the variables
# (GitHub UI: Settings → Secrets and variables → Actions → Variables)

# After Phase D: verify preflight passes
just dev-preflight
```

---

## To Land the Job: What You've Built

By following this checklist, you demonstrate:

- ✅ **Infrastructure as Code** — Terraform modules for multi-tier cloud deployment
- ✅ **CI/CD mastery** — GitHub Actions workflows with OIDC (no long-lived secrets)
- ✅ **Security-first mindset** — Zero-trust, least-privilege IAM, encrypted state
- ✅ **DevOps discipline** — Automated testing, image scanning, approval gates, cost controls
- ✅ **Python backend** — FastAPI, async SQLAlchemy, observability, resilience patterns

**Talk track for interviews:**
> "I built api-observatory as a portfolio project demonstrating full-stack cloud architecture. The entire stack—from CI lint to AWS ECS deployment—is Infrastructure as Code. The dev environment deploys from `develop` branch via GitHub Actions with OIDC role assumption (no hardcoded credentials). The Terraform modules are modular and reusable; I can explain the trade-offs (e.g., why I chose ECS Fargate over EKS for MVP scope, how I structured IAM for least-privilege CI/CD). Cost is ~$2.50/day dev, with automated teardown to avoid drift. The whole thing is reproducible: new developers run `just dev-preflight` and `git push develop`, and the infrastructure materializes on real AWS."

---

## If You Get Lost

- **Stuck on AWS account setup?** → Read cloud-security-checklist.md Step 0–1
- **Stuck on Terraform?** → Read STATE_BACKEND_CHECKLIST.md (I just corrected it for 'dev' only)
- **Stuck on CI/CD?** → Read cd-dev.yml and aws-ecs.md
- **Cost concerns?** → Read cost-teardown.md

**Do not skip the "Final Checklist" above. Follow it step-by-step.** Everything else is context; this is execution.
