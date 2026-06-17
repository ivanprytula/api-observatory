# User Guide

Monitor, analyze, and maintain reliable API integrations with real-time visibility into performance, contract changes, and automated insights.

> **Legend:** `[MVP]` = available now, `[Post-MVP]` = coming in a future phase

---

## What is API Observatory? [MVP]

API Observatory continuously checks the health and reliability of your external API dependencies:

- **Is my API still working?** Real-time uptime tracking with configurable health probes
- **How fast is my API?** Latency metrics with 95th-percentile analysis
- **Has the API contract changed?** Automatic detection of breaking schema changes
- **What's the impact?** Error-budget burn rate to prioritize reliability issues

---

## Quick Start [MVP]

### Prerequisites
- Docker and Docker Compose
- Python 3.14+

### Run the Dashboard

```bash
# Start core services (ingestor includes built-in Streamlit dashboard)
just up

# Apply database schema
just migrate

# Manual bootstrap (prints curl commands)
just init
```

Open `http://127.0.0.1:8501` to access the dashboard.

> For local development without Docker:
> ```bash
> uv run streamlit run services/dashboard/streamlit_app.py
> ```

### Monitor Your First API

1. Add a source: `POST /api/v1/sources`
2. Wait for probe cycles (or trigger manually via "Probe all" in dashboard)
3. View real-time metrics in the **Source Health** panel
4. Watch for drift events in the **Live Stream** panel

---

## Source Registration [MVP]

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

## Reliability Scorecards [MVP]

Get rolling-window reliability metrics for any API:

| Metric | Meaning |
|--------|---------|
| Uptime % | Percentage of successful probes |
| p50/p95 Latency | Median and 95th-percentile response time |
| Error Budget Burn Rate | How fast you're consuming your SLO budget |

```bash
GET /api/v1/scorecards/{source_id}?days=7
```

### API Reference

- `POST /api/v1/scorecards/samples` — record a probe result
- `GET /api/v1/scorecards/{source_id}?days=1-90&slo_target_pct=90-100` — query scorecard
- `GET /api/v1/scorecards?source_id=...&limit=...` — list scorecards

Scorecards use a single PostgreSQL `PERCENTILE_CONT` query — no materialization.

---

## Contract Drift Detection [MVP]

When APIs change their response structure, the system detects and classifies the impact:

- **Critical**: Breaking changes requiring immediate attention
- **High**: Significant changes that may affect integrations
- **Medium/Low**: Minor changes or additions
- **Compatibility Score**: Quantitative measure of drift severity (0-100)

Drift events stream to your dashboard in real-time via WebSocket.

### API

- `POST /api/v1/contracts/snapshots` — submit a schema snapshot
- `GET /api/v1/contracts/sources/{source_id}/drift` — list drift events

---

## Live Stream (WebSocket) [MVP]

Real-time event stream at `WS /ws/observations/stream?token=<bearer_token>`.

### Message Types

| Type | Meaning |
|------|---------|
| `observation.created` | New ingestion |
| `drift.detected` | Contract change detected |
| `job.progress` | Background job progress (0-1) |
| `ping` | 30s keepalive |

### Connection Examples

```bash
# wscat
wscat -c "ws://127.0.0.1:8000/ws/observations/stream?token=<bearer>"
```

```javascript
// Browser
const ws = new WebSocket(`wss://api.example.com/ws/observations/stream?token=${token}`);
ws.onmessage = (event) => { console.log(JSON.parse(event.data)); };
```

```python
# Python
import websockets
async with websockets.connect(f"ws://127.0.0.1:8000/ws/observations/stream?token={token}") as ws:
    async for msg in ws: print(msg)
```

Close codes: 4001 (missing token), 4003 (invalid token).

---

## Streamlit Dashboard [MVP]

Access at `http://127.0.0.1:8501` (or via `uv run streamlit run services/dashboard/streamlit_app.py`).

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
| **Live Stream** | WebSocket events: observation.created, drift.detected, job.progress, ping |
| **Agent Enrichment** | Full-run auto, HITL review with approve/reject, SSE streaming |

### Configuration

| Env Var | Purpose |
|---------|---------|
| `INGESTOR_URL` | API base URL (default: `http://localhost:8000`) |
| `BEARER_TOKEN` | Ingestor API token (or `.streamlit/secrets.toml`) |

---

## Post-MVP Features (Coming)

### Agent Enrichment (LangGraph) [Post-MVP]

AI-powered analysis of observations via LangGraph StateGraph:

- **Classification**: Automatic categorization (incident, performance, schema change)
- **Priority Scoring**: Criticality assessment (1-5 scale)
- **Sentiment Analysis**: Health trend detection
- **Deep Analysis**: GPT-4 escalation for high-priority items

Choose between fully-automated, human-in-the-loop review, or streaming via SSE.

### HTMX Operations Dashboard [Post-MVP]

A server-rendered UI with Jinja2 templates and SSE live metrics, replacing the Streamlit dashboard for production use. Panels: Worker Health, Task Lookup, Manual Rerun, Session Bootstrap. Access at `http://127.0.0.1:8003/admin`.

### Vector Search [Post-MVP]

Semantic search across observations using Qdrant vector database, with pgvector comparison.

### Multi-Channel Notifications [Post-MVP]

Alert dispatch via Slack, Telegram, webhook (Jira), and email (Resend) for operational events.

---

## Value Proposition

### For Engineering Teams
- **Proactive Reliability**: Catch API outages before users notice
- **Contract Safety**: Enforce API compatibility through automated monitoring
- **Data-Driven SLAs**: Quantify reliability with SLO-compliant metrics

### For Operations
- **Real-time Visibility**: WebSocket streaming for instant event delivery
- **Operational Health**: Built-in `/health` and `/readyz` endpoints
- **Cost Control**: Explicit teardown guides to prevent cloud waste

### For Product Managers
- **SLA Reporting**: Clear metrics for stakeholder communication
- **Vendor Evaluation**: Compare API reliability objectively

---

## Related Documents

- [Architecture](../02-architecture/architecture.md) — system design and data flows
- [Deployment Guide](../07-deployment/deployment-guide.md) — cloud deploy and monitoring
- [Observability](../08-operations/observability.md) — metrics, tracing, logging
