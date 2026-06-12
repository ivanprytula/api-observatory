# AWS ECS Deployment Guide

Track: C — Architecture and Platform Strategy

This guide defines the operational sequence for Phase 11 deployment work (commits 13a-13c): image audit, local sandbox validation, and AWS ECS rollout steps.

## Scope

This project deploys to AWS ECS/Fargate.

Use these docs as source of truth:

- [Cloud deployment model](../cloud-deployment.md)
- [Floci local workflow](../floci-aws-deployment-workflow.md)
- [Cost teardown checklist](cost-teardown.md)

## Prerequisites

- Docker and Docker Compose
- Terraform (install via standard package manager)
- AWS CLI (install with standard installer)
- No local Trivy install required (scan runs via Docker Compose service)

Run host checks first:

```bash
just doctor
```

## Phase 13a: Image Audit and Scan

Build and verify the deployment image gate:

```bash
just deploy-audit
```

This gate performs:

1. `docker build` for `api-observatory:local`
2. MVP size audit (default budget 1.5GB; informational for full feature coverage)
3. Trivy scan with `--severity CRITICAL --exit-code 1` via compose service

Run local stack smoke checks after image audit:

```bash
docker compose up -d
docker compose down
```

## Phase 13b: Floci Sandbox + Terraform Plan

MSK messaging is disabled by default in dev Terraform (`enable_messaging = false`) to avoid unnecessary spend in sandbox workflows.

Run the full sandbox validation chain:

```bash
just sandbox-up
just tf-plan-local
just sandbox-test
just tf-destroy-local
just sandbox-down
```

## Terraform Variables for Local Sandbox

`just tf-plan-local` uses these defaults when not provided:

- `TF_VAR_aws_region=us-east-1`
- `TF_VAR_aws_profile=default`
- `TF_VAR_availability_zones=["us-east-1a","us-east-1b"]`
- `TF_VAR_cache_auth_token=local-dev-cache-token`
- `TF_VAR_enable_messaging=false`

Override any value inline if needed:

```bash
TF_VAR_enable_messaging=true just tf-plan-local
```

## AWS ECS Rollout (Real Cloud)

From [infra/terraform/environments/dev](../../infra/terraform/environments/dev):

```bash
terraform init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="key=data-zoo/dev/terraform.tfstate" \
  -backend-config="region=<aws-region>" \
  -backend-config="use_lockfile=true"

terraform plan
terraform apply
```

Then validate the workload endpoint:

```bash
curl -f https://<alb-dns>/docs
```

## Streamlit Dashboard (Separate Container)

The Streamlit dashboard runs as a dedicated `dashboard` container, not embedded in ingestor. It connects to the ingestor API via `INGESTOR_URL`.

### Local access

- Dashboard is available at `http://localhost:8501` when running via `just up` or `docker compose up -d dashboard`.
- The `INGESTOR_URL` environment variable (set to `http://ingestor:8000` in compose) tells Streamlit where to reach the API.
- Both services start independently via `docker compose up -d ingestor dashboard`.

### Cloud access (ALB)

When deployed via the ECS rollout, the dashboard is served at `/dashboard/` through the edge HTTPS proxy:

```bash
curl -f https://<alb-dns>/dashboard/
```

The `/api/*` path continues to route to the ingestor API. The dashboard service gets its own ECS task and target group on port 8501.

## Verification Gates

Run test gates after deployment/doc changes:

```bash
DATABASE_URL_TEST=sqlite+aiosqlite://:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```
