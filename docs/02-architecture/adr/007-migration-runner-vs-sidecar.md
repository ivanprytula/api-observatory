# ADR 007: One-Shot Migration Runner

## Status

Accepted on 2026-07-31. This decision supersedes the earlier proposed ECS/Fargate-specific wording.

## Context

Alembic is authoritative for persistent local and deployment databases. Migrations must complete
before a changed application image serves traffic, but they must not run from FastAPI startup or
from one sidecar per replica. Those alternatives create duplicate execution, ordering, and rollback
ambiguity.

Local Docker Compose is canonical. AWS MVP uses the same application images on one EC2 Compose
host, with a separate optional inference database.

## Decision

Run each selected service's migration command once as an explicit blocking step before application
replacement:

```bash
docker compose run --rm --no-deps ingestor alembic upgrade head
docker compose --profile inference run --rm --no-deps inference \
  alembic -c services/inference/alembic.ini upgrade head
```

The inference command runs only when the reviewed `inference` profile is enabled. Migration failure
stops delivery before `docker compose up -d` replaces application containers.

CI independently proves fresh upgrade, current-head checks, and the supported downgrade/upgrade
path. Application changes use expand/contract sequencing so the previous and next image sets remain
compatible during best-effort rollback.

## Consequences

Benefits:

- one explicit and observable migration execution per selected database;
- the same image and Alembic configuration are used locally and during MVP delivery;
- application startup remains focused on serving traffic;
- no sidecar, leader election, or replica coordination is required.

Costs and limits:

- deployment orchestration owns migration ordering;
- a successful schema upgrade is not automatically reversible;
- image rollback cannot safely undo a breaking migration;
- future replicas or managed orchestration must retain a single migration owner.

## Validation

- Application CI validates ingestor and inference migrations against isolated PostgreSQL databases.
- Local onboarding runs `just db-migrate` through the configured ingestor container.
- The app-owned rollout runs selected migrations before application replacement and aborts on failure.
- Rollback documentation requires backward-compatible migrations across both image sets.

## References

- [Application CI](../../../.github/workflows/ci.yml)
- [Local database lifecycle](../../../just/database-lifecycle.just)
- [AWS MVP rollout](../../../deployment/aws-mvp/rollout.sh)
- [AWS MVP deployment contract](../../07-deployment/app-repo-contract.md)
