# Streamlit Dashboard

A single-page visual interface for the API Observatory portfolio.
Lets reviewers see live data without needing to interact with the REST API directly.

## Panels

| Panel | What it shows | Refresh |
|-------|--------------|---------|
| Source Health | Scorecards table: uptime %, p95 latency, error-budget burn rate | Every 30 s (cached) |
| Drift Events | Recent contract drift events across all sources, newest first | Every 30 s (cached) |
| Live Stream | WebSocket event tail — up to 50 messages | Real-time (connect button) |

## Running locally

### Prerequisites

- Ingestor running through the active local URL mode (`just up` or `LOCAL_API_SCHEME=https just up-https`)
- Dependencies installed: `uv sync`

### Start the dashboard

```bash
uv run streamlit run services/dashboard/streamlit_app.py
```

The dashboard opens at `http://127.0.0.1:8501` for direct Streamlit, or through the active local URL helper when using the edge proxy.

### With a bearer token (if `API_V1_BEARER_TOKEN` is set on the server)

```bash
BEARER_TOKEN=mysecret uv run streamlit run services/dashboard/streamlit_app.py
```

Or create `.streamlit/secrets.toml`:

```toml
BEARER_TOKEN = "mysecret"
```

### Point to a remote ingestor

```bash
INGESTOR_URL=https://api.example.com uv run streamlit run services/dashboard/streamlit_app.py
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INGESTOR_URL` | `$(bash scripts/daily/local-url.sh api-base-url)` | Base URL of the ingestor service |
| `BEARER_TOKEN` | *(empty)* | Bearer token for the WebSocket `?token=` param |

## Live Stream panel

The WebSocket panel connects to `WS /ws/observations/stream`.  Click **Connect** to
start receiving events.  The panel auto-refreshes every second while connected.
Events accumulate up to 50 messages; older ones are dropped automatically.

Message types:

- `observation.created` — a new pipeline observation was ingested
- `drift.detected` — a contract drift event was persisted
- `job.progress` — background job progress update
- `ping` — server keepalive (every 30 s)
- `info` — stream unavailable (Cache not enabled on the server)

Click **Disconnect** to stop the stream.  Click **Clear** to reset the message list.

## Architecture

```text
services/dashboard/streamlit_app.py
│
├── httpx (sync) ─── GET /api/v1/scorecards     ─── ingestor
│                ─── GET /api/v1/sources
│                ─── GET /api/v1/contracts/sources/{id}/drift-events
│
└── websockets ────── WS /ws/observations/stream     ─── ingestor (Cache pub/sub)
     (daemon thread)
```

The dashboard never connects to PostgreSQL or Cache directly.
All data comes through the ingestor HTTP/WebSocket API.

## Notes on the WebSocket approach

Streamlit re-renders on each user interaction.  The WebSocket connection runs in a
`daemon=True` background thread and accumulates messages into `st.session_state`.
While connected, `st.rerun()` is called every second so new messages appear live.

This approach is intentionally simple and avoids the complexity of async Streamlit
extensions.  For a production-grade real-time dashboard consider Plotly Dash or a
dedicated frontend.
