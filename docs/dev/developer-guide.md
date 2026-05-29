# Developer Guide

Track: B - Engineering Execution

This guide is the operational handbook for day-to-day development.

Command policy for this repo:

- Canonical command source: [docs/dev/commands.md](commands.md)
- Onboarding sequence: [docs/02-first-time-setup.md](../02-first-time-setup.md)
- Workflow intent and cadence: [docs/03-daily-development.md](../03-daily-development.md)

This file intentionally avoids duplicating long command blocks.

## Prerequisites

- Docker and Docker Compose
- Python tooling managed by uv
- just command runner

Run host checks first:

```bash
just doctor
```

## First-Time Setup

Bootstrap once after clone, then start and migrate the stack using the exact sequence in [docs/02-first-time-setup.md](../02-first-time-setup.md).

## Daily Development Loop

Use the daily sequence from [docs/03-daily-development.md](../03-daily-development.md), and copy exact commands from [docs/dev/commands.md](commands.md).

## Test Strategy

Use test lane commands from [docs/dev/commands.md](commands.md#tests).

Testing policy summary:

- Run the unit lane on every feature iteration.
- Run integration or e2e lanes before merge for persistence and cross-service paths.
- Run migration checks whenever schema-affecting model changes are introduced.

## Debugging Workflow

Debugging entrypoints are documented in [docs/dev/commands.md](commands.md) and [docs/dev/gotchas.md](gotchas.md).

Debugging policy summary:

- Prefer `just db-reset` when state corruption is suspected.
- Use container logs before stepping into app internals.
- Switch to local uvicorn only when IDE-level debugging is required.

## Load Testing

Quick baseline checks with simple HTTP clients are acceptable for smoke validation.
For repeatable and scripted load, use k6 scenarios when available in this repository.

Suggested sequence:

1. Verify functional path first with regular API tests.
2. Run a small baseline load sample.
3. Increase concurrency gradually and inspect latency, error rate, and saturation.

## Adding a New Endpoint (6 steps)

1. Add request and response schemas in the service schema module.
2. Implement repository function with AsyncSession as first parameter.
3. Add a thin router handler with explicit status codes.
4. Add unit or integration tests for happy path and failure path.
5. Run format, lint, and tests.
6. Update API-facing docs and Bruno collection if endpoint is public.

## Adding a New Service (future)

Use this pattern for new services:

- Keep shared logic in libs/platform or other libs modules.
- Avoid importing service internals across service boundaries.
- Give each service a clear ownership boundary and runtime contract.
- Start with a minimal Docker service and health endpoint, then add dependencies.

## Floci Sandbox Workflow

Use this only when developing or validating AWS-integrated flows:

Follow the local sandbox sequence in [docs/floci-aws-deployment-workflow.md](../floci-aws-deployment-workflow.md).

## Pre-Deployment Gate Checklist

- All required tests for the changed scope pass.
- Lint, format, and type checks pass.
- Migrations are present for schema-affecting model changes.
- Security scans and dependency checks are clean for release candidate images.
- Docs are updated for behavior or operational workflow changes.

## Extending Observability

When adding features, include observability from day one:

- Structured logs with request or task context.
- Metrics for throughput, errors, and duration.
- Tracing spans for external calls and expensive operations.
- Dashboard and alert updates for newly critical paths.

See also:

- [docs/observability.md](../observability.md)
- [docs/dev/commands.md](commands.md)
- [docs/dev/gotchas.md](gotchas.md)
