# ADR 007: Migration Runner vs Sidecar for Cloud Deploys

Track: C — Architecture and Platform Strategy


## Status

Proposed

## Date

2026-04-24

## Context

Phase 7 introduces cloud deployment on ECS Fargate. Database migrations must run before service rollout and must not execute from FastAPI app startup.

The roadmap policy now defines a strict split:

- Alembic is authoritative for persistent-local and production-like environments.
- create_all is allowed only in explicitly ephemeral-local contexts.
- Migration failure blocks rollout.

We need a deployment-time execution model for Alembic in production-like environments.

## Decision Drivers

- Safety: avoid double-runs, race conditions, and partial rollout.
- Operational clarity: one observable migration step per release.
- Rollback control: explicit app rollback and controlled downgrade path.
- Compatibility with CI migration gate and revision checks.

## Options

### Option A: One-shot migration runner task (recommended candidate)

Run a dedicated task/job before service rollout:

- Build image
- Run alembic upgrade head once
- Verify current revision at head
- Roll ECS services

Pros:

- Single, explicit execution point.
- Easy to make blocking and observable in pipeline.
- Prevents app startup from carrying migration responsibility.

Cons:

- Requires deployment orchestration step.
- Needs idempotency and lock protection in runner execution.

### Option B: Sidecar migration container per service deploy

Bundle migration behavior into sidecar container attached to service rollout.

Pros:

- Co-locates migration artifact with service release unit.
- Potentially simpler packaging for some teams.

Cons:

- Higher risk of repeated or concurrent migration attempts.
- Harder to reason about global execution ordering.
- More complex failure handling across rolling updates.

## Current Recommendation

Prefer Option A (one-shot migration runner) for Phase 7 implementation.

## Consequences

Positive:

- Clear separation of schema migration from app lifecycle.
- Stronger deploy gate semantics.
- Better auditability of migration step outcome.

Negative:

- Additional pipeline orchestration logic.
- Requires explicit runbook ownership.

## Validation Criteria

- Fresh database: upgrade head succeeds.
- Idempotency path: downgrade base then upgrade head succeeds in CI.
- Schema object checks pass (extensions, views, partitions, indexes).
- Deployment dry run executes migration task successfully before rollout.

## Related References

- .github/prompts/plan-dataZooPlatform.prompt.md
- .github/workflows/ci.yml
- alembic/env.py
- Gotchas reference
- Decisions document
