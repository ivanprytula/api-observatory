# Interview Package

Use this package before the repository feels “finished.” It is a speaking and debugging aid, not a
script to memorize.

## Five-Minute Repository Tour

1. State the practical problem: a solo SaaS developer depends on APIs that can fail, slow down, or
   change contract.
2. Show the [system context](overview.md) and app/infra ownership boundary.
3. Trace source registration → scheduled probe → health sample → scorecard/incident.
4. Show one test and one telemetry signal rather than listing technologies.
5. Use the [topic index](../02-architecture/engineering-topics.md) to explain what is Core, Lab,
   Decision, Deferred, or Historical.

## Ten-Minute Demo

1. Register a source and explain SSRF validation.
2. Ingest two failed samples and show one deduplicated availability incident.
3. Acknowledge it, ingest a successful sample, and show resolution.
4. Create a breaking contract snapshot and show drift plus incident/agent evidence.
5. Open the dashboard incident table and one Prometheus/trace/log correlation path.
6. End with one explicit non-choice: why no database sharding or managed gateway exists yet.

## Architecture Defence

Be ready to defend:

- modular ingestor plus a separately owned inference service rather than many small services;
- PostgreSQL as authority, Redis/Kafka as optional supporting systems;
- in-process scheduling at current scale and why replicas create duplicate-job risk;
- outbox/inbox limits versus end-to-end delivery proof;
- application tenant filtering plus incremental RLS;
- Streamlit now, with concrete triggers for Jinja2/HTMX or a full SPA later;
- EC2/Compose as an unexecuted Stage 0 decision, not production ownership.

## Evidence Stories

### Incident story

Explain the requirement, migration, availability/latency/drift triggers, active-key deduplication,
cooldown, tenant-safe API, notification failure boundary, dashboard, metrics, tests, and rollback.

### Performance story

Use the [performance worksheet](../05-development/performance-and-failure-lab.md). Include the
query/workload, environment, measurement, bottleneck, change, result, and what remained uncertain.

### Scaling exercise

Start with the measured bottleneck. Walk 10x and 100x changes while preserving ordering, tenant
isolation, recovery, and cost. Defend when not to add sharding, Kubernetes, a gateway, another
database, or another service.

## Ownership Scorecard

The repository now supports locating all 20 topics. Personal ownership still requires teach-back
without generated notes.

| Target | Repository evidence | Personal proof required |
| --- | --- | --- |
| 20 Locate | Canonical topic index with current links and commands | Find evidence live in under two minutes |
| 12 Explain | Behavior, failure, tradeoff, and scale prompts in each entry | Explain selected flows without notes |
| 6 Operate | Auth/RLS, schema/retention, cache/resilience, incidents, broker lab, gateway lab | Diagnose, recover, and interpret signals |
| 3 Lead | Deferred sharding, gateway adoption, deployment/frontend triggers | Defend sequencing to technical and business stakeholders |

Freeze broad feature development when the core topic index and this package are demonstrable. New
work should close an evidence gap or respond to a measured trigger, not increase the technology
count.
