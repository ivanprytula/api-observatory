# WebSocket Real-Time Stream

Receive live events from the ingestor — observation ingestions, job progress updates,
and contract drift notifications — over a persistent WebSocket connection.

## Endpoint

```text
WS /ws/observations/stream
```

Authentication token is passed as a query parameter because browsers cannot set
custom `Authorization` headers on WebSocket connections.

## Authentication

If `api_v1_bearer_token` is configured in the environment the connection requires
a token.

```text
WS /ws/observations/stream?token=<bearer_token>
```

### Close codes

| Code | Reason |
|------|--------|
| `4001` | Token missing (`?token=` not supplied) |
| `4003` | Token invalid (does not match configured bearer) |

If no bearer token is configured on the server, any connection is accepted
without a `?token=` parameter.

## Message types

All messages are JSON objects with a `type` field and an `ts` ISO timestamp.

### `observation.created`

Emitted when a new pipeline observation is ingested.

```json
{
  "type": "observation.created",
  "observation_id": 42,
  "source": "api.example.com",
  "ts": "2026-01-01T12:00:00.000000"
}
```

### `job.progress`

Emitted during long-running background jobs.

```json
{
  "type": "job.progress",
  "job_id": "ingest-batch-7",
  "status": "running",
  "progress": 0.65,
  "message": "processed 650 / 1000 observations",
  "ts": "2026-01-01T12:00:01.000000"
}
```

### `drift.detected`

Emitted immediately after a breaking or non-breaking contract drift event is
persisted.  See Contract Drift guide for full field semantics.

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

### `ping`

Sent by the server every 30 seconds as a keepalive.

```json
{ "type": "ping", "ts": "2026-01-01T12:00:30.000000" }
```

### `info`

Sent when the stream is unavailable (Cache not enabled).

```json
{ "type": "info", "message": "stream unavailable" }
```

The connection is then closed by the server.

## Connecting

### wscat (CLI)

```bash
# Install once
npm install -g wscat

# Connect (no auth)
wscat -c "ws://127.0.0.1:8000/ws/observations/stream"

# Connect (with token)
wscat -c "ws://127.0.0.1:8000/ws/observations/stream?token=mysecret"
```

### Browser (JavaScript)

```javascript
const wsUrl = new URL('/ws/observations/stream', window.location.origin);
wsUrl.searchParams.set('token', 'mysecret');
const ws = new WebSocket(wsUrl.toString());

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'drift.detected') {
    console.warn('Contract drift!', msg);
  }
};

ws.onclose = (event) => {
  console.log('Closed', event.code, event.reason);
};
```

### Python (websockets)

```python
import asyncio, json, subprocess, websockets

async def listen() -> None:
    base_url = "ws://127.0.0.1:8000/ws/observations/stream?token=mysecret"
    async with websockets.connect(base_url) as ws:
        async for raw in ws:
            msg = json.loads(raw)
            print(msg)

asyncio.run(listen())
```

## Cache dependency

The WebSocket stream requires Cache to be enabled (`CACHE_ENABLED=true` and a
valid `CACHE_URL`).  When Cache is unavailable the server sends a single `info`
message and closes the connection.  All other endpoints remain unaffected.

## Internal architecture

```text
POST /api/v1/...          ─→  repository layer
                                │
                                ├─ persist to PostgreSQL
                                └─ pubsub.publish_*()  ─→  Cache channel: ingestor:events
                                                                 │
WS /ws/observations/stream   ←─  subscribe_events()  ←──────────────┘
```

`subscribe_events()` opens a dedicated Cache connection per WebSocket session
and yields decoded dicts.  Two concurrent asyncio tasks run per session:

- `_reader` — reads from Cache and forwards messages to the WebSocket
- `_pinger` — sends a keepalive `ping` every 30 seconds

Both tasks are cancelled when the client disconnects.

### Pub/sub fail-open

`publish_event()` and all `publish_*` wrappers are fail-open: if the Cache
client is not connected (or errors mid-publish) the event is dropped silently
with a debug log.  The write path is never blocked.
