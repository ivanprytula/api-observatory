# SLO Breach Response

**Trigger**: Alertmanager fires `HighErrorRate` (5xx > 1 %) or `HighLatency` (P95 > 500 ms).

**Severity**: Critical — user-facing impact confirmed.

---

## 1. Confirm the breach

```bash
# Error rate over last 5 minutes
curl -sf 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=sum(rate(http_requests_total{job="ingestor",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="ingestor"}[5m]))' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Error rate:', d['data']['result'][0]['value'][1])"

# P95 latency
curl -sf 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="ingestor"}[5m])) by (le))' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('P95 latency:', d['data']['result'][0]['value'][1], 's')"
```

Check Grafana → **SLO Dashboard** → Golden Signals row.

---

## 2. Identify the failing endpoint

```bash
# Error rate per handler
curl -sf 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=sum(rate(http_requests_total{job="ingestor",status=~"5.."}[5m])) by (handler)' \
  | python3 -c "import sys,json; [print(r['metric']['handler'], r['value'][1]) for r in json.load(sys.stdin)['data']['result']]"
```

---

## 3. Root cause decision tree

```text
High error rate (5xx)
├── DB errors?
│   ├── YES → check circuit breaker (see circuit-breaker-triggered.md)
│   └── NO  → check application logs for exceptions
├── Validation errors only (422)?
│   └── Bad client request — not an SLO breach; suppress alert
└── 500 from unknown path?
    └── Check GlitchTip http://127.0.0.1:8010 for grouped exceptions

High latency (P95 > 500ms)
├── DB query slow?
│   └── EXPLAIN ANALYZE the slow query (check pg_stat_statements)
├── External call slow?
│   └── Check Jaeger traces http://127.0.0.1:16686
├── CPU saturation?
│   └── Check Grafana → Infrastructure → Container CPU
└── Kafka backpressure?
    └── Check DLQ lag (see dlq-replay.md)
```

---

## 4. Trace a slow request

```bash
# Jaeger UI — search for traces > 500ms on the ingestor service
open http://127.0.0.1:16686/search?service=ingestor&minDuration=500ms
```

Or query the API directly:

```bash
curl "http://127.0.0.1:16686/api/traces?service=ingestor&minDuration=500ms&limit=10"
```

---

## 5. Check error details in GlitchTip

1. Open `http://127.0.0.1:8010`
2. Navigate to **Issues** → sort by **Last seen**
3. Click the top issue → review stack trace, breadcrumbs, and tags
4. Note: `SENTRY_ENABLED=true` must be set for errors to appear

---

## 6. Immediate mitigations

| Scenario | Mitigation |
| -------- | ---------- |
| Single bad deployment | `git revert <commit>` + re-deploy |
| DB connection exhaustion | Increase pool size or restart ingestor |
| Slow external dependency | Enable circuit breaker for that call |
| Memory pressure | Scale ingestor replicas or increase memory limit |

---

## 7. Verify resolution

```bash
# SLO should recover within 1 evaluation window (5 min)
watch -n 30 'curl -sf "http://127.0.0.1:9090/api/v1/query?query=sum(rate(http_requests_total{job=\"ingestor\",status=~\"5..\"}[5m]))/sum(rate(http_requests_total{job=\"ingestor\"}[5m]))"'
```

---

## 8. Post-incident

- Write a 5-line incident summary: what broke, when, why, fix, prevention.
- Open a follow-up ticket if the root cause needs a permanent fix.
- Update alert thresholds if they were too sensitive.
