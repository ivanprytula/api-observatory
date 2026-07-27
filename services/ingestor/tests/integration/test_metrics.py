"""Integration tests for Step 10 — Prometheus metrics (Pillar 4 bridge).

Tests:
  - GET /metrics returns 200 with prometheus text format
  - Default instrumentator metrics are present (http_requests_total)
  - Custom counter increments after observation creation (observations_created_total)
  - Custom histogram gets a sample after batch insert (batch_insert_size)
  - Custom upsert conflict counter increments on duplicate
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.database import get_db
from services.ingestor.routers import observations_v2
from tests.shared.payloads import OBSERVATION_API


_METRICS_URL = "/metrics"
_OBSERVATION = OBSERVATION_API


# ---------------------------------------------------------------------------
# /metrics endpoint availability
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_metrics_endpoint_returns_200(client: AsyncClient) -> None:
    """GET /metrics returns 200 OK (Prometheus text format)."""
    r = await client.get(_METRICS_URL)
    assert r.status_code == 200


@pytest.mark.integration
async def test_metrics_content_type_is_prometheus_text(client: AsyncClient) -> None:
    """Content-Type header indicates Prometheus exposition format."""
    r = await client.get(_METRICS_URL)
    assert "text/plain" in r.headers["content-type"]


@pytest.mark.integration
async def test_metrics_contains_default_http_metrics(client: AsyncClient) -> None:
    """Default instrumentator metrics exist in /metrics output."""
    r = await client.get(_METRICS_URL)
    body = r.text
    # prometheus_fastapi_instrumentator adds http_requests_total by default
    assert "http_requests_total" in body or "http_request_duration" in body, (
        f"Expected default HTTP metrics in /metrics body. Got:\n{body[:500]}"
    )


@pytest.mark.integration
async def test_metrics_contains_custom_metric_names(client: AsyncClient) -> None:
    """Custom metric names are registered and visible in /metrics output."""
    r = await client.get(_METRICS_URL)
    body = r.text
    assert "pipeline_observations_created_total" in body
    assert "pipeline_batch_insert_size" in body
    assert "pipeline_enrich_duration_seconds" in body
    assert "pipeline_observations_upsert_conflicts_total" in body


# ---------------------------------------------------------------------------
# Custom counter — observations_created_total increments
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_observations_created_counter_increments_on_single_create(
    client: AsyncClient,
) -> None:
    """pipeline_observations_created_total{endpoint="single"}
    increments after POST /observations.
    """

    def _get_single_count(body: str) -> float:
        for line in body.splitlines():
            if (
                "pipeline_observations_created_total" in line
                and 'endpoint="single"' in line
                and not line.startswith("#")
            ):
                return float(line.split()[-1])
        return 0.0

    r_before = await client.get(_METRICS_URL)
    count_before = _get_single_count(r_before.text)

    await client.post("/api/v1/observations", json=_OBSERVATION)

    r_after = await client.get(_METRICS_URL)
    count_after = _get_single_count(r_after.text)

    assert count_after == count_before + 1, (
        f"Expected counter to increment by 1. Before: {count_before}, After: {count_after}"
    )


@pytest.mark.integration
async def test_observations_created_counter_increments_on_batch_create(
    client: AsyncClient,
) -> None:
    """pipeline_observations_created_total{endpoint="batch"}
    increments after POST /observations/batch."""

    def _get_batch_count(body: str) -> float:
        for line in body.splitlines():
            if (
                "pipeline_observations_created_total" in line
                and 'endpoint="batch"' in line
                and not line.startswith("#")
            ):
                return float(line.split()[-1])
        return 0.0

    payload = {
        "observations": [
            {**_OBSERVATION, "source": f"metrics-batch-{i}", "data": {"v": i}}
            for i in range(3)
        ]
    }

    r_before = await client.get(_METRICS_URL)
    count_before = _get_batch_count(r_before.text)

    await client.post("/api/v1/observations/batch", json=payload)

    r_after = await client.get(_METRICS_URL)
    count_after = _get_batch_count(r_after.text)

    assert count_after == count_before + 3, (
        f"Expected batch counter to increment by 3. Before: {count_before}, After: {count_after}"
    )


# ---------------------------------------------------------------------------
# Custom histogram — batch_size_histogram gets a sample
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_batch_size_histogram_has_sample_after_batch_insert(
    client: AsyncClient,
) -> None:
    """pipeline_batch_insert_size_count increments after a batch insert."""

    def _get_histogram_count(body: str) -> float:
        for line in body.splitlines():
            if "pipeline_batch_insert_size_count" in line and not line.startswith("#"):
                return float(line.split()[-1])
        return 0.0

    r_before = await client.get(_METRICS_URL)
    count_before = _get_histogram_count(r_before.text)

    payload = {
        "observations": [
            {**_OBSERVATION, "source": f"hist-test-{i}", "data": {"v": i}}
            for i in range(5)
        ]
    }
    await client.post("/api/v1/observations/batch", json=payload)

    r_after = await client.get(_METRICS_URL)
    count_after = _get_histogram_count(r_after.text)

    assert count_after == count_before + 1, (
        f"Expected histogram count +1. Before: {count_before}, After: {count_after}"
    )


# ---------------------------------------------------------------------------
# Upsert conflict counter
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_upsert_conflict_counter_increments_on_idempotent_duplicate(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """The opt-in v2 upsert route increments its conflict metric on a duplicate.

    The production-default app deliberately does not mount v2 learning routes.
    Mount only the v2 router here so this proof remains independent of the
    default-route inventory asserted by the Phase 4 tests.
    """

    def _get_conflict_count(body: str, mode: str) -> float:
        for line in body.splitlines():
            if (
                "pipeline_observations_upsert_conflicts_total" in line
                and f'mode="{mode}"' in line
                and not line.startswith("#")
            ):
                return float(line.split()[-1])
        return 0.0

    upsert_payload = {
        **_OBSERVATION,
        "source": "conflict-metrics-sensor",
        "timestamp": "2024-06-01T09:00:00",
    }

    r_before = await client.get(_METRICS_URL)
    count_before = _get_conflict_count(r_before.text, "idempotent")

    lab_app = FastAPI()
    lab_app.include_router(observations_v2.router)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        yield db

    lab_app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(
        transport=ASGITransport(app=lab_app), base_url="http://v2-lab"
    ) as lab_client:
        created = await lab_client.post(
            "/api/v2/observations/upsert", json=upsert_payload
        )
        conflict = await lab_client.post(
            "/api/v2/observations/upsert", json=upsert_payload
        )

    assert created.status_code == 201, created.text
    assert conflict.status_code == 200, conflict.text

    r_after = await client.get(_METRICS_URL)
    count_after = _get_conflict_count(r_after.text, "idempotent")

    assert count_after == count_before + 1, (
        f"Expected conflict counter +1. Before: {count_before}, After: {count_after}"
    )


# ---------------------------------------------------------------------------
# Job execution metrics — registered metric names visible in /metrics
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_metrics_contains_job_execution_metric_names(
    client: AsyncClient,
) -> None:
    """Job execution metric names are registered and visible in /metrics output."""
    r = await client.get(_METRICS_URL)
    body = r.text
    assert "pipeline_job_executions_total" in body, (
        "Expected pipeline_job_executions_total in /metrics"
    )
    assert "pipeline_job_duration_seconds" in body, (
        "Expected pipeline_job_duration_seconds in /metrics"
    )
    assert "pipeline_retention_runs_total" in body, (
        "Expected pipeline_retention_runs_total in /metrics"
    )
