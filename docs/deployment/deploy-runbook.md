# Deploy Runbook — Floci Sandbox + Dev AWS ECS/Fargate

Track: C — Architecture and Platform Strategy

Canonical workflow reference for deploying the ingestor + dashboard to:

1. the local Floci sandbox emulator; and
2. the real AWS dev environment.

Command names and arguments live in the `Justfile`; the live recipe list is
`just --list --unsorted`. This runbook shows minimal deploy sequences and links
to the command reference for the full catalog:

- [docs/dev/commands.md](../dev/commands.md)

## Contents

1. [Pre-flight checklist](#pre-flight-checklist)
2. [Floci sandbox deployment](#floci-sandbox-deployment)
3. [Dev deploy (real AWS)](#dev-deploy-real-aws)
4. [Smoke test matrix](#smoke-test-matrix)
5. [Rollback procedures](#rollback-procedures)
6. [Known failure modes](#known-failure-modes)
7. [Quick reference](#quick-reference)

---

## Pre-flight checklist

Run once per session, before any deploy.

```bash
# 1. Verify host tooling
just doctor

# 2. Start the target infra
just up                         # local Docker Compose
# OR
just floci-up                   # Floci sandbox emulator

# 3. Authenticate for the target
source scripts/aws-env.sh       # sandbox/Floci only
aws sts get-caller-identity     # confirm credentials are active

# 4. Initialize Terraform backend when using Terraform
just tf init                    # sandbox by default
TF_ENV=dev just tf init         # real AWS dev
```

For real AWS dev deploys, also run:

```bash
just dev-preflight
```

---

## Floci sandbox deployment

Target: local Floci emulator with S3/SQS/ECS-shaped APIs.

### Steps

```bash
# A. Start Floci and seed the local AWS-shaped data plane
just floci-up

# B. Apply Terraform to create Floci-backed ECR, RDS, ElastiCache, ALB, and ECS
TF_ENV=sandbox just tf plan
TF_ENV=sandbox just tf apply

# C. Build, push, and deploy to Floci-backed ECS
just floci-deploy

# D. Validate Floci health and run Floci-specific E2E tests
just floci-validate
just floci-test
```

`just floci-deploy` delegates to `scripts/sandbox/deploy.sh`. It uses the
Floci ECR/ECS-shaped APIs exposed by the running Floci stack.

### One-click reset

```bash
TF_ENV=sandbox just tf destroy
just floci-down
```

For a clean sandbox rebuild after destroy:

```bash
TF_ENV=sandbox just tf fresh
just floci-deploy
```

### Sandbox network access note

Floci-provisioned ECS tasks run inside Docker containers on the `api-obs`
network. The ALB target group routes to container IPs. If smoke-tests fail with
connection refused but ECS shows running tasks, verify:

1. The ALB listener rule includes the correct path (`/`, `/api/*`,
   `/dashboard/*`).
2. The security group attached to the ALB allows inbound 80/443.
3. The target group health check path matches the container health endpoint.

---

## Dev deploy (real AWS)

Target: real AWS account (`data-zoo-dev` ECS cluster, `eu-central-1`).

### Preferred path

Push to `develop` after CI is green:

```bash
git push origin develop
```

`cd-dev.yml` fires automatically after CI success:

1. Require `dev` environment approval in GitHub Actions.
2. OIDC → AWS credentials using `AWS_ROLE_ARN_DEV`.
3. Resolve image digests from `DEV_ECR_REGISTRY`.
4. Initialize Terraform using `TERRAFORM_STATE_BUCKET_DEV`.
5. Save a Terraform plan, publish it to the workflow summary, and apply that saved plan.
6. Force new deployments for ingestor and dashboard.
7. Wait for ECS services to stabilize.
8. Smoke-test via `scripts/smoke-test.sh`; the workflow fails if no ALB DNS is available.
9. Publish GitHub step summary with image refs, Terraform status, ALB, and deploy status.

### Manual deploy

Use this when you need to run the deploy locally instead of through GitHub
Actions:

```bash
just dev-preflight
just deploy-audit

TF_ENV=dev just tf plan
just deploy-ecs
```

`just deploy-ecs` applies the reviewed saved Terraform plan, then forces new
ECS deployments for ingestor and dashboard.

### Environment variables required in GitHub

| Variable | Purpose |
|----------|---------|
| `AWS_ROLE_ARN_DEV` | OIDC role for CI to assume |
| `DEV_ECR_REGISTRY` | Dev ECR registry for image references |
| `TERRAFORM_STATE_BUCKET_DEV` | S3 bucket for the dev Terraform backend |
| `DEV_ALB_DNS` | ALB DNS for smoke-tests; workflow fails if neither this nor Terraform output is available |

---

## Smoke test matrix

Run by `scripts/smoke-test.sh`. Non-blocking dashboard checks are gracefully
skipped if the dashboard path is not reachable.

| Check | Endpoint | Expected |
|-------|----------|----------|
| Ingestor ready | `GET /readyz` | 200 |
| Ingestor health | `GET /health` | 200 |
| Metrics | `GET /metrics` | 200 |
| Scorecards list | `GET /api/v1/scorecards` | 200 |
| Sources list | `GET /api/v1/sources` | 200 |
| Job metrics | `GET /health/jobs-metrics` | 200 |
| Create observation | `POST /api/v1/observations` | 201 |
| List observations | `GET /api/v1/observations?limit=5` | 200 |
| Dashboard health | `GET /dashboard/_stcore/health` | 200 (non-blocking) |

### Smoke-test exit codes

- `0` — all checked endpoints returned expected codes.
- `1` — at least one endpoint failed; review output and investigate.

### Running smoke-tests manually

```bash
# Local Docker Compose
bash scripts/smoke-test.sh http://127.0.0.1:8000 http://127.0.0.1:8501

# Floci sandbox after deploy; substitute the actual ALB DNS when available
bash scripts/smoke-test.sh http://127.0.0.1:8000 120

# AWS dev from any machine with network access to the ALB
bash scripts/smoke-test.sh https://my-alb.eu-central-1.elb.amazonaws.com
```

---

## Rollback procedures

### Floci sandbox rollback

```bash
# Quick rollback: destroy and recreate from the current Terraform configuration
TF_ENV=sandbox just tf destroy
TF_ENV=sandbox just tf fresh
just floci-deploy
```

If images are the problem, push or build a known-good tag:

```bash
export IMAGE_TAG=<previous-commit-sha>
just floci-deploy
```

### Dev rollback

There is no automated CD rollback workflow yet.

Manual procedure:

```bash
# 1. Identify the last known-good task definition revision
aws ecs describe-services \
  --cluster data-zoo-dev \
  --services ingestor dashboard \
  --query 'services[].taskDefinition'

# 2. Re-register the old image URI on the task definition family
aws ecs describe-task-definition \
  --task-definition data-zoo-dev-ingestor \
  --query 'taskDefinition' | \
  jq '.containerDefinitions[0].image = "ghcr.io/<owner>/data-zoo-ingestor:tree-<sha>" | del(.taskDefinitionArn) | del(.revision) | del(.status)' | \
  aws ecs register-task-definition --cli-input-json -

# 3. Force a new deployment with the old task definition
aws ecs update-service \
  --cluster data-zoo-dev \
  --service ingestor \
  --force-new-deployment
```

**Recommendation:** cut a `v*` tag on `main` after every validated dev deploy.
Rollback = redeploy the last released tag.

---

## Known failure modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `docker login to ... failed` | Floci ECR auth token expired or Floci down | Restart Floci with `just floci-reset` |
| `Failed to push ...` | Registry sidecar unreachable | Check the Floci ECR registry container on the `api-obs` network |
| `ECS cluster '...' not found` | Terraform not applied | Run `TF_ENV=sandbox just tf plan` and `TF_ENV=sandbox just tf apply` |
| `ecr_repository_urls` missing from Terraform output | `enable_ecr = false` in `terraform.tfvars` | Set `enable_ecr = true` and re-apply |
| `update-service ... failed` | Service name mismatch | Verify ECS service name matches Terraform output |
| `services-stable` timeout | CrashLoopBackOff or OOM | Check CloudWatch logs / Floci task logs; roll back image tag |
| Smoke-test `/readyz` non-200 | DB migration not run or DB unreachable | Run `just migrate`; check ECS task env for `DATABASE_URL` |
| Smoke-test 401 on `/api/v1/*` | Missing/invalid bearer token | Dashboard and some endpoints require auth; `/metrics`, `/health`, `/readyz` are open |
| Dashboard health 404 at `/dashboard/_stcore/health` | ALB path-based routing not configured or dashboard task down | Check ALB listener rules; check ECS dashboard service events |
| `DEV_ALB_DNS not set and Terraform has no ALB output` | No endpoint available for smoke-tests | Set `DEV_ALB_DNS` or fix Terraform ALB output; the workflow fails closed |
| Terraform state lock timeout | Another Terraform apply is running | Wait for it to finish, or `terraform force-unlock <LOCK_ID>` if stuck |

### Floci-specific gotchas

- Floci requires rootful Docker for sibling container creation.
- Floci uses private proxy port ranges for RDS/ElastiCache.
- The ECR registry sidecar must be on the same Docker network as Floci.
- State is stored in Floci S3 at `http://127.0.0.1:4566`. If state is corrupted,
  delete the bucket key and re-init.

---

## Quick reference

| Command | Context | Purpose |
|---------|---------|---------|
| `just floci-up` | Local dev | Start Floci + Docker infra + seed S3/SQS/admin/demo |
| `just floci-down` | Local dev | Stop Floci |
| `just floci-reset` | Local dev | Restart Floci cleanly |
| `just floci-validate` | Local dev | Validate Floci health, S3, SQS, and optional API health |
| `just floci-test` | Local dev | Run Floci-specific E2E tests |
| `just tf init` | Sandbox | Init Terraform backend |
| `TF_ENV=sandbox just tf plan` | Sandbox | Plan changes |
| `TF_ENV=sandbox just tf apply` | Sandbox | Apply saved plan |
| `TF_ENV=sandbox just tf destroy` | Sandbox | Tear down Floci Terraform resources |
| `just floci-deploy` | Sandbox | Build + push + Floci ECS deploy + smoke-test |
| `TF_ENV=sandbox just tf fresh` | Sandbox | Init → plan → apply in one shot |
| `just deploy-audit` | Anywhere | Build + size check + Trivy scan |
| `TF_ENV=dev just tf plan` | Dev AWS | Plan real AWS changes |
| `TF_ENV=dev just tf apply` | Dev AWS | Apply real AWS changes |
| `just deploy-ecs` | Dev AWS | Manual ECS deploy wrapper |
| `bash scripts/smoke-test.sh <BASE_URL>` | Anywhere | Post-deploy smoke test |
