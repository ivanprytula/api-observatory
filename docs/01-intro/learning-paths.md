# Architecture-First Learning Path

The goal is progressive ownership, not memorizing every line. Use the canonical
[`engineering-topics.md`](../02-architecture/engineering-topics.md) to locate concepts, then
study one critical flow at a time.

## Session Method

For each flow, follow:

`purpose → architecture → code → data → dependencies → failure → proof → tradeoff`

Inspect no more than three production files and two test files in one session. End with a verbal
teach-back, a debugging exercise, and one focused proof command. Progress through the ownership
levels: **Locate → Explain → Operate → Lead**.

## Critical Flows

1. **Authenticated API request and tenant isolation** — JWT claims, authorization policy,
   tenant context, and PostgreSQL RLS.
2. **Source registration and scheduled probing** — source contract, scheduler lifecycle,
   bounded external HTTP, and persisted health samples.
3. **Scorecard calculation** — rolling-window SQL, indexes, query plan, and latency tradeoffs.
4. **Contract snapshot and drift detection** — fingerprints, compatibility classification,
   persisted drift, and real-time publication.
5. **Outbox, Kafka, inbox, DLQ, and replay** — transaction boundary, idempotency, ordering,
   poison-message handling, and recovery.
6. **Cache, pub/sub, and WebSocket delivery** — fail-open cache behavior, ephemeral fan-out,
   reconnect gaps, and backpressure.
7. **Agent enrichment and human review** — deterministic trigger, RAG boundary, provider
   fallback, Postgres checkpoint, approval, and evaluation.
8. **Deployment, telemetry, failure, and rollback** — app/infra ownership, health/readiness,
   logs, metrics, traces, migration order, and rollback evidence.

## Lead-Level Practice

For each flow, defend what should remain simple at current scale, which measurement would trigger
more complexity, what changes at 10x and 100x load, and how the decision affects the solo SaaS
developer who depends on the system. Do not claim expertise from catalogue coverage alone; record
repeated diagnosis, measurement, recovery, and revised decisions.
