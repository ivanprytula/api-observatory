# AWS ECS Deployment Guide

Track: C — Architecture and Platform Strategy

This guide defines the operational sequence for Phase 11 deployment work:
image audit, local Floci validation, and AWS ECS rollout steps.

## Scope

This project deploys to AWS ECS/Fargate.

Use these docs as source of truth:

- [Cloud deployment model](../cloud-deployment.md)
- [Floci local workflow](../floci-aws-deployment-workflow.md)
- [Deploy runbook](../deployment/deploy-runbook.md)
- [Cost teardown checklist](../deployment/cost-teardown.md)
- [Dev command reference](../dev/commands.md)

This guide shows deployment workflow examples only. For exact recipe names,
arguments, and compatibility aliases, use [docs/dev/commands.md](../dev/commands.md).

## Prerequisites

- Docker and Docker Compose
- Terraform
- AWS CLI
- No local Trivy install required; scan runs via Docker Compose service
- **First-time AWS deployment**: Complete [Cloud Security Checklist](cloud-security-checklist.md) before proceeding.

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

1. Docker build for `api-observatory:local`.
2. MVP size audit with default budget 1.5GB.
3. Trivy scan with `--severity CRITICAL --exit-code 1` via compose service.

Run local stack smoke checks after image audit:

```bash
just up
just api-check
just down
```

## Phase 13b: Floci Sandbox + Terraform Plan

MSK messaging is disabled by default in dev Terraform (`enable_messaging = false`)
to avoid unnecessary spend in sandbox workflows.

Run the full Floci validation chain:

```bash
just floci-up
just floci-validate
TF_ENV=sandbox just tf plan
TF_ENV=sandbox just tf apply
just floci-test
TF_ENV=sandbox just tf destroy
just floci-down
```

For a plan-only rehearsal, stop after `TF_ENV=sandbox just tf plan`.

## Terraform Variables for Local Sandbox

`TF_ENV=sandbox just tf plan` uses the sandbox Terraform defaults when not
provided:

- `TF_VAR_aws_region=us-east-1`
- `TF_VAR_aws_profile=default`
- `TF_VAR_availability_zones=["us-east-1a","us-east-1b"]`
- `TF_VAR_cache_auth_token=local-dev-cache-token`
- `TF_VAR_enable_messaging=false`

Override any value inline if needed:

```bash
TF_ENV=sandbox TF_VAR_enable_messaging=true just tf plan
```

## AWS ECS Rollout (Real Cloud)

The preferred path is the GitHub CD Dev workflow: push to `develop` after CI is
green and let `cd-dev.yml` deploy.

For a manual real AWS rollout, use the deploy runbook sequence:

```bash
just dev-preflight
just deploy-audit

TF_ENV=dev just tf plan
just deploy-ecs
```

`just deploy-ecs` applies the reviewed saved Terraform plan and then forces new
ECS deployments for ingestor and dashboard. The GitHub CD workflow requires
`dev` environment approval and fails if no ALB DNS is available for smoke tests.

## Streamlit Dashboard (Separate Container)

The Streamlit dashboard runs as a dedicated `dashboard` container, not embedded
in ingestor. It connects to the ingestor API via `INGESTOR_URL`.

### Local access

- Dashboard is available at `http://127.0.0.1:8501` when running via `just up`
  or `docker compose up -d dashboard`.
- The `INGESTOR_URL` environment variable, set to `http://ingestor:8000` in
  compose, tells Streamlit where to reach the API.
- Both services start independently via `docker compose up -d ingestor dashboard`.

### Cloud access (ALB)

When deployed via the ECS rollout, the dashboard is served at `/dashboard/`
through the edge HTTPS proxy:

```bash
curl -f https://<alb-dns>/dashboard/
```

The `/api/*` path continues to route to the ingestor API. The dashboard service
gets its own ECS task and target group on port 8501.

## Verification Gates

Run test gates after deployment/doc changes:

```bash
DATABASE_URL_TEST=sqlite+aiosqlite://:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```
