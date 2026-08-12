# Domain Model

Track: C — Architecture and Platform Strategy

This document maps every persistent entity and key schema in the ingestor service to its
role in Domain-Driven Design terms. Use it to understand *what a thing is* and *why it
exists*, rather than just what columns it has.

Code references: [`services/ingestor/models.py`](../../services/ingestor/models.py),
[`services/ingestor/api_schemas/`](../../services/ingestor/api_schemas/)

---

## Bounded Contexts

The ingestor service contains four bounded contexts. Each context owns its models and
enforces its invariants independently.

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Source Registry        │  Reliability Monitoring                   │
│  SourceProfile          │  ProviderHealthSample                     │
│                         │  ProviderScorecard (computed, no table)   │
├─────────────────────────┼───────────────────────────────────────────┤
│  Contract Drift         │  Identity & Access                        │
│  ContractSnapshot       │  User                                     │
│  DriftEvent             │  UserTenant                               │
│                         │  ApiKey                                   │
├─────────────────────────┼───────────────────────────────────────────┤
│  Observation Ingestion  │  Security & Abuse                         │
│  Observation            │  SecurityAuditEvent                       │
│                         │  AbuseSignal                              │
├─────────────────────────┴───────────────────────────────────────────┤
│  Messaging Infrastructure (cross-cutting)                           │
│  ProcessedEvent  ·  OutboxEvent  ·  InboxConsumption                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Source Registry

### Aggregate Root: `SourceProfile`

A `SourceProfile` is a registered external API or data source that the platform monitors.
It is the central configuration object: probe workers, scorecard queries, contract drift
checks, and health checks all start by looking up a `SourceProfile`.

| Field                    | Meaning                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------ |
| `name`                   | Unique slug used across the system to identify the source (e.g. `httpbin`, `payments-api`) |
| `base_url`               | The URL probe workers connect to                                                           |
| `health_check_path`      | Path appended to `base_url` for liveness probes                                            |
| `probe_interval_seconds` | How often a scheduler fires a probe for this source                                        |
| `is_active`              | Soft-disable without deleting; inactive sources are excluded from scheduling               |

#### Invariants

- `name` is globally unique — two sources cannot share an identifier.
- `health_check_path` must be an absolute path (starts with `/`).
- `base_url` must be a valid HTTP/HTTPS URL; loopback addresses are rejected (SSRF
  prevention).

**DDD role:** Aggregate root. All probe scheduling, scorecard computation, and drift
detection reference a `SourceProfile.id`. Deleting or deactivating a source propagates
intent to all downstream contexts through the `is_active` flag rather than a hard delete.

---

## Reliability Monitoring

### Aggregate Root: `ProviderHealthSample`

### Computed view: `ProviderScorecard` (no ORM table — derived by SQL aggregation)

### ProviderHealthSample

One probe result: did the source respond, how fast, and with what HTTP status. The probe
scheduler inserts a row here every `probe_interval_seconds` for every active source.

| Field                | Meaning                                                                                            |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| `source_id`          | FK to the `SourceProfile` that was probed                                                          |
| `sampled_at`         | When the probe ran (UTC)                                                                           |
| `latency_ms`         | Round-trip time in milliseconds                                                                    |
| `is_success`         | True if the source responded within the timeout with a 2xx status                                  |
| `http_status`        | HTTP status code, if the source responded at all                                                   |
| `response_body_hash` | SHA-256 of the response body — lets contract drift detect body changes without storing the payload |
| `error_message`      | Failure reason when `is_success = false`                                                           |
| `region`             | Optional label for multi-region probing (`eu-west-1`, etc.)                                        |

**DDD role:** Domain event recorded as a fact. Rows are append-only in practice —
a sample is never updated after insertion. The aggregate is the time-series of samples
per source, not any single row.

### ProviderScorecard (computed)

Not a table. Computed on demand from `ProviderHealthSample` rows using a single
PostgreSQL aggregate query with `PERCENTILE_CONT`.

| Field                               | Meaning                                                                                               |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `uptime_pct`                        | Percentage of probes that succeeded in the window                                                     |
| `p50_latency_ms` / `p95_latency_ms` | Latency distribution (median and 95th percentile)                                                     |
| `error_budget_burn_rate`            | How fast the source consumes its SLO budget. 1.0 = on track; >1.0 = will exhaust before window closes |
| `window_days`                       | The look-back window (default 7 days)                                                                 |
| `slo_target_pct`                    | The uptime target the burn rate is computed against (default 99.9%)                                   |

