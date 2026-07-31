# Gateway and Load-Balancing Lab

**Status: Lab.** This standalone Compose project runs three stateless Python replicas behind nginx.
It is isolated from default Compose and is not production evidence.

## Run

```bash
docker compose -f labs/gateway_load_balancing/compose.yaml up -d
uv run python labs/gateway_load_balancing/verify_distribution.py
```

The verifier should report more than one replica. Then exercise passive health removal and recovery:

```bash
docker compose -f labs/gateway_load_balancing/compose.yaml stop replica-b
uv run python labs/gateway_load_balancing/verify_distribution.py
docker compose -f labs/gateway_load_balancing/compose.yaml start replica-b
uv run python labs/gateway_load_balancing/verify_distribution.py
docker compose -f labs/gateway_load_balancing/compose.yaml down
```

Inspect edge logs while stopping a replica. nginx may attempt the failed upstream once, then retries a
healthy replica and passively excludes the failed one for `fail_timeout`. The server handles
`SIGTERM` with a graceful shutdown.

## What to Explain

- A reverse proxy performs routing and passive failure handling; it is not automatically a full API
  gateway with authentication, consumer quotas, transformations, or billing policy.
- Health-aware routing cannot repair local application state. API Observatory's in-process scheduler
  would run in every replica unless scheduling ownership is separated or coordinated.
- WebSockets, database pools, cache locality, readiness, and termination grace all affect safe
  horizontal scaling.

At 10x load, measure connection/pool saturation and scale stateless request handling. At 100x,
separate scheduler/workers, define zone failure behavior, and adopt managed/global ingress only when
availability and operational evidence justify it.
