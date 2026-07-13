# Floci Sandbox Workflow

Track: A (local onboarding) → C (deployment progression)

This document explains the local AWS-shaped Floci sandbox. It is for rehearsing
AWS-integrated behavior before real cloud changes.

This doc shows minimal workflow examples only. For exact recipe names,
arguments, and compatibility aliases, use the command reference:

- Commands reference

Canonical real-cloud runbook:

- Deploy Runbook

## Objective

Use Floci to validate AWS-integrated behaviors locally before real cloud changes.

## Current Scope

- Start and stop the local AWS emulator stack.
- Validate S3 and SQS connectivity for the default sandbox bootstrap.
- Run Floci-specific E2E tests when AWS-shaped behavior is affected.
- Run Terraform plan/apply loops against the sandbox environment.
- Deploy ingestor and dashboard to the Floci-backed ECS simulator.

## Quick Start

`just floci-up` is the main entrypoint. It starts Floci, creates the local S3
bucket and SQS queue, starts the Compose data-plane, applies migrations, and
seeds admin/demo data. See the "Deploy Runbook" for the full
Floci workflow and available `just floci-*` commands.

## Terraform Local Development Workflow

Manage Floci infrastructure via Terraform for testing AWS-integrated resource
provisioning.

**Prerequisite:** one-time workstation setup to add the AWS sandbox profile.
See the "Sandbox AWS Profile" guide.

### Daily Workflow

See the "Commands" reference for Terraform recipe names (`tf init`, `tf plan`, `tf apply`, `tf show`). See the "Deploy Runbook" for the full Floci Terraform loop.

### Clean Slate / Full Teardown

See the "Deploy Runbook" for destroy and teardown commands.
The general pattern: `TF_ENV=sandbox just tf destroy` then `just floci-down`.

## Deploy to Floci ECS

After Terraform has created the Floci ECS resources, deploy the current local
images to the Floci-backed ECS simulator via `just floci-deploy` (delegates to
`scripts/sandbox/deploy.sh`). See the "Deploy Runbook" for
the full workflow.

## Notes

- Floci must be enabled in `docker-compose.yml` before `just floci-up` can start it.
- Use `TF_ENV=sandbox` for Floci Terraform operations.
- Use `TF_ENV=dev` for real AWS dev Terraform operations.
- The Justfile is the source of truth for recipe names and arguments; run
  `just --list --unsorted` from the repo root for the live recipe list.
- Older `sandbox-*` aliases still exist for compatibility, but new docs should
  use canonical `floci-*` names.

## Expected Outcomes

- Floci container is healthy at `http://127.0.0.1:4566/_floci/health`.
- AWS CLI commands work against the Floci endpoint.
- The local S3 bucket and SQS queue are reachable.
- Floci-specific E2E tests pass for the configured services.

## Tooling Notes

Install wrappers with uv tools when needed:

- `awscli-local`
- `terraform-local`

See the detailed install matrix in the "System Requirements" guide.

## When to Use This Doc

Use this guide when:

- developing features that call AWS APIs;
- validating integration tests against local AWS emulation;
- rehearsing infra changes before cloud execution;
- deploying to the local Floci ECS simulator.

Use the "Deploy Runbook" for the
combined sandbox + real AWS deployment workflow.

## Related Documents

- Commands reference
- Deploy Runbook
- AWS ECS
- Cost Teardown
- Sandbox AWS Profile
- System Requirements