**DDD role:** Read model / projection. It is the domain's primary answer to "how reliable
is this source right now?" — derived, never stored, always fresh.

---

## Contract Drift

### Aggregate Root: `ContractSnapshot`

### Domain Event: `DriftEvent`

### ContractSnapshot

A point-in-time observation of the schema a source's API payload carries. Each time the
ingestor receives a payload from a source, it can submit a snapshot of the schema it
observed. The service fingerprints and diffs consecutive snapshots.

| Field                 | Meaning                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------- |
| `source_id`           | The source whose contract this describes                                                 |
| `payload_schema`      | The observed JSON schema (nested objects are flattened for diff)                         |
| `schema_fingerprint`  | SHA-256 of the canonical schema string — used to short-circuit diff when nothing changed |
| `compatibility_score` | 0–100 float; 100 = identical to previous; lower = more fields changed                    |
| `schema_version`      | Optional producer-supplied version label                                                 |

**Invariant:** If a new snapshot's fingerprint equals the previous snapshot's fingerprint,
no diff runs and no `DriftEvent` is emitted. This is the fingerprint short-circuit.

### DriftEvent

Created automatically when two consecutive snapshots differ. Records exactly what changed
between the previous and current snapshot.

| Field                 | Meaning                                                         |
| --------------------- | --------------------------------------------------------------- |
| `event_type`          | `breaking`, `non_breaking`, or `none`                           |
| `severity`            | `critical`, `high`, `medium`, `low`, or `none`                  |
| `added_fields`        | Fields present in the new schema but not in the old             |
| `removed_fields`      | Fields present in the old schema but not in the new             |
| `type_changed_fields` | Fields present in both schemas but with a different type        |
| `compatibility_score` | Quantified impact; mirrors the score on the associated snapshot |
| `summary`             | Human-readable description of what changed                      |

**DDD role:** Domain event. Once emitted it is immutable. A `DriftEvent` is the system's
answer to "did this API's contract change, and how bad is it?" It also triggers a Cache
pub/sub message that fans out to WebSocket clients in real time.

---

## Observation Ingestion

### Aggregate: `Observation`

An `Observation` is an inbound data point — a timestamped, tagged JSON payload from an
external source. This is the primary write path of the service.

| Field          | Meaning                                                                         |
| -------------- | ------------------------------------------------------------------------------- |
| `source`       | Origin identifier: hostname, service name, or sensor ID (no loopback addresses) |
| `timestamp`    | When the observation occurred (naive UTC; future timestamps are rejected)       |
| `raw_data`     | Arbitrary JSON payload; no schema enforced at the API layer                     |
| `tags`         | Lowercase string labels for filtering and grouping                              |
| `processed`    | Whether downstream processing (enrichment, analysis) has run                    |
| `processed_at` | When processing completed                                                       |
| `tenant_id`    | Optional tenant scope for multi-tenant deployments                              |

#### Invariants

- `(source, timestamp)` is unique — the same source cannot produce two observations at
  identical timestamps. This drives idempotent upsert: a retry with the same pair returns
  the existing row rather than inserting a duplicate.
- `source` cannot be a reserved address (`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`,
  `::`) — enforced at the Pydantic layer before any DB write.
- `timestamp` cannot be in the future.
- `tags` are always stored lowercase.

**DDD role:** Core aggregate of the ingestion context. The LangGraph enrichment agent
operates on observations, reading `raw_data` and writing `classification` results back
via `processed` / `processed_at`.

---

## Identity & Access

### Entities: `User`, `UserTenant`, `ApiKey`

### User

The authentication principal. Carries coarse role-based access control.

| Field                | Meaning                                                    |
| -------------------- | ---------------------------------------------------------- |
| `username` / `email` | Identity fields; both are unique                           |
| `password_hash`      | bcrypt hash; plaintext is never stored                     |
| `role`               | `viewer`, `writer`, `operator`, `tenant_admin`, or `admin` |
| `is_active`          | Soft-disable without deletion                              |
| `tenant_id`          | Default tenant scope for this user                         |

#### Roles

- `viewer` — read-only access to observations and scorecards
- `writer` — can create/update observations and submit contract snapshots
- `operator` — writer permissions plus scheduling controls
- `tenant_admin` — can manage users and API keys within their tenant
- `admin` — full access across all tenants

