# Daily Development Workflows

Track: A - Product and Onboarding

This document explains workflow intent and sequence for active development.

Canonical command source:

- [docs/dev/commands.md](dev/commands.md)

Use this file for when and why to run each workflow, not as the full command catalog.

## Daily Cadence

Use this baseline sequence during active feature work:

1. Start with `just doctor` to verify host tooling and local workspace folders.
2. Start runtime dependencies and API service using the preferred Docker-first path.
3. Apply migrations when schema state changed or after DB reset.
4. Run fast unit checks while iterating.
5. Run integration or e2e checks before merge for affected slices.
6. Run lint and formatting gates before opening or updating a PR.
7. Shut down containers when done.

For exact commands, copy from [docs/dev/commands.md](dev/commands.md).

## Two Development Modes

### Mode 1: Docker-first (default)

Use this mode for consistency with shared team workflows and CI assumptions.

Best when:

- you need parity with service wiring in compose
- you are verifying integration behaviors
- you are validating migration and startup sequencing

### Mode 2: Infra-only plus local uvicorn

Use this mode when IDE debugging and breakpoint workflows are the priority.

Best when:

- you need faster reload cycles for app-only edits
- you need debugger attachment to local process
- you are isolating app behavior from container lifecycle

## Validation Rhythm

Fast feedback path:

- unit tests for changed paths
- focused integration tests for touched feature slices
- quality checks before each push

Release confidence path:

- full integration or e2e gates for deployment-bound changes
- migration validation when model or schema changed
- deployment smoke checks after image build and sandbox validation

## CI and PR Workflow

For PR check semantics, manual verification, and workflow composition:

- [docs/ci/workflow-reference.md](ci/workflow-reference.md)

## Related Documents

- [docs/02-first-time-setup.md](02-first-time-setup.md)
- [docs/dev/commands.md](dev/commands.md)
- [docs/dev/developer-guide.md](dev/developer-guide.md)
- [docs/floci-aws-deployment-workflow.md](floci-aws-deployment-workflow.md)
- [docs/deployment/aws-ecs.md](deployment/aws-ecs.md)
