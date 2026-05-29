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
- Validate S3, SQS, and DynamoDB connectivity
- Run sandbox e2e tests
- Run local Terraform plan and apply loops where required

## Quick Start

```bash
just sandbox-up
just test-aws-connectivity
just sandbox-test
just sandbox-down
```

## Optional Terraform Loop

```bash
just tf-init
just tf-plan-local
just tf-apply-local
just tf-destroy-local
```

## Expected Outcomes

- Floci container is healthy.
- AWS wrapper commands respond (`awslocal` and `tflocal`).
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
