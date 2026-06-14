# Chaos Testing

How to run resilience scenarios, interpret results, and validate system recovery.

---

## Overview

The chaos suite lives in `infra/scripts/chaos.sh`. It injects five failure scenarios plus a full gauntlet mode. Each scenario runs for `CHAOS_DURATION` seconds (default: 30) then stops the fault and waits for recovery.

| Scenario | What it does |
| -------- | ------------ |
| `kill` | Stops and restarts the ingestor container |
| `network` | Adds 200 ms latency + 10 % packet loss on ingestor network |
| `db` | Pauses the PostgreSQL container |
| `kafka` | Pauses the Redpanda container |
| `memory` | Runs a memory stress process inside the ingestor container |
| `gauntlet` | Runs all five scenarios sequentially |

---

## Run locally

```bash
# Prerequisites: Docker Compose stack running (just up)
just up

# Run a single scenario
CHAOS_DURATION=20 bash infra/scripts/chaos.sh kill

# Run the full gauntlet
CHAOS_DURATION=30 bash infra/scripts/chaos.sh gauntlet
```

---

## Run via GitHub Actions

1. Go to **Actions** → **Chaos Testing** workflow.
2. Click **Run workflow**.
3. Select a scenario from the dropdown (default: `gauntlet`).
4. Click **Run workflow**.

The workflow runs four jobs: `setup`, `chaos`, `verify`, `report`. Artifacts (chaos output + compose logs) are retained for 14 days.

---

## Interpret results

### Healthy recovery

```text
[10:00:00] Injecting 'db' fault for 20s…
[10:00:20] Fault stopped. Waiting for recovery…
[10:00:35] ✅ /healthz responded 200 — recovery confirmed (15s)
```

### Failed recovery

```text
[10:00:00] Injecting 'kill' fault for 20s…
[10:00:20] Fault stopped. Waiting for recovery…
[10:01:20] ❌ /healthz still failing after 60s
```

Check compose logs:

```bash
docker compose logs ingestor --since 5m
```

---

## Validate recovery programmatically

```bash
# Health check
curl -sf http://127.0.0.1:8000/healthz | python3 -c "import sys,json; d=json.load(sys.stdin); print('healthy' if d.get('status')=='ok' else 'UNHEALTHY')"

# Circuit breaker state (should be 0 = CLOSED after recovery)
curl -sf 'http://127.0.0.1:9090/api/v1/query' \
  --data-urlencode 'query=circuit_breaker_state{job="ingestor"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['data']['result']; print('state:', r[0]['value'][1] if r else 'no_data')"
```

---

## Adding a new scenario

1. Add a function `scenario_<name>()` in `infra/scripts/chaos.sh`.
2. Add the name to the `case` block at the bottom of the script.
3. Add it to the `options` list in `.github/workflows/chaos.yml` (`inputs.scenario`).
4. Document it in the table above.

---

## Recovery time objectives

| Scenario | Expected MTTR | Alert threshold |
| -------- | ------------- | --------------- |
| `kill` | < 10 s | > 30 s |
| `db` | < 45 s | > 90 s |
| `kafka` | < 20 s | > 60 s |
| `network` | 0 s (degraded but running) | error rate > 5 % |
| `memory` | < 60 s | OOMKill restarting repeatedly |

If recovery time exceeds the alert threshold, open a follow-up ticket to tune restart policy, health check timing, or circuit breaker configuration.
