# Floci Sandbox Workflow

Track: A (local onboarding) → C (deployment progression)

This document explains the local AWS-shaped Floci sandbox. It is for rehearsing
AWS-integrated behavior before real cloud changes.

This doc shows minimal workflow examples only. For exact recipe names,
arguments, and compatibility aliases, use the command reference:

- [docs/dev/commands.md](dev/commands.md)

Canonical real-cloud runbook:

- [docs/deployment/deploy-runbook.md](deployment/deploy-runbook.md)

## Objective

Use Floci to validate AWS-integrated behaviors locally before real cloud changes.

## Current Scope

- Start and stop the local AWS emulator stack.
- Validate S3 and SQS connectivity for the default sandbox bootstrap.
- Run Floci-specific E2E tests when AWS-shaped behavior is affected.
- Run Terraform plan/apply loops against the sandbox environment.
- Deploy ingestor and dashboard to the Floci-backed ECS simulator.

## Quick Start

```bash
# Start Floci, seed S3/SQS, start Compose infra, migrate, and seed admin/demo
just floci-up

# Validate Floci health, S3, SQS, and optional API health
just floci-validate

# Run Floci-specific E2E tests
just floci-test

# Stop Floci only; Compose data-plane can keep running
just floci-down
```

`just floci-up` is the main entrypoint. It starts Floci, creates the local S3
bucket and SQS queue, starts the Compose data-plane, applies migrations, and
seeds admin/demo data.

## Terraform Local Development Workflow

Manage Floci infrastructure via Terraform for testing AWS-integrated resource
provisioning.

**Prerequisite:** one-time workstation setup to add the AWS sandbox profile.
See [docs/setup/sandbox-aws-profile.md](setup/sandbox-aws-profile.md).

### Daily Workflow

```bash
# Initialize the sandbox backend once per terminal session
just tf init

# Review resource changes
TF_ENV=sandbox just tf plan

# Apply the saved plan
TF_ENV=sandbox just tf apply

# Inspect Terraform state when debugging
TF_ENV=sandbox just tf show
```

For a full reset from the current Terraform configuration:

```bash
TF_ENV=sandbox just tf fresh
```

### Clean Slate

Use this when you want to destroy current Floci Terraform resources and recreate
them from scratch:

```bash
TF_ENV=sandbox just tf destroy
TF_ENV=sandbox just tf fresh
```

### Full Teardown

Use this at the end of a Floci session:

```bash
TF_ENV=sandbox just tf destroy
just floci-down
```

## Deploy to Floci ECS

After Terraform has created the Floci ECS resources, deploy the current local
images to the Floci-backed ECS simulator:

```bash
just floci-deploy
```

`just floci-deploy` delegates to `scripts/sandbox/deploy.sh` and uses the
Floci ECR/ECS-shaped APIs exposed by the running Floci stack.

## Common Pattern

```bash
# Project start
just floci-up
just floci-validate

# Terraform iteration
just tf init
TF_ENV=sandbox just tf plan
TF_ENV=sandbox just tf apply

# Deploy and test
just floci-deploy
just floci-test

# Session end
TF_ENV=sandbox just tf destroy
just floci-down
```

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

See the detailed install matrix in [docs/setup/system-requirements.md](setup/system-requirements.md).

## When to Use This Doc

Use this guide when:

- developing features that call AWS APIs;
- validating integration tests against local AWS emulation;
- rehearsing infra changes before cloud execution;
- deploying to the local Floci ECS simulator.

Use [docs/deployment/deploy-runbook.md](deployment/deploy-runbook.md) for the
combined sandbox + real AWS deployment workflow.

## Related Documents

- [docs/dev/commands.md](dev/commands.md)
- [docs/deployment/deploy-runbook.md](deployment/deploy-runbook.md)
- [docs/deployment/aws-ecs.md](deployment/aws-ecs.md)
- [docs/deployment/cost-teardown.md](deployment/cost-teardown.md)
- [docs/setup/sandbox-aws-profile.md](setup/sandbox-aws-profile.md)
- [docs/setup/system-requirements.md](setup/system-requirements.md)
