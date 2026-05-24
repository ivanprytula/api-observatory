"""Integration tests for background processing API endpoints (Pillar 5).

These tests explicitly enable FastAPI lifespan so startup hooks run and the
background worker pool is created.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from services.ingestor.config import settings
from services.ingestor.main import app


_BACKGROUND_BATCH = {
    "records": [
        {
            "source": "bg-api-example-1",
            "timestamp": "2024-01-15T10:00:00",
            "data": {"price": 101.5},
            "tags": ["Stock", "NASDAQ"],
        },
        {
            "source": "bg-api-example-2",
            "timestamp": "2024-01-15T10:01:00",
            "data": {"price": 102.5},
            "tags": ["Stock", "NYSE"],
        },
    ]
}


class _DummyAsyncSessionContext:
    """Minimal async context manager to replace AsyncSessionLocal in tests."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest_asyncio.fixture()
async def client_with_background_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient]:
    """Async client with lifespan enabled and worker pool feature flag on."""

    async def _fake_ingest_api_batch(
        db: object,
        requests: list[Any],
        idempotency_key_prefix: str | None = None,
    ) -> dict[str, Any]:
        _ = db
        _ = idempotency_key_prefix
        await asyncio.sleep(0.01)
        return {"inserted": len(requests), "errors": 0, "first_error": None}

    old_enabled = settings.background_workers_enabled
    old_count = settings.background_worker_count
    old_queue_size = settings.background_worker_queue_size
    old_max_tracked = settings.background_max_tracked_tasks

    settings.background_workers_enabled = True
    settings.background_worker_count = 1
    settings.background_worker_queue_size = 50
    settings.background_max_tracked_tasks = 100

    monkeypatch.setattr(
        "services.ingestor.core.background_workers.AsyncSessionLocal",
        lambda: _DummyAsyncSessionContext(),
    )
    monkeypatch.setattr(
        "services.ingestor.core.background_workers.jobs.ingest_api_batch",
        _fake_ingest_api_batch,
    )

    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client
    finally:
        settings.background_workers_enabled = old_enabled
        settings.background_worker_count = old_count
        settings.background_worker_queue_size = old_queue_size
        settings.background_max_tracked_tasks = old_max_tracked


async def _wait_until_task_done(client: AsyncClient, task_id: str) -> dict[str, Any]:
    """Poll task status endpoint until it reaches terminal state."""
    for _ in range(100):
        response = await client.get(f"/api/v1/background/tasks/{task_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"succeeded", "failed", "cancelled"}:
            return body
        await asyncio.sleep(0.01)
    raise AssertionError(f"Task {task_id} did not reach terminal state")


# ---------------------------------------------------------------------------
# Worker health endpoint
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_background_workers_health_running(
    client_with_background_workers: AsyncClient,
) -> None:
    """Worker health endpoint reports running pool when feature flag is enabled."""
    r = await client_with_background_workers.get("/api/v1/background/workers/health")

    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True
    assert body["worker_count"] == 1
    assert body["queue_capacity"] == 50


# ---------------------------------------------------------------------------
# Submit + status endpoints
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_submit_background_batch_and_observe_success_status(
    client_with_background_workers: AsyncClient,
) -> None:
    """Submitting a batch returns task id and task status transitions to success."""
    submit = await client_with_background_workers.post(
        "/api/v1/background/ingest/batch",
        json=_BACKGROUND_BATCH,
    )

    assert submit.status_code == 202
    submit_body = submit.json()
    assert submit_body["task_id"]
    assert submit_body["status"] == "queued"
    assert submit_body["batch_size"] == 2

    final_status = await _wait_until_task_done(
        client_with_background_workers,
        submit_body["task_id"],
    )
    assert final_status["status"] == "succeeded"
    assert final_status["result"] is not None
    assert final_status["result"]["inserted"] == 2
    assert final_status["error"] is None


@pytest.mark.integration
async def test_background_task_status_not_found(
    client_with_background_workers: AsyncClient,
) -> None:
    """Unknown background task id returns 404."""
    r = await client_with_background_workers.get(
        "/api/v1/background/tasks/does-not-exist"
    )

    assert r.status_code == 404
    body = r.json()
    assert "detail" in body
