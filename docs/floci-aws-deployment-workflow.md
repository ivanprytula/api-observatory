# Floci Sandbox Workflow

Track: A (local onboarding) -> C (deployment progression)

This document is the local AWS sandbox guide.
It intentionally avoids duplicating real AWS rollout runbooks.

Canonical real-cloud runbook:

- [docs/deployment/aws-ecs.md](deployment/aws-ecs.md)

## Objective

Use Floci to validate AWS-integrated behaviors locally before real cloud changes.

## Current Scope

- Start and stop local AWS emulator stack
- Validate S3 and SQS connectivity for the default sandbox bootstrap
- Run service-specific AWS tests only when needed; they provision their own resources
- Run sandbox e2e tests
- Run local Terraform plan and apply loops where required

## Quick Start

```bash
just sandbox-up
just test-aws-connectivity
just sandbox-test
just sandbox-down
```

## Terraform Local Development Workflow

Manage Floci infrastructure via Terraform for testing AWS-integrated resource provisioning.

**Prerequisite:** One-time workstation setup to add AWS sandbox profile.
See [docs/setup/sandbox-aws-profile.md](setup/sandbox-aws-profile.md) for instructions.

### Daily Workflow (Recommended)

```bash
# In a new terminal session: initialize once
just tf-init

# Then iterate as many times as needed (same terminal)
just tf-plan-local          # Review resources to create/modify
just tf-apply-local         # Apply the plan
just tf-plan-local          # Make changes, plan again
just tf-apply-local         # Apply the new plan
# ... repeat as needed

# Inspect state anytime (no re-init needed)
just tf-show-local          # Full resource details
just tf-state-list          # List all managed resources
```

**Key point:** `tf-init` runs once per terminal session. You don't re-run it on subsequent plan/apply iterations.

### Clean Slate (Reset All)

```bash
just tf-apply-local-fresh   # Destroy everything, re-init, plan & apply from scratch
```

### Full Teardown

```bash
just tf-destroy-local       # Remove all Floci infrastructure
```

### When to Use Each

| Command | Purpose | Frequency |
|---------|---------|-----------|
| `just tf-init` | Validate files, initialize backend, download modules | Once per terminal session |
| `just tf-plan-local` | Generate resource changes; safe to review before apply | Every iteration |
| `just tf-apply-local` | Apply the plan from above | Every iteration |
| `just tf-show-local` | Inspect deployed resource details | On demand (debugging) |
| `just tf-state-list` | List all managed resources by ID | On demand (inventory) |
| `just tf-apply-local-fresh` | Full reset: destroy → init → plan → apply | When starting from blank slate |
| `just tf-destroy-local` | Teardown all resources; keep state backend | Before session end (optional cleanup) |

### Common Pattern

```bash
# Project start
just sandbox-up
just tf-init

# Development loop
just tf-plan-local
just tf-apply-local
# ... make app/infra changes ...
just tf-plan-local
just tf-apply-local

# Session end
just tf-destroy-local
just sandbox-down
```

### Notes

- `tf-init` runs preflight validation and backend initialization only once per session
- Daily recipes (`tf-plan-local`, `tf-apply-local`) skip re-initialization overhead
- State is persisted in Floci's S3 backend; use `just tf-show-local` to view it
- Changes to `infra/terraform/environments/dev/` require `just tf-plan-local` → `just tf-apply-local`

## Expected Outcomes

- Floci container is healthy.
- AWS CLI commands work against LocalStack endpoint.
- Sandbox tests pass for configured services.

## Tooling Notes

Install wrappers with uv tools:

- `awscli-local`
- `terraform-local`

See detailed install matrix in [docs/setup/system-requirements.md](setup/system-requirements.md).

## When to Use This Doc

Use this guide when:

- developing features that call AWS APIs
- validating integration tests against local AWS emulation
- rehearsing infra changes before cloud execution

Use [docs/deployment/aws-ecs.md](deployment/aws-ecs.md) for actual AWS rollout steps.

## Related Documents

- [docs/deployment/aws-ecs.md](deployment/aws-ecs.md)
- [docs/cloud-deployment.md](cloud-deployment.md)
- [docs/deployment/cost-teardown.md](deployment/cost-teardown.md)
- [docs/setup/system-requirements.md](setup/system-requirements.md)
