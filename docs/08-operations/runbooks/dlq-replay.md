# DLQ Replay

**Trigger**: Kafka dead-letter topic (`*.dead-letter`) consumer lag rising or messages not being processed.

**Severity**: High — data loss risk if DLQ fills and messages expire.

---

## 1. Confirm the problem

```bash
# Check consumer lag across all topics (requires rpk in PATH or use the container)
docker compose exec broker rpk topic describe pipeline-events --summary
docker compose exec broker rpk group describe ingestor-consumer-group
```

Check Grafana → **Business Metrics** dashboard → **Kafka DLQ Consumer Lag** panel.

Expected normal state: lag = 0 or slowly draining.

---

## 2. Inspect DLQ messages

```bash
# Consume up to 20 messages from the DLQ without committing offsets
docker compose exec broker rpk topic consume pipeline-events.dead-letter \
  --num 20 \
  --offset start \
  --format json
```

Look for:

- `error` field in message metadata/headers
- Malformed payloads (schema mismatch, null required fields)
- Persistent downstream errors (DB unavailable, validation failures)

---

## 3. Diagnose root cause

| Symptom | Likely cause |
| ------- | ------------ |
| Schema parse error | Producer changed schema without consumer update |
| DB constraint violation | Stale reference data; run migration |
| Rate limit / 429 from downstream | Throttle replay speed |
| Ingestor pod restarting | Check circuit breaker runbook first |

---

## 4. Fix and replay

### Option A — Drain and discard (irrecoverable messages)

```bash
# Move consumer group offset past all DLQ messages
docker compose exec broker rpk group seek ingestor-consumer-group \
  --topic pipeline-events.dead-letter \
  --to end
```

### Option B — Replay to main topic after fix

```bash
# Mirror DLQ → main topic using rpk (throttled to 50 msg/s)
docker compose exec broker rpk topic produce pipeline-events \
  < <(docker compose exec broker rpk topic consume pipeline-events.dead-letter \
        --offset start --format json)
```

Or use the admin replay endpoint if implemented:

```bash
curl -X POST http://127.0.0.1:8000/admin/dlq/replay \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"topic": "pipeline-events.dead-letter", "batch_size": 100}'
```

---

## 5. Verify

```bash
# Lag should return to 0 within 1-2 minutes
docker compose exec broker rpk group describe ingestor-consumer-group
```

Check Grafana → **Business Metrics** → **Kafka DLQ Consumer Lag** is dropping.

---

## 6. Post-incident

- Document root cause in the incident log.
- If schema mismatch: update consumer schema registry / Pydantic model and deploy.
- If recurring: add dead-letter alerting rule in `infra/monitoring/rules/`.
