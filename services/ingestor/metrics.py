"""Custom Prometheus metrics for the data pipeline.

This module defines all application-level counters and histograms.
It is imported once at startup and kept as module-level singletons —
prometheus_client enforces that metric names are globally unique within
a process, so registering the same name twice raises a ValueError.

Metric naming convention (Prometheus best practice):
  <namespace>_<subsystem>_<unit>_<suffix>
  e.g. pipeline_observations_created_total

Exposed on: GET /metrics (text/plain; version=0.0.4)

Pillars:
  Pillar 4 — Observability (entry point)
  Next step: connect Grafana dashboard (Week 5)
"""

from prometheus_client import Counter, Gauge, Histogram


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

observations_created_total = Counter(
    name="pipeline_observations_created_total",
    documentation="Number of observations successfully inserted (all endpoints combined).",
    labelnames=["endpoint"],
)
"""Incremented on every successful observation INSERT.

Labels:
  endpoint: "single" | "batch" | "upsert"

Usage::

    from services.ingestor.metrics import observations_created_total
    observations_created_total.labels(endpoint="single").inc()
"""

llm_prompt_tokens_total = Counter(
    name="pipeline_llm_prompt_tokens_total",
    documentation="Total number of prompt tokens used in LLM calls.",
    labelnames=["model", "endpoint"],
)
"""Incremented with the number of prompt tokens returned by the LLM.

Labels:
  model: OpenAI model name (e.g. "gpt-4o")
  endpoint: "analyze" | "analyze_stream"
"""

observations_upsert_conflicts_total = Counter(
    name="pipeline_observations_upsert_conflicts_total",
    documentation="Number of upsert requests that hit an existing observation (conflict resolved).",
    labelnames=["mode"],
)
"""Incremented when upsert detects a (source, timestamp) conflict.

Labels:
  mode: "idempotent" | "strict"
"""


# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------

circuit_breaker_state = Gauge(
    name="pipeline_circuit_breaker_state",
    documentation="Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN).",
    labelnames=["circuit"],
)
"""Circuit breaker state indicator.

Labels:
  circuit: Function qualified name (e.g. "_send_to_kafka", "_mongo_insert_one")

Values:
  0 = CLOSED (normal operation)
  1 = OPEN (failures >= threshold, calls rejected)
  2 = HALF_OPEN (recovery timeout elapsed, probe allowed)

Usage::

    from services.ingestor.metrics import circuit_breaker_state
    circuit_breaker_state.labels(circuit="my_function").set(1)  # OPEN
"""

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

batch_size_histogram = Histogram(
    name="pipeline_batch_insert_size",
    documentation="Distribution of batch insert sizes (number of observations per /batch request).",
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
)
"""Observe the batch size on every POST /api/v1/observations/batch call.

Usage::

    from services.ingestor.metrics import batch_size_histogram
    batch_size_histogram.observe(len(observations))
"""

enrich_duration_seconds = Histogram(
    name="pipeline_enrich_duration_seconds",
    documentation="Wall-clock time (seconds) for a full /enrich fan-out request.",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
"""Observe total enrichment wall time per /enrich call."""


# ---------------------------------------------------------------------------
# Cache metrics
# ---------------------------------------------------------------------------

cache_hits_total = Counter(
    name="pipeline_cache_hits_total",
    documentation="Number of successful cache hits (observation retrieved from cache).",
    labelnames=["operation"],
)
"""Incremented when cache.get_observation() returns a cached value.

Labels:
  operation: "get" | "list" (currently only "get" in use)
"""

cache_misses_total = Counter(
    name="pipeline_cache_misses_total",
    documentation="Number of cache misses (observation not in cache, fetched from DB).",
    labelnames=["operation"],
)
"""Incremented when cache.get_observation() returns None (cache miss).

Labels:
  operation: "get" | "list" (currently only "get" in use)
"""

cache_errors_total = Counter(
    name="pipeline_cache_errors_total",
    documentation="Number of cache operation errors (Redis connection, serialization).",
    labelnames=["operation"],
)
"""Incremented when cache operations fail (fail-open, logged as warning).

Labels:
  operation: "get" | "set" | "invalidate"
"""


# ---------------------------------------------------------------------------
# Scheduled job metrics
# ---------------------------------------------------------------------------

job_executions_total = Counter(
    name="pipeline_job_executions_total",
    documentation="Number of scheduled job executions by outcome.",
    labelnames=["job_name", "status"],
)
"""Incremented on every scheduled job completion.

Labels:
  job_name: Registered job name (e.g. "api_ingest_hourly")
  status: "success" | "timeout" | "failed"

Usage::

    from services.ingestor.metrics import job_executions_total
    job_executions_total.labels(job_name="api_ingest_hourly", status="success").inc()
"""

job_duration_seconds = Histogram(
    name="pipeline_job_duration_seconds",
    documentation="Wall-clock execution time for scheduled jobs.",
    labelnames=["job_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)
"""Observe execution duration per scheduled job.

Labels:
  job_name: Registered job name

Usage::

    from services.ingestor.metrics import job_duration_seconds
    job_duration_seconds.labels(job_name="api_ingest_hourly").observe(duration)
"""


# ---------------------------------------------------------------------------
# Background processing metrics (Pillar 5)
# ---------------------------------------------------------------------------

background_jobs_submitted_total = Counter(
    name="pipeline_background_jobs_submitted_total",
    documentation="Number of background jobs submitted to the in-process worker queue.",
    labelnames=["kind"],
)
"""Incremented when a background task is accepted into the queue.

Labels:
  kind: currently "batch_ingest"
"""

background_jobs_processed_total = Counter(
    name="pipeline_background_jobs_processed_total",
    documentation="Number of background jobs processed by outcome.",
    labelnames=["kind", "status"],
)
"""Incremented when background task processing finishes.

Labels:
  kind: currently "batch_ingest"
  status: "succeeded" | "failed" | "cancelled"
"""

background_jobs_in_queue = Gauge(
    name="pipeline_background_jobs_in_queue",
    documentation="Current number of pending jobs in the background queue.",
)
"""Updated after every enqueue/dequeue operation."""

background_jobs_active = Gauge(
    name="pipeline_background_jobs_active",
    documentation="Current number of jobs actively processed by workers.",
)
"""Incremented when a worker starts processing and decremented on completion."""
