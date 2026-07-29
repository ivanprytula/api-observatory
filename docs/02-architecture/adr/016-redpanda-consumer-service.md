# ADR 016: Reliable Incident Notification Consumer

## Status

Implemented locally on 2026-07-29: the transactional producer, outbox publisher, standalone
consumer process, database-owned retry state, and sanitized terminal DLQ outbox are present. This
is not a deployed-production claim; local Redpanda end-to-end verification remains a required
proof. The internal operations server is deferred.

## Context

The ingestor can publish `observation.created` and `doc.scraped` events to the optional
Redpanda broker when `API_OBS_BROKER_ENABLED=true`. The application has no production consumer: the
dashboard receives live updates through the ingestor's Redis Pub/Sub/WebSocket path, and the Kafka
partition/consumer-group code is an isolated learning lab.

Incident notifications currently run after the incident transaction commits. A process exit can
lose the notification, failures have no durable retry state, and `last_notification_at` records an
attempt rather than successful channel delivery. The subscription delivery-log endpoint infers a
result from drift severity; it does not read actual provider outcomes.

This is a concrete asynchronous workload: preserve incident creation latency while making channel
delivery, failure, retry, quarantine, and replay observable.

## Decision

Add an opt-in reliable notification-delivery flow with these boundaries:

1. An incident transition with `should_notify=true` writes a
   `notification.delivery_requested.v1` outbox event in the same database transaction as the
   incident change. The outbox repository must support flush-without-commit so it does not own the
   caller's transaction.
2. A bounded publisher claims pending outbox rows and publishes them to
   `notifications.delivery.requests.v1`. The shared versioned event contains a stable `message_id`,
   `incident_id`, tenant and source identifiers, severity, safe message context, and requested
   channels. It contains no credentials or destination secrets.
3. Consumer group `notification-delivery-v1` validates the event and claims the existing inbox
   identity `(consumer_name, message_id)` before dispatch. The inbox lifecycle will be extended
   rather than adding a second generic consumed-event abstraction.
4. Each channel outcome is stored as real delivery data. Subscription delivery logs will read
   these records instead of manufacturing a `delivered` status from drift severity.
5. The source Kafka offset is committed only after delivery reaches a durable completed,
   retry-scheduled, or dead-letter state. A malformed or unsupported event stops the worker without
   committing its offset for explicit operator investigation; it is never silently discarded.
6. Dead-letter records retain the message identity, safe payload metadata, attempt count, and
   bounded error detail. Replay is explicit, audited, and idempotent.
7. Metrics cover consumer lag, received/completed/failed/dead-letter totals, attempts, and delivery
   latency. Logs carry `message_id`, `incident_id`, channel, and attempt but no secrets or complete
   provider payloads.

The broker path and direct path are mutually exclusive. Direct delivery remains the default until
the consumer path passes its local end-to-end gate.

## Delivery Guarantee Boundary

Kafka-to-database processing is idempotent through the stable message identity and inbox claim.
External notification providers do not all offer idempotent sends, so the project must not claim
exactly-once user-visible delivery.

Delivery is at least once with at most three total channel attempts: the initial attempt, then
database-scheduled retries after approximately 30 seconds and five minutes with jitter. Connection
failures, timeouts, HTTP `429`, and HTTP `5xx` are retryable. Invalid configuration, malformed
events, unsupported channels, and permanent HTTP `4xx` responses move directly to dead-letter
state.

The inbox owns the message claim lease and aggregate states `processing`, `completed`,
`completed_with_dead_letters`, or `dead_letter`. Per-channel delivery rows own attempt count,
bounded error detail, `next_attempt_at`, and states `pending`, `processing`, `retry_scheduled`,
`delivered`, or `dead_letter`. The worker claims due channel retries with bounded
`FOR UPDATE SKIP LOCKED` batches, so it does not sleep a Kafka partition during backoff. A stable
idempotency key is sent when a provider supports it; duplicate external notifications remain a
documented possibility when a provider accepted a request but its response was lost.

Database state is the single source of retry truth. Kafka retry topics must not run concurrently
for the same delivery because two independent schedulers would create ambiguous ownership and
duplicate risk.

## Dead-Letter Transport

