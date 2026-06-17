# Deployment Guide

Track: C — Architecture and Platform Strategy

---

## Gap #3: DevOps/SRE Promotion Checklist

Use this linear pre-prod → prod checklist for every deployment cycle.

### Pre-Flight (every deploy session)
- [ ] `just doctor` — host tooling verified
- [ ] `just up` — local stack healthy
- [ ] `just floci-validate` — Floci sandbox healthy
- [ ] `aws sts get-caller-identity` — correct AWS credentials active

### Pre-Deploy (before `just deploy-ecs`)
- [ ] `just dev-preflight` — real AWS creds + config files present
- [ ] `just deploy-audit` — image builds, size < 1.5 GB, no CRITICAL CVEs
- [ ] `TF_ENV=dev just tf plan` — review changeset; no unintended destroys
- [ ] No secrets in diff (pre-commit scan passes)
- [ ] CI green on the commit being deployed

### Deploy
- [ ] `TF_ENV=dev just tf apply` (or: push to `develop` for CI/CD path)
- [ ] `just deploy-ecs` — forces new ECS deployments for ingestor + dashboard
- [ ] Wait for ECS services to stabilize

### Smoke Test
- [ ] Ingestor ready: `GET /readyz` → 200
- [ ] Ingestor health: `GET /health` → 200
- [ ] Metrics: `GET /metrics` → 200
- [ ] Scorecards: `GET /api/v1/scorecards` → 200
- [ ] Sources: `GET /api/v1/sources` → 200
- [ ] Create observation: `POST /api/v1/observations` → 201
- [ ] Dashboard: `GET /dashboard/_stcore/health` → 200
- [ ] `bash scripts/smoke-test.sh <alb-dns>` — full automated smoke suite

### Post-Deploy
- [ ] CloudWatch logs: no crash loops or OOM
- [ ] Prometheus targets: all up
- [ ] Cost: verify no unexpected resource creation

### Rollback
- [ ] Known-good image tag identified
- [ ] Manual: `aws ecs update-service --service <name> --force-new-deployment --region <region>`

---

## Deployment Model

This project deploys to **AWS ECS/Fargate**. Kubernetes is a separate learning path.

### Architecture

```text
Internet → Route53 → ALB → ECS services (private subnets)
  → RDS PostgreSQL
  → ElastiCache Cache
  → Messaging (MSK, when enabled)
```

### Why ECS/Fargate

- Minimal control-plane burden
- Simple deployment primitives (`aws ecs update-service`)
- Straightforward CI/CD integration (GitHub OIDC)
- Predictable cost profile for small-to-medium service counts

### Dev vs Prod Environment Split

| Resource | Dev | Prod |
|----------|-----|------|
| Fargate | Spot (70% savings) | On-Demand |
| RDS | `db.t3.micro` | `db.t3.medium` Multi-AZ |
| Cache | `cache.t3.micro` | `cache.t3.small` + replica |
| NAT Gateways | 1 (cost-optimized) | 3 (HA) |
| ECS replicas | 1 per service | 2 per service |
| Log retention | 14 days | 90 days |
| Monthly cost | ~$85 | ~$280 |

---

## Deploy Runbook

### Floci Sandbox Deploy

```bash
just floci-up                              # start Floci + seed
TF_ENV=sandbox just tf plan && just tf apply  # Terraform
just floci-deploy                          # build, push, deploy
just floci-validate                        # health check
just floci-test                            # E2E tests
```

### Dev Deploy (GitHub Actions)

Push to `develop` after CI is green:

1. `cd-dev.yml` fires automatically
2. OIDC → AWS credentials using `AWS_ROLE_ARN_DEV`
3. Resolve image digests from `DEV_ECR_REGISTRY`
4. Terraform plan + apply
5. Force new ECS deployments
6. Wait for services to stabilize
7. Smoke-test via `scripts/smoke-test.sh`

### Dev Deploy (Manual)

```bash
just dev-preflight
just deploy-audit
TF_ENV=dev just tf plan
just deploy-ecs
```

### Required GitHub Variables

| Variable | Purpose |
|----------|---------|
| `AWS_ROLE_ARN_DEV` | OIDC role for CI to assume |
| `DEV_ECR_REGISTRY` | Dev ECR registry |
| `TERRAFORM_STATE_BUCKET_DEV` | S3 backend for Terraform state |
| `DEV_ALB_DNS` | ALB DNS for smoke-tests |

