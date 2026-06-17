# Contract Drift

Track schema changes between API snapshots and receive real-time notifications
when a breaking change is detected.

## Overview

Contract drift detects when the payload schema of an API source changes between
ingestion runs.  Each ingest call submits a **contract snapshot**; the service
diffs the new schema against the previous one, assigns a compatibility score, and
emits a `drift.detected` event over Cache pub/sub if any field changed.

## Concepts

### ContractSnapshot

A point-in-time observation of a source's declared JSON schema.

| Field | Description |
|-------|-------------|
| `source_id` | Foreign key to `SourceProfile` |
| `payload_schema` | JSON object — the full schema at ingestion time |
| `schema_fingerprint` | SHA-256 of the canonical schema string |
| `compatibility_score` | 0–100 float; 100 means no change |
| `created_at` | Timestamp of the ingest call |

### DriftEvent

Created when two consecutive snapshots differ.

| Field | Description |
|-------|-------------|
| `source_id` | Which source drifted |
| `event_type` | `breaking`, `non_breaking`, or `none` |
| `severity` | `critical`, `high`, `medium`, `low`, or `none` |
| `compatibility_score` | Quantified impact (0–100) |
| `summary` | Human-readable diff summary |
| `detected_at` | When the drift was computed |

### Compatibility score

Computed from the share of **unchanged** fields in the new schema relative to the
previous one.  A value of 100 means the schemas are identical.  Breaking changes
(removed or type-changed required fields) push the score toward 0.

### Fingerprint short-circuit

If the incoming schema has the **same SHA-256 fingerprint** as the previous
snapshot, the service skips the diff entirely, observations a snapshot with
`compatibility_score = 100.0`, and returns `drift_event = None`.  No pub/sub
event is published.

## HTTP API

### Submit a snapshot

```http
POST /api/v1/contracts/snapshots
Content-Type: application/json
Authorization: Bearer <token>

{
  "source_id": 1,
  "payload_schema": {
    "type": "object",
    "properties": {
      "id":    { "type": "integer" },
      "email": { "type": "string" }
    },
    "required": ["id", "email"]
  }
}
```

**Response 201** — new snapshot created; `drift_event` is `null` when no change
was detected.

```json
{
  "snapshot": {
    "id": 42,
    "source_id": 1,
    "schema_fingerprint": "a3f1...",
    "compatibility_score": 100.0,
    "created_at": "2026-01-01T12:00:00Z"
  },
  "drift_event": null
}
```

**Response 201** with a drift event — returned when fields changed.

```json
{
  "snapshot": { "id": 43, "compatibility_score": 60.0, "..." : "..." },
  "drift_event": {
    "id": 7,
    "source_id": 1,
    "event_type": "breaking",
    "severity": "high",
    "compatibility_score": 60.0,
    "summary": "removed required field 'email'",
    "detected_at": "2026-01-01T12:05:00Z"
  }
}
```

### List drift events for a source

```http
GET /api/v1/contracts/sources/{source_id}/drift
Authorization: Bearer <token>
```

Returns a list of `DriftEvent` objects ordered by `detected_at` descending.

## WebSocket integration

Whenever a `DriftEvent` is created, the service publishes a `drift.detected`
message on the Cache channel `ingestor:events`.  Any connected WebSocket client
receives it in real time.  See WebSocket guide for how to connect.

Sample message:

```json
{
  "type": "drift.detected",
  "source_id": 1,
  "drift_event_id": 7,
  "event_type": "breaking",
  "severity": "high",
  "compatibility_score": 60.0,
  "ts": "2026-01-01T12:05:00.123456"
}
```

### Pub/sub is fail-open

If Cache is not connected, `publish_drift_event` logs a debug message and returns
without raising.  The snapshot and drift event are still persisted; only the
real-time notification is skipped.

## Developer notes

### Repository layer

`services/ingestor/repositories/contract_drift.py`

Key entry point:

```python
snapshot, drift_event = await create_contract_snapshot(db, payload)
```

The function:

1. Computes the schema fingerprint.
2. Short-circuits if unchanged (returns `drift_event=None`).
3. Fetches the previous snapshot and runs the field-level diff.
4. Persists `ContractSnapshot` and, if there is a drift, `DriftEvent`.
5. Calls `pubsub.publish_drift_event()` when `drift_event is not None`.

### Pure helper functions

The following helpers in `contract_drift.py` are side-effect free and unit
tested in `services/ingestor/tests/unit/test_contract_drift_helpers.py`:

- `_fingerprint(schema)` — SHA-256 of canonical JSON
- `_flatten_schema(schema)` — flattens nested properties to dot-paths
- `_diff_contract(old, new)` — computes added/removed/changed/unchanged fields
- `_event_type(diff)` — `breaking` / `non_breaking` / `none`
- `_compatibility_score(diff)` — 0–100 float
- `_severity(event_type, score)` — severity label
- `_summary(diff)` — human-readable string
