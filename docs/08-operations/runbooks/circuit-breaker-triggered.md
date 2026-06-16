# Circuit Breaker Triggered

**Trigger**: Alertmanager fires `CircuitBreakerOpen` alert, or `circuit_breaker_state{job="ingestor"} > 0` in Prometheus.

**Severity**: High — ingestor is partially or fully rejecting traffic.

---

## 1. Identify the open breaker

```bash
# Query Prometheus directly
curl -sf 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=circuit_breaker_state{job="ingestor"}' \
  | python3 -c "import sys,json; [print(r['metric']['name'], '→ state', r['value'][1]) for r in json.load(sys.stdin)['data']['result']]"
```

State values: `0` = CLOSED (healthy), `1` = HALF-OPEN (probing), `2` = OPEN (rejecting).

Check Grafana → **Ingestor Service** dashboard → **Circuit Breaker State** gauge.

---

## 2. Find the cause

```bash
# Tail ingestor logs for the last 5 minutes
docker compose logs ingestor --since 5m | grep -i "circuit\|breaker\|error\|exception"
```

Common causes:

| Breaker | Typical trigger |
| ------- | --------------- |
| `db_write` | PostgreSQL unavailable or connection pool exhausted |
| `kafka_publish` | Redpanda broker down or partition leader election |
| `inference_call` | Inference service pod restarting or overloaded |
| `http_external` | Downstream API rate-limited or unreachable |

---

## 3. Resolve the downstream issue

### PostgreSQL

```bash
# Check DB health
docker compose exec db pg_isready -U postgres
# Check active connections
docker compose exec db psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
# Restart DB if unresponsive (last resort)
docker compose restart db
```

### Redpanda

```bash
docker compose exec broker rpk cluster health
docker compose restart broker   # only if health check fails repeatedly
```

### Inference service

```bash
docker compose logs inference --tail=50
docker compose restart inference
```

---

## 4. Wait for automatic recovery

The circuit breaker transitions OPEN → HALF-OPEN → CLOSED automatically once the downstream recovers.
Default probe interval: 30 s. Monitor:

```bash
watch -n 5 'curl -sf http://127.0.0.1:8000/readyz | python3 -c "import sys,json; d=json.load(sys.stdin); print(d)"'
```

---

## 5. Force reset (emergency only)

Only if automatic recovery is stuck and downstream is confirmed healthy:

```bash
curl -X POST http://127.0.0.1:8000/admin/circuit-breakers/reset \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

---

## 6. Verify

- Grafana → **Ingestor Service** → **Circuit Breaker State** shows green (CLOSED = 0).
- Error rate drops back below 1 %.
- No new `CircuitBreakerOpen` alerts within 10 minutes.

---

## 7. Post-incident

- Record MTTR (open time → closed time).
- If the breaker opened due to transient load spike: review thresholds in `services/ingestor/core/circuit_breaker.py`.
- If it opened due to infrastructure failure: add a health check or dependency wait to the failing service.
