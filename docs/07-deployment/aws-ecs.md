# AWS ECS Deployment Guide

Track: C — Architecture and Platform Strategy

This guide defines the operational sequence for Phase 11 deployment work:
image audit, local Floci validation, and AWS ECS rollout steps.

## Scope

This project deploys to AWS ECS/Fargate.

Use these docs as source of truth:

- Cloud Deployment Model
- Floci AWS Workflow
- Deploy Runbook
- Cost Teardown
- Commands Reference

This guide shows deployment workflow examples only. For exact recipe names,
arguments, and compatibility aliases, use the Commands Reference.

## Terraform Variables for Local Sandbox

`TF_ENV=sandbox just tf plan` uses the sandbox Terraform defaults when not
provided:

- `TF_VAR_aws_region=us-east-1`
- `TF_VAR_aws_profile=default`
- `TF_VAR_availability_zones=["us-east-1a","us-east-1b"]`
- `TF_VAR_cache_auth_token=local-dev-cache-token`
- `TF_VAR_enable_messaging=false`

Override any value inline as needed (see `infra/terraform/` for full variable list).

## AWS ECS Rollout (Real Cloud)

Use the deploy runbook for deployment sequences:

- **[Deploy runbook](deploy-runbook.md)** — manual rollout, image audit, post-deploy verification
- **Smoke tests** — post-deploy verification
- **GitHub CD** — push to `develop` triggers `cd-dev.yml` (preferred path)
- **Image scanning** — `just deploy-audit` (build → size audit → Trivy scan)

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
through the edge HTTPS proxy. The `/api/*` path continues to route to the
ingestor API. The dashboard service gets its own ECS task and target group on
port 8501.
