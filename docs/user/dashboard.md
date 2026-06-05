# Dashboard User Guide

The Streamlit dashboard provides a visual interface for monitoring API health, drift events, and enrichment results.

## Access

Open `http://localhost:8501` after starting the services with `just up`.

Login credentials:

- Username: `viewer` (read-only access)
- Username: `admin` (full access including probe triggers)

## Panels

### 1. Source Health

Real-time reliability scorecards for all registered APIs:

| Column | Description |
|--------|-------------|
| Source ID | Unique identifier for the API |
| Uptime % | Success rate over the selected window |
| p95 Latency ms | 95th-percentile response time |
| Error Budget Burn | Rate of SLO budget consumption (1.0 = on track to exhaust) |

> **Thresholds**: >99% uptime = 🟢; 95-99% = 🟡; <95% = 🔴

### 2. Probe Scheduler

Execute manual health probes or monitor scheduled jobs:

- **Probe all**: Trigger probes for every registered source
- **Probe (per source)**: Trigger individual probes
- **Scheduler status**: View job execution counts and next scheduled run

### 3. Drift Events

Recent contract drift detections across all sources:

| Column | Description |
|--------|-------------|
| Source | API that experienced drift |
| Detected | Timestamp of detection |
| Type | Drift event type |
| Severity | Critical/High/Medium/Low impact |
| Compatibility Score | Numerical measure of change severity |
| Summary | Brief description of the change |

### 4. Live Stream

WebSocket connection for real-time event streaming:

| Event Type | Description |
|------------|-------------|
| `observation.created` | New data observation ingested |
| `drift.detected` | Contract drift event detected |
| `job.progress` | Scheduler job progress update |
| `ping` | Server keepalive (every 30s) |

Click **Connect** to start streaming. Events accumulate up to 50 messages.

### 5. Agent Enrichment

Invoke the LangGraph agent to analyze observations:

#### Full Run (Auto)

Enter an observation ID and click **Enrich** for immediate classification and analysis.

#### HITL Review

Start a human-in-the-loop review. The agent pauses before publishing, allowing approval or rejection of results.

#### Stream (SSE)

Stream analysis progress node-by-node via Server-Sent Events.

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INGESTOR_URL` | `http://localhost:8000` | Base URL of the API service |
| `BEARER_TOKEN` | — | JWT for WebSocket authentication |

### Remote Ingestor

Point to a remote deployment:

```bash
INGESTOR_URL=https://api.your-domain.com uv run streamlit run streamlit_app.py
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No scorecards yet" | Add sources and wait for first probe cycle |
| "Could not reach ingestor" | Verify `just up` completed, check Docker logs |
| "Log in to view data" | Use credentials from `.env` file |
| WebSocket won't connect | Ensure `REDIS_ENABLED=true` on the server |