PostgreSQL is authoritative for terminal delivery state and audited replay. In the same transaction
that marks a channel delivery `dead_letter`, insert a uniquely keyed
`notification.delivery_dead_lettered.v1` outbox event. The outbox publisher sends it to
`notifications.delivery.dlq.v1` independently of the source notification request.

The DLQ event contains only `delivery_id`, `message_id`, incident/source/tenant identifiers,
channel name, attempt count, bounded error category and code, and first/last attempt timestamps. It
must not contain provider credentials, destination addresses, authorization headers, provider
response bodies, or the original notification payload.

If Redpanda is unavailable, the database dead-letter transition still commits and the DLQ outbox
row remains pending. The source request offset can then commit because both terminal state and the
intent to publish the sanitized DLQ event are durable. The DLQ topic is an operational signal, not
an automatic retry input; replay remains an explicit database operation with actor and reason.

## Deployment Boundary

Run the consumer as a separate process using the existing ingestor code and image. A Compose
`notification-consumer` service overrides the image command with the consumer module, has no
host-published port, and owns its health signal, restart policy, resource bounds, and consumer-group
metrics independently from the ingestor API.

The root `Dockerfile` already copies the required ingestor and shared-contract source, but currently
installs only the `ai` and `tracing` extras. The implementation must add `--extra messaging` to that
existing image build so `aiokafka` is present. This is a shared-image dependency correction, not a
new image or dependency manifest.

The service is enabled only through the opt-in local broker profile. It shares the ingestor database
and broker configuration but does not start the ingestor API, scheduler, producer lifespan, cache
Pub/Sub bridge, or agent runtime. It starts only the consumer process.

Local Compose remains canonical and opt-in. AWS Stage 0 remains unchanged because its deployment
contract does not currently require a broker.

## Deferred Worker Health Interface

An internal FastAPI/Uvicorn operations server on port `8002` is deferred. It would expose only:

- `GET /health` for process/event-loop liveness.
- `GET /readyz` for consumer and retry-loop readiness.
- `GET /metrics` for Prometheus scraping inside the Compose network.

Readiness requires the consumer task to be alive, a successful broker subscription/assignment, a
recent bounded poll heartbeat, a successful database probe, and a recent database retry-loop
heartbeat. An empty topic remains ready because successful bounded polls refresh the heartbeat.
Missing topics, a stalled poll, database failure, or a completed/failed worker task returns `503`.

Run the consumer, retry loop, and failure monitor under structured concurrency. An unexpected
consumer or retry-loop exit must terminate the process with a non-zero status so Docker restart
policy can act; readiness must not remain stale `true` after a background task dies.

The endpoints expose state labels, counters, timestamps, and a safe version identifier only. They
must not expose message payloads, notification destinations, credentials, provider responses, or
database/broker connection strings.

## Rollback

Stop the consumer and outbox publisher, switch notification delivery mode back to `direct`, and
retain pending outbox/inbox/delivery rows for inspection. Rollback does not delete broker messages
or delivery history. Re-enabling broker delivery resumes from committed offsets and inbox state.

## Required Proof Before Acceptance

- Producer: [`services/ingestor/events.py`](../../../services/ingestor/events.py)
- Shared event names: [`libs/contracts/events.py`](../../../libs/contracts/events.py)
- Event persistence/idempotency seam:
  [`services/ingestor/repositories/messaging.py`](../../../services/ingestor/repositories/messaging.py)
- Consumer-group learning lab: [`labs/partitioning_sharding/`](../../../labs/partitioning_sharding/)
- Focused unit proof for event validation, retry classification, inbox deduplication, and channel
  result persistence.
- PostgreSQL integration proof for transactional outbox creation and concurrent inbox claims.
- Local Redpanda proof for delivery, duplicate replay, retry exhaustion, DLQ, restart recovery, and
  consumer lag metrics.
- DLQ proof that terminal state and its uniquely keyed outbox event commit together, duplicate
  publication is harmless, and serialized events contain none of the prohibited fields.
- Image proof that imports `aiokafka` and starts the consumer command without importing the FastAPI
  application lifespan.
- Rendered Compose proof that the consumer uses the ingestor image, has no host port, and remains
  absent unless the messaging profile is selected.
- Operations-interface proof is deferred with the operations server: liveness, readiness
  dependencies, stale heartbeats, safe response fields, and Prometheus metrics.
