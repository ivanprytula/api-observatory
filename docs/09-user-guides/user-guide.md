# User Guide

Monitor, analyze, and maintain reliable API integrations with real-time visibility into performance, contract changes, and automated insights.

> **Evidence note:** sections marked `[Core]` are implemented and tested. Provider-backed
> behavior remains opt-in and must not be presented as exercised unless its proof was captured.

---

## What is API Observatory? [Core]

API Observatory continuously checks the health and reliability of your external API dependencies:

- **Is my API still working?** Real-time uptime tracking with configurable health probes
- **How fast is my API?** Latency metrics with 95th-percentile analysis
- **Has the API contract changed?** Automatic detection of breaking schema changes
- **What's the impact?** Error-budget burn rate to prioritize reliability issues

---

## Quick Start [Core]

Follow the [Canonical Onboarding and Delivery Checklist](../05-development/onboarding-and-delivery-checklist.md) for setup, then open `http://127.0.0.1:8501`. Protected actions such as source management require the authenticated local demo state; run `just db-auto-init` when following the populated walkthrough. MCP is separate from the Compose stack: after its one-time service-account setup, run `uv run python -m services.mcp.main` as a local stdio process.

### Monitor Your First API

1. Open the dashboard at `http://127.0.0.1:8501`.
2. Use the source-management panel to add an API source.
3. Wait for probe cycles (or trigger manually via **Probe all**).
4. View metrics in **Source Health** and events in **Live Stream**.

---

## Source Registration [Core]

Register any HTTP API you depend on for monitoring:

```json
{
  "name": "payment-service",
  "base_url": "https://api.payments.com",
  "health_check_path": "/status",
  "probe_interval_seconds": 60
}
```

Each source is probed at your configured interval to collect health samples.

---

## Reliability Scorecards [Core]

Get rolling-window reliability metrics for any API:

| Metric | Meaning |
|--------|---------|
| Uptime % | Percentage of successful probes |
| p50/p95 Latency | Median and 95th-percentile response time |
| Error Budget Burn Rate | How fast you're consuming your SLO budget |

The rolling-window endpoint is `GET /api/v1/scorecards/{source_id}?days=7`.

Full API details live in the [OpenAPI UI](http://127.0.0.1:8000/docs) and
[`services/ingestor/routers/scorecards.py`](../../services/ingestor/routers/scorecards.py).
Scorecards use a single PostgreSQL `PERCENTILE_CONT` query — no materialization.

---

## Contract Drift Detection [Core]

When APIs change their response structure, the system detects and classifies the impact:

- **Critical**: Breaking changes requiring immediate attention
- **High**: Significant changes that may affect integrations
- **Medium/Low**: Minor changes or additions
- **Compatibility Score**: Quantitative measure of drift severity (0-100)

Drift events stream to your dashboard in real-time via WebSocket.

Full API details live in the [OpenAPI UI](http://127.0.0.1:8000/docs) and
[`services/ingestor/routers/contract_drift.py`](../../services/ingestor/routers/contract_drift.py).

---

## Live Stream (WebSocket) [Core]

Real-time event stream at `WS /ws/observations/stream?token=<bearer_token>`.

Message types, connection behavior, and close codes are implemented by the dashboard client under
[`services/dashboard/`](../../services/dashboard/) and verified by the ingestor WebSocket tests;
see the [OpenAPI UI](http://127.0.0.1:8000/docs) for the full WebSocket schema.

---

## Streamlit Dashboard [Core]

Access at `http://127.0.0.1:8501`.

### Login Roles

| Role | Access |
|------|--------|
| `viewer` | Read-only: health, drift events, scorecards |
| `admin` | Full access including manual probes |

### Panels

| Panel | Description |
|-------|-------------|
| **Source Health** | Uptime %, p95 latency, error budget burn (red/yellow/green) |
| **Probe Scheduler** | Manual probes per source or all; scheduler status |
| **Drift Events** | Recent contract drift with type, severity, score |
| **Dependency Incidents** | Availability, latency, and drift incidents with lifecycle state |
| **Live Stream** | WebSocket events: observation.created, drift.detected, job.progress, ping |
| **Agent Enrichment** | Run status and Postgres-checkpointed HITL approve/reject flow |

### Configuration

| Env Var | Purpose |
|---------|---------|
| `INGESTOR_URL` | API base URL (default: `http://localhost:8000`) |
| `BEARER_TOKEN` | Ingestor API token (or `.streamlit/secrets.toml`) |

---

## Additional Implemented Capabilities

### Agent Enrichment (LangGraph) [Core Optional Path]

AI-powered analysis of observations via LangGraph StateGraph:

- **Classification**: Automatic categorization (incident, performance, schema change)
- **Priority Scoring**: Criticality assessment (1-5 scale)
- **Sentiment Analysis**: Health trend detection
- **Draft Analysis**: optional provider-backed analysis after deterministic classification

Runs support a human-in-the-loop pause and explicit approve/reject resume.

### Vector Search [Core Optional Path]

The inference service uses pgvector and supports deterministic embeddings in tests. Qdrant
is deferred rather than part of the current runtime.

### Multi-Channel Notifications [Core, Provider-Optional]

The ingestor dispatches Slack, Telegram, outbound webhook, and email notifications. Unit and
integration tests exercise dispatch behavior without claiming that external providers are
configured in a deployed environment.

### Dependency Incident Lifecycle [Core]

Repeated availability failures, configured latency breaches, and breaking drift create one
tenant-scoped incident instead of one alert per event. See the [operations guide](../08-operations/dependency-incidents.md).

---

## Practical Value

- Detect dependency outages and latency degradation before users report them.
- Preserve contract-change evidence instead of relying on transient alerts.
- Prioritize incidents using uptime, latency, drift severity, and operator state.

---

## Related Documents

- [Application Architecture](../02-architecture/application-architecture.md) — service structure and data flows
- [Infrastructure Deployment Guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md) — canonical cloud deploy and monitoring guide
- [Observability](../08-operations/observability.md) — metrics, tracing, logging
