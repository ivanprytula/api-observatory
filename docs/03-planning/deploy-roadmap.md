# Deploy Roadmap — Code → Cloud

**Goal:** Run the full code→deploy→smoke-test loop, then expand to real AWS and new services.

**Rule:** Do the phases **in order**. Each phase has a gate — you must pass it before moving on. No detours into "fixing minor things". If a step fails, fix only that step, then keep going.

---

## Phase 0 — Prerequisites (one-time)

| # | Step | Check |
|---|------|-------|
| 0.1 | Docker running | `docker ps` |
| 0.2 | `uv` installed | `uv --version` |
| 0.3 | AWS CLI sandbox profile has credentials | `aws configure list --profile sandbox \| grep -q access_key` |
| 0.4 | Sandbox Terraform config files exist | `ls infra/terraform/environments/sandbox/terraform.tfvars` + `backend.hcl` |

**Gate:** 0.1–0.4 green. Run each check exactly once. If one fails, fix it, recheck, move on.

---

## Phase 1 — Sandbox loop (local AWS emulator, zero cost)

The full loop: start stack → terraform → build+push → deploy → smoke test → destroy.

| # | Step | Command | Expected |
|---|------|---------|----------|
| 1.1 | Start data-plane + Floci | `just floci-up` | All containers running, S3 bucket + SQS queue seeded |
| 1.2 | Create ECR registry sidecar | Auto-started with `just floci-up` via `docker compose` | `docker ps --filter name=floci-ecr-registry` shows running |
| 1.3 | Init Terraform backend | `TF_ENV=sandbox just tf init` | Backend initialized |
| 1.4 | Review infrastructure plan | `TF_ENV=sandbox just tf plan` | Shows resources to create — skim the output for unexpected changes |
| 1.5 | Visualize the architecture | `just tf-diagram png` | PNG diagram in `.local-dev/diagrams/data-zoo-sandbox.png` |
| 1.6 | Provision infra | `TF_ENV=sandbox just tf apply` | VPC, ALB, ECR repos, RDS, ElastiCache, ECS cluster created |
| 1.7 | Build images + push to ECR + deploy to ECS | `just floci-deploy` | Images pushed, task defs re-registered, ECS services stable |
| 1.8 | Validate sandbox health | `just floci-validate` | All 5 checks pass |
| 1.9 | Run E2E tests against deployed stack | `just floci-test` | All tests pass |
| 1.10 | Clean up sandbox | `TF_ENV=sandbox just tf destroy` | All resources deleted |

**Gate:** 1.1–1.9 pass. If 1.7 or 1.9 fails, investigate the specific error, fix it, re-trigger from 1.4, do NOT fix unrelated issues. If you find a minor bug, note it in a TODO and keep going.

> **1.2 details:** Now handled automatically by `just floci-up` — the `floci-ecr-registry` service is defined in `docker-compose.yml` under the `aws` profile. If you previously created the container manually, remove it first: `docker rm -f floci-ecr-registry`.

**Reinforcement loop:** Run 1.2 → 1.6 three times. Each iteration should be faster. Goal: complete the full loop in under 10 minutes.

---

## Phase 2 — Understand each layer

Now that Phase 1 works, pause and **inspect** each piece. Do NOT change anything.

| # | Step | What to look for |
|---|------|-----------------|
| 2.1 | `docker build -t test-ingestor . && docker history test-ingestor` | Multi-stage layers, cache hits, which files end up in the final image |
| 2.2 | Read `infra/terraform/modules/compute/main.tf` (first 100 lines) | How ALB, target groups, and ECS task definitions connect |
| 2.3 | `aws ecs describe-services --cluster data-zoo-sandbox --services ingestor --endpoint-url http://127.0.0.1:4566` | Running tasks, task definition ARN, deployment status |
| 2.4 | `scripts/smoke-test.sh` (full read) | What endpoints are checked post-deploy — that's your SLA |
| 2.5 | `just floci-test` output detail | What e2e tests actually verify against the deployed stack |

**Gate:** You can explain (out loud or to yourself) the data flow from `git push` → container → ECS task → ALB → HTTP response. If not, re-read the relevant Terraform module.

---

## Phase 3 — Real AWS dev deployment

Same loop, real AWS. Requires an AWS account with permissions.

| # | Step | Command | Expected |
|---|------|---------|----------|
| 3.1 | Create S3 bucket for Terraform state | `aws s3 mb s3://your-tf-state-bucket` | Bucket created |
| 3.2 | Create Terraform backend config | `cp infra/terraform/environments/dev/backend.aws.hcl.example infra/terraform/environments/dev/backend.aws.hcl` | Edit with your bucket name |
| 3.3 | Create Terraform variable overrides | `cp infra/terraform/environments/dev/terraform.aws.tfvars.example infra/terraform/environments/dev/terraform.aws.tfvars` | Edit with your values |
| 3.4 | Run preflight | `just dev-preflight` | All checks pass |
| 3.5 | Init + plan | `TF_ENV=dev just tf init && TF_ENV=dev just tf plan` | Plan shows resources to create |
| 3.6 | Apply | `TF_ENV=dev just tf apply` | Real AWS infra provisioned |
| 3.7 | Build + push + deploy | `IMAGE_TAG=$(git rev-parse HEAD) just deploy-ecs` | ECS rolling update, smoke test passes |
| 3.8 | Verify via ALB | `curl http://$(aws elbv2 describe-load-balancers --query 'LoadBalancers[0].DNSName' --output text)/health` | 200 OK |

