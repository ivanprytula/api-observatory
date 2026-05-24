"""Background processing routes for Pillar 5 worker-queue prototype."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from services.ingestor.api_schemas.records import (
    BackgroundBatchSubmitResponse,
    BackgroundTaskStatusResponse,
    BatchRecordsRequest,
)
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.core.background_workers import BackgroundWorkerPool


router = APIRouter(prefix=f"{API_V1_PREFIX}/background", tags=["background"])

_worker_pool: BackgroundWorkerPool | None = None


def set_worker_pool(worker_pool: BackgroundWorkerPool | None) -> None:
    """Inject the background worker pool created during app startup."""
    global _worker_pool
    _worker_pool = worker_pool


@router.post(
    "/ingest/batch",
    response_model=BackgroundBatchSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_background_batch_ingest(
    payload: BatchRecordsRequest,
) -> BackgroundBatchSubmitResponse:
    """Queue a large batch ingest task for worker-pool execution."""
    if _worker_pool is None or not _worker_pool.running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background workers are disabled or not running",
        )

    try:
        submitted = await _worker_pool.submit_batch_ingest(payload.records)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    return BackgroundBatchSubmitResponse(
        task_id=submitted.task_id,
        status=submitted.status,
        batch_size=submitted.batch_size,
        queued_at=submitted.queued_at,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=BackgroundTaskStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_background_task_status(task_id: str) -> BackgroundTaskStatusResponse:
    """Return status for one background ingestion task."""
    if _worker_pool is None or not _worker_pool.running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background workers are disabled or not running",
        )

    task_status = _worker_pool.get_task_status(task_id)
    if task_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background task {task_id} not found",
        )

    return BackgroundTaskStatusResponse(
        task_id=task_status.task_id,
        status=task_status.status,
        batch_size=task_status.batch_size,
        queued_at=task_status.queued_at,
        started_at=task_status.started_at,
        finished_at=task_status.finished_at,
        result=task_status.result,
        error=task_status.error,
    )


@router.get("/workers/health", response_model=dict[str, Any])
async def get_background_workers_health() -> dict[str, Any]:
    """Return lightweight worker pool health summary."""
    if _worker_pool is None:
        return {
            "running": False,
            "detail": "Background workers disabled",
        }
    return _worker_pool.health_summary()