### UserTenant

Junction table for many-to-many user-to-tenant mapping. Enables a `tenant_admin` to
switch active tenant context without changing their `User` row.

| Field       | Meaning                            |
| ----------- | ---------------------------------- |
| `user_id`   | FK to `User`                       |
| `tenant_id` | The tenant this user has access to |

### ApiKey

A tenant-scoped, scope-limited alternative to JWT authentication. Intended for
machine-to-machine access (CI pipelines, scripts, integrations).

| Field          | Meaning                                                                             |
| -------------- | ----------------------------------------------------------------------------------- |
| `key_prefix`   | First 8 hex chars of the raw key — safe to log, used for O(1) DB lookup             |
| `key_hash`     | SHA-256 of the full raw key — used for constant-time verification                   |
| `scopes`       | JSON list of fine-grained permissions, e.g. `["observations:read", "sources:read"]` |
| `expires_at`   | Optional hard expiry; `null` = no expiry                                            |
| `last_used_at` | Updated on every authenticated request — usable for dormant-key cleanup             |

**Invariant:** The full raw key is returned exactly once at creation time and never stored.
Only the hash is persisted. This is the industry-standard "show once" pattern.

**Available scopes:** `observations:read`, `observations:write`, `sources:read`,
`sources:write`, `scorecards:read`, `contracts:read`, `contracts:write`.

---

## Security & Abuse

### Entities: `SecurityAuditEvent`, `AbuseSignal`

These two entities serve different purposes despite both being "security-related".

### SecurityAuditEvent

Append-only, hash-chained audit log. Every security-relevant decision (authentication
success/failure, authorization grant/deny, admin action) produces one row.

| Field                            | Meaning                                                                      |
| -------------------------------- | ---------------------------------------------------------------------------- |
| `event_type`                     | Category of the event: `auth.login`, `authz.denied`, `api_key.created`, etc. |
| `action`                         | The specific action attempted                                                |
| `decision`                       | `allow` or `deny`                                                            |
| `actor_type` / `actor_id`        | Who performed the action: `user:42`, `api_key:abc1234`, `system`             |
| `resource_type` / `resource_id`  | What was acted upon: `observation:99`, `source:3`                            |
| `correlation_id`                 | Links the audit event to the HTTP request that triggered it                  |
| `prev_event_hash` / `event_hash` | SHA-256 hash chain — lets verifiers detect gaps or row mutation              |

**DDD role:** Immutable domain event log. Rows have no `updated_at` and no soft-delete —
by convention the application layer never issues UPDATE or DELETE against this table.
The hash chain makes tampering detectable.

### AbuseSignal

Mutable operational finding raised by the abuse detection system (or manually by an
operator) when a pattern of suspicious behaviour is detected.

| Field                         | Meaning                                                                                                              |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `signal_type`                 | What kind of abuse: `noisy_source`, `suspicious_key`, `burst_abuse`, `credential_stuffing`, `ip_rotation`            |
| `actor_type` / `actor_id`     | The offending entity: API key prefix, source name, IP address, or tenant ID                                          |
| `severity`                    | `low`, `medium`, `high`, or `critical`                                                                               |
| `detection_rule`              | The rule that fired: `quota_exceeded`, `auth_failure_spike`, `multi_ip_key`, `error_rate_spike`, `rapid_enumeration` |
| `evidence`                    | Machine-readable evidence bag (counts, thresholds, time window)                                                      |
| `action_taken`                | What the system did: `logged`, `rate_limited`, `blocked`, or `alerted`                                               |
| `resolved_at` / `resolved_by` | Set when an operator closes the signal                                                                               |

**DDD role:** Mutable operational entity with a defined lifecycle: `open → resolved`.
Unlike `SecurityAuditEvent` it can be annotated and closed. It is the domain's answer
to "is there an active abuse problem right now, and has it been dealt with?"

---

## Messaging Infrastructure

These entities implement reliability patterns for Kafka-based messaging. They are
cross-cutting and not owned by any single domain context.

### ProcessedEvent

Tracks every Kafka message consumed by the service. Enables idempotent processing
(a message received twice produces only one side-effect), DLQ routing (poison pills are
forwarded to a dead-letter topic after a retry limit), and replay (Kafka offset is stored
for recovery after crash).

