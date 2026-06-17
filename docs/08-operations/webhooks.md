# Webhooks

Track: C — Architecture and Platform Strategy

---

## Integration Guide

The webhook gateway runs on port 8004. External sources send events to `POST /api/v1/webhooks/{source}`.

### Flow

```text
External source → POST /api/v1/webhooks/{source}
  → Signature validation (HMAC-SHA256)
  → Idempotency check (delivery_id)
  → Audit log (webhook_events table, regardless of outcome)
  → Publish to Kafka topic webhook.events.{source}
```

### Quick Start

1. Register a webhook source via admin API.
2. Set `WEBHOOK_SIGNING_KEY_{SOURCE_UPPER}` environment variable.
3. Send webhook with headers: `X-Delivery-Id`, `X-Webhook-Signature`, `Content-Type`.

### Response Codes

| Code | Meaning |
|------|---------|
| 202 | Accepted |
| 400 | Bad request |
| 401 | Signature mismatch |
| 409 | Duplicate delivery ID |
| 413 | Payload too large (>10 MB) |
| 503 | Source not registered |

### Signature Support

- Plain hex format
- Stripe-compatible signature format (v1, v2)

### Signing Key Resolution

1. In-memory cache (5-min TTL)
2. Environment variable
3. AWS Secrets Manager
4. Fallback default

---

## Debugging

### Audit Log

Every inbound attempt is stored in `webhook_events` table regardless of outcome:

```sql
-- Recent events
SELECT * FROM webhook_events ORDER BY created_at DESC LIMIT 20;

-- Only failures
SELECT * FROM webhook_events WHERE status = 'failed' ORDER BY created_at DESC;

-- Duplicate delivery IDs
SELECT delivery_id, COUNT(*) FROM webhook_events GROUP BY delivery_id HAVING COUNT(*) > 1;
```

### Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 Signature mismatch | Wrong key, re-serialization difference, algorithm mismatch | Manually verify HMAC: `echo -n "<payload>" | openssl dgst -sha256 -hmac "<key>"` |
| 409 Duplicate | Idempotency guard working correctly | If first delivery failed, use replay |
| 413 Payload too large | Exceeds 10 MB limit | Reduce payload size |
| No matching source | Source not registered in admin API | Register source first |

### Key Rotation

No dual-key validation period — brief maintenance window. Update `WEBHOOK_SIGNING_KEY_{SOURCE}` env var and restart the service.

### Log Correlation

Use the `delivery_id` to correlate events across logs:

```bash
grep "<delivery-id>" /var/log/webhook/*.log
```
