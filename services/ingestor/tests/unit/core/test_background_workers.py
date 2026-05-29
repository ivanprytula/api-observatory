"""Unit tests for the in-process background worker pool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.core.background_workers import BackgroundWorkerPool


def _observation(source: str) -> ObservationRequest:
    return ObservationRequest(
        source=source,
        timestamp="2026-04-22T12:00:00Z",
        data={"value": 1},
        tags=["bg"],
    )


async def _wait_for_terminal_state(
    pool: BackgroundWorkerPool,
    task_id: str,
    timeout_seconds: float = 2.0,
) -> str:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        status = pool.get_task_status(task_id)
        assert status is not None
        if status.status in {"succeeded", "failed", "cancelled"}:
            return status.status
        await asyncio.sleep(0.01)
    pytest.fail(f"Task {task_id} did not reach terminal state")


async def test_background_worker_pool_processes_successful_task() -> None:
    async def processor(observations: list[ObservationRequest]) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        return {"inserted": len(observations), "errors": 0, "first_error": None}

    pool = BackgroundWorkerPool(
        worker_count=1,
        queue_size=10,
        max_tracked_tasks=10,
        processor=processor,
    )
    await pool.start()

    try:
        submitted = await pool.submit_batch_ingest([_observation("bg-success")])
        terminal_status = await _wait_for_terminal_state(pool, submitted.task_id)

        assert terminal_status == "succeeded"
        status = pool.get_task_status(submitted.task_id)
        assert status is not None
        assert status.result is not None
        assert status.result["inserted"] == 1
    finally:
        await pool.stop()


async def test_background_worker_pool_marks_failed_task() -> None:
    async def processor(observations: list[ObservationRequest]) -> dict[str, Any]:
        raise RuntimeError(f"boom-{len(observations)}")

    pool = BackgroundWorkerPool(
        worker_count=1,
        queue_size=10,
        max_tracked_tasks=10,
        processor=processor,
    )
    await pool.start()

    try:
        submitted = await pool.submit_batch_ingest([_observation("bg-failure")])
        terminal_status = await _wait_for_terminal_state(pool, submitted.task_id)

        assert terminal_status == "failed"
        status = pool.get_task_status(submitted.task_id)
        assert status is not None
        assert status.error is not None
        assert "boom" in status.error
    finally:
        await pool.stop()


async def test_background_worker_pool_invokes_failure_callback() -> None:
    callback_calls: list[str] = []

    async def processor(observations: list[ObservationRequest]) -> dict[str, Any]:
        raise RuntimeError(f"boom-{len(observations)}")

    async def on_failed(task_status) -> None:
        callback_calls.append(task_status.task_id)

    pool = BackgroundWorkerPool(
        worker_count=1,
        queue_size=10,
        max_tracked_tasks=10,
        processor=processor,
        on_task_failed=on_failed,
    )
    await pool.start()

    try:
        submitted = await pool.submit_batch_ingest([_observation("bg-callback")])
        terminal_status = await _wait_for_terminal_state(pool, submitted.task_id)

        assert terminal_status == "failed"
        assert callback_calls == [submitted.task_id]
    finally:
        await pool.stop()


async def test_background_worker_pool_trims_old_statuses() -> None:
    async def processor(observations: list[ObservationRequest]) -> dict[str, Any]:
        return {"inserted": len(observations), "errors": 0, "first_error": None}

    pool = BackgroundWorkerPool(
        worker_count=1,
        queue_size=10,
        max_tracked_tasks=1,
        processor=processor,
    )
    await pool.start()

    try:
        first = await pool.submit_batch_ingest([_observation("bg-trim-1")])
        await _wait_for_terminal_state(pool, first.task_id)

        second = await pool.submit_batch_ingest([_observation("bg-trim-2")])
        await _wait_for_terminal_state(pool, second.task_id)

        assert pool.get_task_status(first.task_id) is None
        assert pool.get_task_status(second.task_id) is not None
    finally:
        await pool.stop()