| Field                                              | Meaning                                                                    |
| -------------------------------------------------- | -------------------------------------------------------------------------- |
| `idempotency_key`                                  | Unique per event; a second arrival with the same key is silently skipped   |
| `kafka_topic` / `kafka_partition` / `kafka_offset` | Kafka coordinates for replay                                               |
| `event_type`                                       | What happened: `observation.created`, `drift.detected`, etc.               |
| `status`                                           | State machine: `pending → processing → completed \| failed \| dead_letter` |
| `processing_attempts`                              | Retry counter; triggers DLQ routing when limit is reached                  |
| `dead_letter_queue`                                | True when the message was forwarded to the DLQ after exhausting retries    |

### OutboxEvent

Implements the transactional outbox pattern. Instead of publishing to Kafka inside an
application transaction (which can produce a message even if the transaction rolls back),
the service writes an `OutboxEvent` row within the same transaction as the domain change.
A background relay process reads unpublished outbox rows and publishes them to Kafka,
then marks them `published_at`.

| Field                             | Meaning                                                              |
| --------------------------------- | -------------------------------------------------------------------- |
| `aggregate_type` / `aggregate_id` | The domain object that changed: `Observation`, `SourceProfile`, etc. |
| `event_type`                      | What change occurred                                                 |
| `payload`                         | The event data to publish                                            |
| `idempotency_key`                 | Prevents duplicate publications if the relay runs twice              |
| `published_at`                    | `null` = not yet published; non-null = relay has sent it             |
| `publish_attempts` / `last_error` | Retry tracking for the relay                                         |

### InboxConsumption

Implements the transactional inbox pattern — the consumer side of `OutboxEvent`. Records
that a specific consumer has already processed a given `message_id`, preventing
double-processing when a message is delivered more than once by the broker.

| Field           | Meaning                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| `consumer_name` | Which consumer group / handler processed this message                   |
| `message_id`    | The message's unique identifier (maps to `OutboxEvent.idempotency_key`) |
| `event_type`    | The event type that was processed                                       |

**`(consumer_name, message_id)`** is a unique constraint — the deduplication key.

---

## Cross-Cutting Concerns

### TimestampMixin

Applied to all mutable entities. Provides:

- `created_at` — set once on INSERT, never changes
- `updated_at` — refreshed on every UPDATE
- `deleted_at` — `null` until soft-deleted; all active-record queries filter
  `WHERE deleted_at IS NULL`

Soft-delete is used throughout (never hard-delete active domain data) so audit trails
remain intact and accidental deletes can be recovered within the 90-day grace period
before the cleanup job permanently removes rows.

### `tenant_id`

Present on `Observation`, `ProviderHealthSample`, `ApiKey`, `AbuseSignal`,
`OutboxEvent`, and `User`. This is the row-level tenancy discriminator for multi-tenant
deployments. A `viewer` user with `tenant_id = 3` can only read rows where
`tenant_id = 3`. Enforced in the repository layer and, in production, by PostgreSQL
Row-Level Security policies.

---

## Entity Relationship Summary

```text
SourceProfile ──< ProviderHealthSample    (one source, many probe results)
SourceProfile ──< ContractSnapshot        (one source, many schema snapshots)
ContractSnapshot ──< DriftEvent           (consecutive snapshot pair → one drift event)

User >──< UserTenant                      (many-to-many: user can belong to many tenants)
User ──< ApiKey                           (one user owns many API keys)

Observation (standalone)                  (no FK to SourceProfile by design —
                                           source is a string identifier, not a FK,
                                           to allow ingestion before a SourceProfile exists)

ProcessedEvent  (Kafka consumer log)
OutboxEvent     (Kafka producer outbox)
InboxConsumption (Kafka consumer inbox)
SecurityAuditEvent (append-only audit log)
AbuseSignal     (mutable abuse findings)
```

---

## Related Documents

- [`services/ingestor/models.py`](../../services/ingestor/models.py) — ORM definitions
- [`services/ingestor/api_schemas/`](../../services/ingestor/api_schemas/) — Pydantic request/response schemas
- Architecture Overview (02-architecture) — service boundaries and request flows
- Contract Drift (05-development) — contract drift HTTP API
- Scorecards (09-user-guides) — scorecard aggregation and SLO burn rate
- Security Architecture (02-architecture) — auth layers and RBAC
