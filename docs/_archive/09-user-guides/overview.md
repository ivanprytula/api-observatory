# API Observatory — User Guide

Monitor, analyze, and maintain reliable API integrations with real-time visibility into performance, contract changes, and automated insights.

## What is API Observatory?

API Observatory is a production-grade monitoring platform that continuously checks the health and reliability of your external API dependencies. It answers critical questions:

- **Is my API still working?** Real-time uptime tracking with configurable health probes
- **How fast is my API?** Latency metrics with 95th-percentile analysis
- **Has the API contract changed?** Automatic detection of breaking schema changes
- **What's the impact?** Error-budget burn rate to prioritize reliability issues

## Core Functionality

### 1. Source Registration

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

### 2. Reliability Scorecards

Get rolling-window reliability metrics for any API:

| Metric | Meaning |
|--------|---------|
| Uptime % | Percentage of successful probes |
| p95 Latency | 95th-percentile response time (slow tail) |
| Error Budget Burn Rate | How fast you're consuming your SLO budget |

```bash
GET /api/v1/scorecards/{source_id}?days=7
```

### 3. Contract Drift Detection

When APIs change their response structure, API Observatory detects and classifies the impact:

- **Critical**: Breaking changes requiring immediate attention
- **High**: Significant changes that may affect integrations
- **Medium/Low**: Minor changes or additions
- **Compatibility Score**: Quantitative measure of drift severity

Drift events stream to your dashboard in real-time via WebSocket.

### 4. AI-Powered Enrichment

The built-in LangGraph agent analyzes observations to provide:

- **Classification**: Automatic categorization of events (incident, performance, schema change)
- **Priority Scoring**: Criticality assessment (1-5 scale)
- **Sentiment Analysis**: Health trend detection
- **Deep Analysis**: Detailed investigation for high-priority items (escalates to GPT-4 when needed)

Choose between fully-automated analysis, human-in-the-loop review, or streaming results via Server-Sent Events.

## Quick Start

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

The Streamlit dashboard is now bundled inside the `ingestor` container — it starts automatically alongside the API.

Open `http://127.0.0.1:8501` to access the dashboard.

> **Note:** For local development without Docker, run the dashboard separately:

 ```bash
 uv run streamlit run services/dashboard/streamlit_app.py
 ```

### Monitor Your First API

1. Add a source: `POST /api/v1/sources`
2. Wait for probe cycles (or trigger manually via "Probe all" in dashboard)
3. View real-time metrics in the **Source Health** panel
4. Watch for drift events in the **Live Stream** panel

## Value Proposition

### For Engineering Teams

- **Proactive Reliability**: Catch API outages before users notice
- **Contract Safety**: Enforce API compatibility through automated monitoring
- **Data-Driven SLAs**: Quantify reliability with SLO-compliant metrics
- **Reduced Alert Fatigue**: Smart prioritization with error-budget burn rates

### For Operations

- **Real-time Visibility**: WebSocket streaming for instant event delivery
- **Operational Health**: Built-in `/health` and `/readyz` endpoints
- **Runbook Integration**: Pre-built workflows for common scenarios
- **Cost Control**: Explicit teardown guides to prevent cloud waste

### For Product Managers

- **SLA Reporting**: Clear metrics for stakeholder communication
- **Vendor Evaluation**: Compare API reliability objectively
- **Risk Assessment**: Quantify integration failure probability

## Next Steps

- **Dashboard User Guide**: [dashboard.md](dashboard.md)
- **API Reference**: Scorecards guide
- **Architecture**: Architecture Overview
- **Deployment**: AWS ECS Deployment