---

## Cloud Security Checklist (AWS Dev)

### Step 0: One-Time Account Hardening

- [ ] Enable MFA on AWS root account
- [ ] Create billing budgets ($20 / $50)
- [ ] Create IAM admin user (no root for daily tasks)
- [ ] Delete/disable root access keys
- [ ] Enable CloudTrail (management events, all regions)
- [ ] Enable IAM Access Analyzer
- [ ] Enable GuardDuty (evaluate after 30-day trial)

### Step 1: Bootstrap S3 State Bucket

```bash
aws s3api create-bucket --bucket "<name>" --region eu-central-1 --create-bucket-configuration LocationConstraint=eu-central-1
aws s3api put-bucket-versioning --bucket "<name>" --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket "<name>" --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

Create ECR repos: `aws ecr create-repository --repository-name data-zoo-ingestor` (also `data-zoo-dashboard`).

### Step 2: Configure Local Files

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example infra/terraform/environments/dev/backend.aws.hcl
# Edit: set bucket = "your-terraform-state-bucket"
cp infra/terraform/environments/dev/terraform.aws.tfvars.example infra/terraform/environments/dev/terraform.aws.tfvars
```

### Step 3: First Terraform Apply (bootstraps OIDC role)

```bash
TF_ENV=dev just tf init
TF_ENV=dev just tf plan && TF_ENV=dev just tf apply
```

### Step 4: Set GitHub Variables

`AWS_ROLE_ARN_DEV`, `DEV_ECR_REGISTRY`, `TERRAFORM_STATE_BUCKET_DEV`

### Step 5: Verify Preflight

```bash
just dev-preflight    # all [ok]
```

---

## Cost Teardown

### Local Sandbox

```bash
TF_ENV=sandbox just tf destroy
just floci-down
docker compose down -v
```

### AWS Dev

```bash
terraform destroy
```

Verify: no ALB, ECS services, RDS instance, ElastiCache cluster, or MSK resources remaining.

### Cost Estimates

| Profile | Daily | Notes |
|---------|-------|-------|
| Local sandbox | $0 | Containers only |
| AWS dev (no MSK) | ~$2.50 | Network + baseline |
| AWS dev (with MSK) | ~$5.14 | Adds messaging |

**Safety:** Never leave `terraform apply` environments idle overnight without a teardown decision. Keep `enable_messaging=false` unless actively testing Kafka.

---

## Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `docker login to ... failed` | Floci ECR auth expired | `just floci-reset` |
| `ECS cluster not found` | Terraform not applied | Run `just tf plan && just tf apply` |
| `services-stable` timeout | CrashLoopBackOff / OOM | Check CloudWatch logs; roll back image |
| Smoke test `/readyz` non-200 | DB migration not run | `just migrate` |
| Smoke test 401 | Missing bearer token | Auth required on some endpoints; `/health`, `/readyz`, `/metrics` are open |
| `TERRAFORM_STATE_BUCKET_DEV not set` | GitHub variable missing | Set in repo Settings → Variables |
| Terraform state lock timeout | Another apply running | Wait or `terraform force-unlock` |

---

## Governance Checklist (Pre-Prod)

1. Environment protections enabled (protected branches)
2. OIDC role wiring verified
3. Deployment secrets scoped per environment
4. Rollback path documented and tested
5. Cost teardown steps prepared
6. Pre-production ingress hardened (see specialized-setups)

### Prod Hardening (deferred — required before prod)

- [ ] S3 state bucket: deny-non-TLS policy, access logging, lifecycle for noncurrent versions
- [ ] IAM: replace SSE-S3 with KMS CMK, tighten OIDC sub condition to specific workflow refs
- [ ] `cd-prod.yml`: fill OIDC block (currently commented out)
- [ ] Separate prod IAM role with narrower permissions
- [ ] Enable AWS Config + Security Hub
- [ ] Add `terraform force-unlock` emergency workflow

---

## Related Documents

- [CI/CD Reference](../06-ci-cd/ci-cd.md) — workflow semantics
- [Setup Guide](../04-setup/setup-guide.md) — local dev bootstrap
- [Specialized Setups](../04-setup/specialized-setups.md) — ingress hardening, Ansible
- [Observability](../08-operations/observability.md) — monitoring and alerting
