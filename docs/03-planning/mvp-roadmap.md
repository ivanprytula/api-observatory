# Current Roadmap and Evolution Triggers

The repository is a locally runnable backend/platform portfolio project. The standing product
example is a small SaaS developer monitoring third-party APIs; permanent hosting, billing,
customer acquisition, and speculative scale work are out of scope.

## Current State

- **Core:** source registry, scheduled health/contract probes, scorecards, tenant-scoped incidents,
  auth, migrations, retention, resilience controls, dashboard, and optional agent/inference paths.
- **Lab:** gateway/load-balancing, Kafka partitioning, k3d, monitoring, cloud emulators, and bounded
  performance/failure exercises.
- **Decision:** AWS MVP uses three immutable images on EC2 Compose with RDS; configuration and
  contract checks exist, but no completed live deployment is claimed.
- **Deferred:** managed gateway/Kafka, ECS/EKS, database sharding, multi-region, and a replacement
  frontend require measured product or operational pressure.
- **Local event consumer:** notification delivery has a separately owned, opt-in Redpanda consumer
  process with at-least-once semantics. It is local implementation evidence, not a production
  operations claim; see [ADR 016](../02-architecture/adr/016-redpanda-consumer-service.md).

The [engineering evidence map](../02-architecture/engineering-topics.md) owns topic-level status;
ADRs own technology rationale.

## Near-Term Priorities

### 1. Keep the critical product slice demonstrable

Trace source registration → scheduled probe → health sample → scorecard/incident → operator action.
Completion means the behavior is locally reproducible, tenant-safe, observable, covered by focused
tests, and explainable without relying on a technology list.

### 2. Strengthen proof before adding breadth

Use captured query plans, performance baselines, fault/recovery timing, authorization regressions,
and deterministic agent evaluation. Add a tool only when it closes a named evidence gap.

### 3. Validate AWS MVP only as a separately approved exercise

Before any live proof, validate the three image contracts locally, review Terraform cost and
security, configure short-lived OIDC identities, define rollback/teardown, and obtain explicit
approval for cloud mutations. Until then the status remains **Decision**.

## Change Decision

Plan any change as one vertical slice:

1. State the user failure or cost being reduced.
2. Place behavior in the current service unless ownership or scaling evidence requires another.
3. Define API/event/schema compatibility and data migration.
4. Bound dependencies, timeouts, retries, payloads, and failure behavior.
5. Include tests, telemetry, rollout, rollback, and documentation impact.

## Transformation Triggers

| Proposed change | Evidence required first |
| --- | --- |
| New service/runtime | Independent ownership, release cadence, scaling profile, or isolation SLO |
| Multiple ingestor replicas | Saturation/availability target plus explicit scheduler ownership |
| ECS or Kubernetes | Repeated Compose delivery friction or several independently operated workloads |
| Managed gateway | Multiple public services or consumer-specific edge policy |
| Managed Kafka | Sustained asynchronous workload with ordering, replay, and availability objectives |
| Additional Redpanda consumer service | A named asynchronous workflow with an ownership, isolation, replay, or throughput objective beyond notification delivery; record the boundary in [ADR 016](../02-architecture/adr/016-redpanda-consumer-service.md) |
| Database partitioning/sharding | Measured single-node limit after query, index, and retention work |
| New frontend | Stable workflow requiring richer interaction, client state, deep links, or UI testing |
| Multi-region | Recovery objective that backup/restore in one region cannot meet |

When a trigger is met, record an ADR and update the relevant contract, proof, and rollback path in
the same change. Git history carries completed work; this roadmap stays current.