**Gate:** 3.7 smoke test passes. If it fails, check ECS task logs: `aws ecs describe-tasks --cluster data-zoo-dev --tasks $(aws ecs list-tasks --cluster data-zoo-dev --query 'taskArns[0]' --output text)`. Fix the deployment issue, NOT unrelated code.

**Reinforcement loop:** Run 3.7 twice. First with a code change (edit any test, commit, push), second with no change (just re-deploy the same tag to verify idempotency).

---

## Phase 4 — CI/CD automation

| # | Step | What happens |
|---|------|-------------|
| 4.1 | Push a branch to `develop` | CI workflow triggers: lint → unit tests → docker build → Trivy scan → integration tests |
| 4.2 | Merge PR to `develop` | CI again → CD Dev workflow triggers: Terraform plan/apply → ECS update → smoke test |
| 4.3 | Create a `v*` tag and push | Release workflow: build → sign → SBOM → attest → push to GHCR |
| 4.4 | Verify CD Prod stub is still a stub | READ the comment at top of `.github/workflows/cd-prod.yml` — it's a TODO template |

**Gate:** 4.1 and 4.2 run end-to-end without manual `just deploy-ecs`. If the OIDC IAM role isn't set up, read `infra/terraform/modules/iam/main.tf` to understand the GitHub Actions OIDC trust policy, then run 3.6 to create it.

---

## Phase 5 — Post-MVP: add remaining services

The 5 services without Dockerfiles: `analytics`, `inference`, `processor`, `webhook`, `portal`.

| # | Step | |
|---|------|-|
| 5.1 | Pick one service (start with `processor` — simplest) | Read its code, understand its entry point |
| 5.2 | Create its Dockerfile (copy pattern from `Dockerfile`) | Multi-stage, uv install, non-root user, healthcheck |
| 5.3 | Add ECR repo + ECS task def to Terraform `ecr_services` | One variable addition + module call |
| 5.4 | Build + push to sandbox Floci ECR | Verify it deploys via existing `just floci-deploy` |
| 5.5 | Add smoke test check for the new service | One `check` line in `scripts/smoke-test.sh` |
| 5.6 | Repeat 5.1–5.5 for the next service | |

**Gate:** Sandbox loop passes with the new service included. The new service appears in `floci-validate` and smoke test output.

**Important:** Do NOT optimize the Dockerfile yet. Do NOT add service mesh or K8s. Do NOT "fix" the existing services while adding new ones. One service per cycle, deploy, validate, move on.

---

## Phase 6 — post-MVP: monitoring in the cloud

| # | Step | |
|---|------|-|
| 6.1 | Enable Prometheus/Grafana for real AWS | Add `monitoring` module to dev Terraform |
| 6.2 | Deploy the stack to real AWS dev | Re-run Phase 3 with monitoring |
| 6.3 | Create one CloudWatch alarm | e.g., ALB 5xx > 1% for 5 minutes |
| 6.4 | Verify you get the alert | Trigger the alarm by hitting a bad endpoint |

**Gate:** You can see the deployed service metrics in a real Grafana dashboard (or CloudWatch if you skip Grafana).

---

## Anti-detour rules

Read this every time you feel the urge to "just fix this one thing":

1. **The sandbox costs nothing** — destroy it, tweak code, rebuild, re-deploy. Do not fix code in the middle of a deploy loop.
2. **If a test fails:** fix only the failing test or the broken assertion. Do not refactor the test suite.
3. **If a lint warning appears:** ignore it, finish the deploy, then create a GitHub Issue labeled `tech-debt` with the warning. Do not fix it inline.
4. **If you find a bug during Phase 1:** does it block the deploy? Yes → fix it, re-deploy. No → file an Issue, keep going.
5. **The goal is the loop, not the code.** Speed over perfection. You can refactor after you've done the full loop 3 times.

---

## Quick reference — all commands

```bash
# Phase 1 — Sandbox (local)
just floci-up
TF_ENV=sandbox just tf init
TF_ENV=sandbox just tf plan
just tf-diagram png
TF_ENV=sandbox just tf apply
just floci-deploy
just floci-validate
just floci-test
TF_ENV=sandbox just tf destroy

# Phase 3 — Real AWS dev
just dev-preflight
TF_ENV=dev just tf plan
TF_ENV=dev just tf apply
IMAGE_TAG=$(git rev-parse HEAD) just deploy-ecs

# Phase 4 — CI/CD
git push origin develop
# → watch `.github/workflows/ci.yml` in GitHub Actions
# → then `.github/workflows/cd-dev.yml`

# Phase 5 — Add service
#  1. Create services/<name>/Dockerfile
#  2. Add "name" to ecr_services in terraform.tfvars
#  3. Add smoke test check
#  4. Re-run Phase 1
```
