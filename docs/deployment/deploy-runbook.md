# Deploy Runbook — Sandbox + Dev (AWS ECS/Fargate)

Track: C — Architecture and Platform Strategy

Canonical source of truth for deploying the ingestor + dashboard to
(1) the Floci sandbox emulator and (2) the real AWS dev environment.

## Contents

1. [Pre-flight checklist](#pre-flight-checklist)
2. [Sandbox deploy (Floci)](#sandbox-deploy-floci)
3. [Dev deploy (real AWS)](#dev-deploy-real-aws)
4. [Smoke test matrix](#smoke-test-matrix)
5. [Rollback procedures](#rollback-procedures)
6. [Known failure modes](#known-failure-modes)
7. [Quick reference](#quick-reference)

---

## Pre-flight checklist

Run once per session, before any deploy.

```bash
# 1. Verify host
just doctor

# 2. Start infra (local or Floci depending on target)
just up                              # local Docker Compose
# OR
just sandbox-up                      # Floci emulator for sandbox/terraform

# 3. Authenticate AWS
source scripts/aws-env.sh            # sets AWS_REGION, ECR_ENDPOINT, etc.
aws sts get-caller-identity          # confirm credentials are active

# 4. Verify Terraform backend (sandbox only)
just tf-init                         # one-time per terminal session
```

---

## Sandbox deploy (Floci)

Target: local Floci emulator (real containers, loopback ECR at `127.0.0.1:5100-5199`).

### Steps

```bash
# A. Apply Terraform (creates ECR repos, RDS, ElastiCache, ALB, ECS)
just tf-plan
just tf-apply

# B. Build, push, and deploy
just sandbox-deploy
```

`sandbox-deploy` runs the full chain:

1. Read ECR URIs from Terraform output
2. Authenticate Docker against Floci ECR
3. Build ingestor + dashboard images, tag with `${IMAGE_TAG:-develop}`
4. Push images to Floci registry
5. Re-register ECS task definitions with fresh image URIs
6. `update-service --force-new-deployment` for both services
7. `wait services-stable` (blocking, up to 2 minutes per service by default)
8. **Run smoke-test script** (`scripts/smoke-test.sh`) against the ALB DNS or `localhost`
9. Print ALB DNS + ECS service state summary

### One-click reset

```bash
just tf-destroy   # tears down all sandbox resources
just sandbox-down # stops Floci container
```

### ECS_MOCK mode (local dev without real AWS)

For faster local iteration, set `ECS_MOCK=true`:

```bash
ECS_MOCK=true just sandbox-deploy
```

With ECS_MOCK, ECS task definitions register straight to RUNNING without
waiting for real container pulls. Useful for testing the deploy script logic
without the full Floci data plane.

### Sandbox network access note

Floci-provisioned ECS tasks run inside Docker containers on the `api-obs` network.
The ALB target group routes to container IPs. If smoke-tests fail with connection
refused but ECS shows RUNNING tasks, verify:

1. The ALB listener rule includes the correct path (`/`, `/api/*`, `/dashboard/*`)
2. The security group attached to the ALB allows inbound 80/443
3. The target group health check path matches the container's health endpoint

---

## Dev deploy (real AWS)

Target: real AWS account (`data-zoo-dev` ECS cluster, `eu-central-1`).

### Trigger

Push to `develop` after CI is green:

```bash
git push origin develop
```

`cd-dev.yml` fires automatically on CI success:

1. OIDC → AWS credentials (`AWS_ROLE_ARN_DEV`)
2. Resolve image digests (`ghcr.io/<owner>/data-zoo-<service>:tree-<sha>`)
3. `update-service --force-new-deployment` for ingestor
4. `wait services-stable` for ingestor
5. `update-service --force-new-deployment` for dashboard
6. `wait services-stable` for dashboard
7. **Smoke-test** via `scripts/smoke-test.sh` against `https://${DEV_ALB_DNS}`
8. Publish GitHub step summary (ingestor + dashboard image refs + status)

### Manual trigger

```bash
# Re-run from GitHub UI: Actions → CD Dev → Run workflow
# OR push a no-op commit to develop:
git commit --allow-empty -m "trigger dev deploy" && git push
```

### Environment variables required in GitHub

| Variable | Purpose |
|----------|---------|
| `AWS_ROLE_ARN_DEV` | OIDC role for CI to assume |
| `DEV_ALB_DNS` | ALB DNS for smoke-tests (without it smoke-tests are skipped) |

---

## Smoke test matrix

Run by `scripts/smoke-test.sh`. Non-blocking dashboard checks are
gracefully skipped if the dashboard path is not reachable.

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

- `0` — all checked endpoints returned expected codes
- `1` — at least one endpoint failed; review output and investigate

### Running smoke-tests manually

```bash
# Local Docker Compose
bash scripts/smoke-test.sh http://127.0.0.1:8000 http://127.0.0.1:8501

# Floci sandbox (after deploy, substitute actual ALB DNS)
bash scripts/smoke-test.sh http://127.0.0.1:8000 120

# AWS dev (from any machine with network access to the ALB)
bash scripts/smoke-test.sh https://my-alb.eu-central-1.elb.amazonaws.com
```

---

## Rollback procedures

### Sandbox rollback

```bash
# Quick rollback: destroy and recreate from last known good tfplan
just tf-destroy
just tf-fresh    # init → plan → apply

# OR manual:
just tf-apply    # re-apply previous plan (if tfplan file still exists)
```

If images are the problem, push a known-good tag:

```bash
export IMAGE_TAG=<previous-commit-sha>
just sandbox-deploy
```

### Dev rollback

There is no automated CD rollback workflow yet.
Manual procedure:

```bash
# 1. Identify last known-good task definition revision
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

# 3. Force new deployment with old task def
aws ecs update-service \
  --cluster data-zoo-dev \
  --service ingestor \
  --force-new-deployment
```

**Recommendation:** Cut a `v*` tag on `main` after every validated dev deploy.
Rollback = redeploy the last released tag.

---

## Known failure modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `docker login to ... failed` | Floci ECR auth token expired or Floci down | Restart Floci: `just sandbox-reset` |
| `Failed to push ...` | Registry sidecar unreachable | Check `floci-ecr-registry` container is running on `api-obs` network |
| `ECS cluster '...' not found` | Terraform not applied | Run `just tf-apply` |
| `ecr_repository_urls` missing from Terraform output | `enable_ecr = false` in `terraform.tfvars` | Set `enable_ecr = true` and re-apply |
| `update-service ... failed` | Service name mismatch | Verify ECS service name matches Terraform output |
| `services-stable` timeout | CrashLoopBackOff or OOM | Check CloudWatch logs / Floci task logs; roll back image tag |
| Smoke-test `/readyz` non-200 | DB migration not run or DB unreachable | `just migrate`, check ECS task env for `DATABASE_URL` |
| Smoke-test 401 on `/api/v1/*` | Missing/invalid bearer token | Dashboard and some endpoints require auth; `/metrics`, `/health`, `/readyz` are open |
| Dashboard health 404 at `/dashboard/_stcore/health` | ALB path-based routing not configured or dashboard task down | Check ALB listener rules; check ECS dashboard service events |
| `DEV_ALB_DNS not set — skipping smoke tests` | GitHub var not configured | Set `DEV_ALB_DNS` in repo Settings → Variables |
| Terraform state lock timeout | Another `tf apply` running | Wait for it to finish, or `terraform force-unlock <LOCK_ID>` if stuck |

### Floci-specific gotchas

- Floci requires **rootful Docker** (sibling container creation). Rootless Docker cannot create the ECS backend containers.
- Floci uses **private proxy port ranges** for RDS/ElastiCache (7001-7099, 6379-6399) — no host port conflicts.
- The ECR registry sidecar (`registry:2` container) must be on the **same Docker network** (`api-obs`) as Floci.
- State is stored in Floci S3 at `http://127.0.0.1:4566`. If state is corrupted, delete the bucket key and re-init.

---

## Quick reference

| Command | Context | Purpose |
|---------|---------|---------|
| `just sandbox-up` | Local dev | Start Floci + Docker infra |
| `just sandbox-down` | Local dev | Stop Floci |
| `just sandbox-reset` | Local dev | Restart Floci cleanly |
| `just tf-init` | Sandbox | Init Terraform backend |
| `just tf-plan` | Sandbox | Plan changes |
| `just tf-apply` | Sandbox | Apply plan |
| `just tf-destroy` | Sandbox | Tear down all resources |
| `just sandbox-deploy` | Sandbox | Build + push + ECS deploy + smoke-test |
| `just tf-fresh` | Sandbox | init → plan → apply in one shot |
| `just deploy-audit` | Anywhere | Build + size check + Trivy scan |
| `bash scripts/smoke-test.sh <BASE_URL>` | Anywhere | Post-deploy smoke test |
| `just sandbox` | Local dev | Full sandbox loop: up → seed → AWS tests |
| `just deploy-dev` | Local dev trigger | Push to `develop` to trigger CD Dev |
