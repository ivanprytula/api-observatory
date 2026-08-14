# Observability Guide

Use metrics, logs, traces, and health probes together to diagnose the current system. The
monitoring stack is opt-in; `just dev-up` starts the core application stack, while
`just dev-up-monitoring` starts the monitoring profile. It requires `OTEL_ENABLED=true`;
restart the application services before starting monitoring.

## Current Signal Stack

| Signal | Current implementation | Access |
| --- | --- | --- |
| Metrics | Prometheus scrapes the ingestor `/metrics` endpoint | `http://127.0.0.1:9090` |
| Dashboards | Grafana with provisioned Prometheus, Loki, and Tempo data sources | `http://127.0.0.1:3000` |
| Logs | Structured application logs collected by Promtail into Loki | Grafana Explore |
| Traces | OpenTelemetry OTLP export from instrumented services to Tempo | Grafana Explore |
| Alerts | Prometheus rules routed through Alertmanager | `http://127.0.0.1:9093` |
| Exceptions | Optional Sentry integration when explicitly configured | External |

Tempo replaced the Jaeger design found in older planning material. The active topology is
defined by [`docker-compose.yml`](../../docker-compose.yml) and
[`infra/monitoring/`](../../infra/monitoring/).

## Metrics

Application metrics are defined in
[`services/ingestor/metrics.py`](../../services/ingestor/metrics.py). They cover HTTP
requests, observations, cache outcomes, circuit-breaker state, scheduled jobs, background
queue depth, retention, authentication, and other bounded operational work.

Operational queries and alert thresholds are owned by the provisioned Grafana dashboards and
[`infra/monitoring/rules/`](../../infra/monitoring/rules/). The
[Compose topology](../../docker-compose.yml) owns their runtime references, and the
Justfile owns supported validation syntax.

## Traces and Correlation

The application initializes OpenTelemetry from the service lifespan and exports OTLP when
telemetry is enabled. The local endpoint defaults to `http://tempo:4317`. Request
correlation IDs are propagated in structured logs, which lets Grafana link a trace to the
logs produced during the same request.

Relevant evidence:

- [`services/ingestor/main.py`](../../services/ingestor/main.py)
- [`libs/platform/tracing.py`](../../libs/platform/tracing.py)
- [`infra/monitoring/tempo.yml`](../../infra/monitoring/tempo.yml)
- [`infra/monitoring/grafana/provisioning/datasources/`](../../infra/monitoring/grafana/provisioning/datasources/)

Tracing configuration is evidence of instrumentation, not proof that a particular failure
was diagnosed. Preserve a trace ID, correlated log event, and metric change when running a
failure exercise.

## Debugging Workflows

### Failed API request

1. Capture the response status and correlation ID.
2. Query ingestor logs by correlation ID in Grafana/Loki.
3. Check the matching HTTP error-rate and latency metrics.
4. Inspect the trace in Tempo if tracing was enabled for that run.
5. Check Sentry only when its optional integration was enabled.

### Slow endpoint

1. Find the affected route with the HTTP duration histogram.
2. Compare database, cache, external HTTP, and enrichment spans in Tempo.
3. Inspect cache-miss and circuit-breaker metrics.
4. Reproduce with a bounded focused test or load script before changing code.

### Background queue buildup

1. Compare `pipeline_background_jobs_in_queue` with active-worker metrics.
2. Query worker failures by correlation ID and job kind.
3. Verify whether downstream database, broker, cache, or provider latency increased.
4. Measure drain and recovery time after restoring the dependency.

## Proof and Limits

Start the opt-in monitoring profile through the
[`dev-up-monitoring` target](../../Justfile), then inspect the monitoring services and the ingestor
`/metrics` endpoint. The [Compose topology](../../docker-compose.yml) owns profile and service
details.

This proves local wiring only. A production SLO claim requires a deployed workload,
representative traffic, an agreed objective, and retained incident evidence.
