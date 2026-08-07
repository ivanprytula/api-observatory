# Technology Decisions

This page summarizes durable choices and links to ADRs where a longer tradeoff record is useful.
Current implementation status belongs in the
[engineering evidence map](engineering-topics.md), not here.

## Recorded Decisions

| Question | Current decision | Rationale and record |
| --- | --- | --- |
| Broker | Redpanda locally; managed Kafka deferred | Kafka protocol enables replay/partition exercises without claiming the MVP needs a managed broker. [ADR 001](adr/001-kafka-vs-rabbitmq.md) |
| Vector database | Dedicated pgvector PostgreSQL for inference | Preserves service data ownership without another database engine. [ADR 015](adr/015-inference-dedicated-pgvector-postgres.md); [superseded ADR 002](adr/002-qdrant-vs-pgvector.md) |
| Frontend | Keep Streamlit until workflow complexity justifies replacement | Avoid a second build/runtime without a stable product trigger. [ADR 003](adr/003-htmx-vs-react.md) |
| Image build/security | BuildKit, dependency audit, and container scanning | Reproducible, cached builds with standard supply-chain checks. [ADR 004](adr/004-docker-buildkit-and-security-scanning.md) |
| Cloud authentication | GitHub OIDC; no long-lived AWS keys in GitHub | Short-lived, scoped credentials with auditable assumptions |
| Terraform state | S3 backend with native lockfile locking | Remote versioned state for recovery; no DynamoDB lock dependency |
| Migrations | Explicit Alembic migration step before application rollout | Startup migration ownership becomes unsafe with replicas. [ADR 007](adr/007-migration-runner-vs-sidecar.md) |
| AWS MVP | EC2 plus Docker Compose; ECS on Fargate and EKS deferred | Exercise one operational layer at a time; production migration still requires measured pressure |
| Agent workflow | Optional LangGraph graph, PostgreSQL checkpointing, human review | Explicit pause/resume and fail-open behavior. [ADR 012](adr/012-langgraph-agent.md) |
| Management vs operations | Keep product administration separate from platform access | Different identities, risks, and audit boundaries. [ADR 014](adr/014-management-vs-ops-plane.md) |
| Contract drift baseline | Compare observations with a versioned accepted baseline; confirm candidates before alerting | Prevents single-poll noise and gradual baseline creep while keeping acceptance tenant-scoped and auditable. [ADR 017](adr/017-versioned-contract-baselines.md) |
| Cloud direction | AWS is the only active infrastructure target | Keep application contracts portable, but add another IaaS provider only after exercised EC2, ECS on Fargate, and EKS evidence |

## Decision Rules

- PostgreSQL remains authoritative; Redis, Kafka, and AI integrations are optional supporting
  systems with explicit fallback behavior.
- Prefer standard libraries and established packages over custom infrastructure.
- Add a service, datastore, managed platform, or framework only after a measurable product,
  capacity, availability, or ownership trigger.
- Preserve backward compatibility through contract versioning, expand/contract migrations, and
  immutable image rollback.
- Describe local runs, labs, configuration, and unexecuted cloud plans according to their actual
  evidence status.

Add or revise an ADR only for a durable choice with meaningful alternatives or compatibility cost.
Routine implementation detail belongs in code and tests.
