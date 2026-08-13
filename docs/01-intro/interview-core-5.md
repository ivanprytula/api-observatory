# Interview Core 5

Five flows that form the complete narrative of this system.
Everything else is supporting evidence or a learning exercise.

---

## 1. Source Registration and Health Probing

**The story**: A developer registers an external API source. The ingestor
periodically probes it, records health samples, and computes scorecards.

**End-to-end path**:

1. `POST /api/v1/sources` — register source with URL, schedule, and SSRF allow-list.
2. `JobScheduler` registers a probe job per source on startup.
3. `run_source_probe` fetches the source, times the response, and writes a
   `ProviderHealthSample`.
4. Scorecard job aggregates samples into time-window availability/latency/drift.
5. If thresholds breach, `open_or_update_incident` creates a dependency incident.

**Evidence**:

- `services/ingestor/jobs_registry.py` — job registration
- `services/ingestor/jobs/probes.py:run_source_probe` — probe execution
- `services/ingestor/repositories/scorecards.py` — aggregation
- `services/ingestor/repositories/incidents.py` — incident lifecycle
- Integration tests at `services/ingestor/tests/integration/test_source_probe_jobs.py`

**Interview line**: "I start with source registration because every other flow
depends on having a monitored upstream. The scheduler is in-process APScheduler,
which is fine for a single-replica dev/portfolio scale."

---

## 2. Observation Ingestion

**The story**: A client POSTs observations. The ingestor validates, deduplicates,
writes to PostgreSQL, and publishes an event for downstream consumers.

**End-to-end path**:

1. `POST /api/v1/observations` — JWT-authenticated, rate-limited, validated by Pydantic.
2. Repository layer inserts with `ON CONFLICT DO NOTHING` dedup.
3. `publish_observation_created` emits to Redis pub/sub (an optional,
   fail-open side effect for WebSocket fan-out) and optionally to Kafka
   (when broker is enabled).
4. Response returns the created observation.

**Evidence**:

- `services/ingestor/routers/observations.py` — production CRUD routes
- `services/ingestor/repositories/observations.py` — dedup insert
- `services/ingestor/events.py` — Kafka publisher (fail-open)
- `services/ingestor/pubsub.py` — Redis pub/sub bridge
- `services/ingestor/routers/ws.py` — WebSocket fan-out

**Interview line**: "PostgreSQL is the source of truth. The write path is
synchronous and fails fast. Redis pub/sub is an optional fail-open side effect
for real-time WebSocket updates, not a primary path. Kafka is a tertiary,
feature-gated path for transactional outbox — it's a learning exercise, not
the default."

---

## 3. Contract Drift and Incident Triage

**The story**: A source contract changes. The ingestor snapshots the new contract,
detects drift, opens an incident, and the LangGraph agent triages it.

**End-to-end path**:

1. Scheduled job fetches the source's OpenAPI/schema and stores a `ContractSnapshot`.
2. `ContractBaseline` holds the last-known-good. Diffing produces `DriftEvent`s.
3. `open_or_update_incident` creates a breaking/breaking-warning incident.
4. If `anthropic_enabled`, the LangGraph agent classifies severity and drafts
   root-cause analysis.
5. Incident is visible in the dashboard and via `GET /api/v1/incidents`.

**Evidence**:

- `services/ingestor/routers/contract_drift.py` — snapshot and drift endpoints
- `services/ingestor/repositories/contract_drift.py` — baseline storage
- `services/ingestor/agent/` — LangGraph triage graph
- `services/ingestor/repositories/incidents.py` — incident lifecycle
- Eval suite under `services/ingestor/agent/evals/`

**Interview line**: "Contract drift is the differentiator. I don't just monitor
uptime — I monitor schema changes. The agent is gated behind an LLM API key,
so the core drift detection works without AI, but the triage agent adds
explainability when needed."

---

## 4. Tenant Isolation and Row-Level Security

**The story**: Multi-tenant data is isolated at the middleware, query, and
database layers so one tenant never sees another's data.

**End-to-end path**:

1. `TenantMiddleware` extracts `X-Tenant-ID` or JWT `tid` claim and sets
   `tenant_context`.
2. All repository queries filter by `tenant_id`.
3. When `RLS_ENABLED=true`, PostgreSQL RLS policies enforce the same filter at
   the storage layer as a defense-in-depth guarantee.
4. `jwt_role_guard` enforces `viewer` / `writer` / `admin` roles on every
   non-auth route.

**Evidence**:

- `services/ingestor/core/tenant.py` — tenant context and middleware
- `services/ingestor/security/authorization.py` — RBAC evaluation
- `services/ingestor/database.py` — session.info tenant tagging
- `alembic/versions/*_enable_observations_rls.py` — RLS migration
- `tests/integration/test_observations_rls.py` — cross-tenant leak test

**Interview line**: "Tenant isolation is three layers: middleware for request
context, query filters for application safety, and PostgreSQL RLS for storage
enforcement. If any layer forgets, the next layer catches it."

---

## 5. Notification Delivery with Failure Boundaries

**The story**: An incident or drift event triggers a notification. The delivery
path is direct by default, with an optional transactional broker path for
at-least-once semantics.

**End-to-end path**:

1. `open_or_update_incident` calls `dispatch_notification` after DB commit.
2. `notification_delivery_mode=direct` — HTTP calls to Slack/Telegram/email
   happen inline, fail-open, and are logged.
3. `notification_delivery_mode=broker` — a `NotificationDelivery` outbox record
   is written transactionally; a separate consumer reads and dispatches.
4. If the cache/broker is unavailable, `publish()` logs a warning and returns —
   the write path never blocks.

**Evidence**:

- `services/ingestor/core/incident_notifications.py` — dispatch boundary
- `services/ingestor/notifications.py` — provider adapters
- `services/ingestor/repositories/notification_delivery.py` — outbox repository
- `services/ingestor/notification_delivery_consumer.py` — Kafka consumer
- `tests/unit/core/test_notifications.py` — provider unit tests

**Interview line**: "Notifications are fail-open by design. If Slack is down,
the incident is still recorded in PostgreSQL. The broker path is a learning
exercise in transactional outbox — it's feature-gated and not part of the
default stack."

---

## What to Skip in the First Ten Minutes

- Inference service (separate service, started with `--profile inference`; LangGraph agent gated by `ANTHROPIC_ENABLED`)
- Kafka consumer / notification-delivery worker (lab path)
- LangGraph agent details (show the drift detection first, mention the agent
  as a gated enhancement)
- Redis cache / vector search (optional supporting systems)
- Terraform / AWS deployment (designed, not executed)

If the interviewer asks about a skipped component, answer with one sentence and
return to the Core 5 flow.
