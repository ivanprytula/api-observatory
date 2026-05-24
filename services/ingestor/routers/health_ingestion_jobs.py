"""Health check and observability endpoints for ingestion and job scheduling.

Routes:
- GET /health/ingestion-metrics — Ingestion pipeline health
- GET /health/jobs-metrics — Scheduled job health summary
- GET /health/jobs/{job_name}-metrics — Specific job metrics
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.database import get_db
from services.ingestor.jobs import get_ingestion_health


# Type alias for database dependency
type DbDep = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/health", tags=["health"])

# Global reference to scheduler (injected at app startup)
_scheduler: Any = None


def set_scheduler(scheduler: Any) -> None:
    """Inject scheduler instance into this module (called from app lifespan)."""
    global _scheduler
    _scheduler = scheduler


@router.get("/ingestion-metrics", response_model=dict[str, Any])
async def get_ingestion_status(db: DbDep) -> dict[str, Any]:
    """Get ingestion pipeline health status.

    Returns:
        {
            "status": "healthy" | "unhealthy",
            "records_24h": int,
            "last_record_time": str (ISO 8601) | null,
            "ingestion_enabled": bool,
            "error": str (if unhealthy),
        }
    """
    return await get_ingestion_health(db)


@router.get("/jobs-metrics", response_model=dict[str, Any])
async def get_jobs_health() -> dict[str, Any]:
    """Get health summary for all scheduled jobs.

    Returns:
        {
            "scheduler_running": bool,
            "job_count": int,
            "jobs": {
                "<job_name>": {
                    "last_run_at": str (ISO 8601) | null,
                    "success_count": int,
                    "failure_count": int,
                    "success_rate": float,
                    "is_healthy": bool,
                    "last_error": str | null,
                    "next_run_time": str (ISO 8601) | null,
                }
            }
        }
    """
    if _scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler not initialized",
        )

    job_health = _scheduler.get_all_jobs_health()
    next_run_times = _scheduler.get_next_run_times()

    jobs_detail = {}
    for job_name, metrics in job_health.items():
        jobs_detail[job_name] = {
            "last_run_at": metrics.last_run_at.isoformat()
            if metrics.last_run_at
            else None,
            "success_count": metrics.success_count,
            "failure_count": metrics.failure_count,
            "success_rate": metrics.success_rate,
            "is_healthy": metrics.is_healthy,
            "last_error": metrics.last_error,
            "next_run_time": next_run_times.get(job_name),
        }

    return {
        "scheduler_running": _scheduler.running,
        "job_count": len(job_health),
        "jobs": jobs_detail,
    }


@router.get("/jobs/{job_name}-metrics", response_model=dict[str, Any])
async def get_job_health(job_name: str) -> dict[str, Any]:
    """Get health metrics for a specific scheduled job.

    Args:
        job_name: Name of the job to query.

    Returns:
        {
            "job_name": str,
            "last_run_at": str (ISO 8601) | null,
            "success_count": int,
            "failure_count": int,
            "success_rate": float,
            "is_healthy": bool,
            "last_error": str | null,
            "next_run_time": str (ISO 8601) | null,
        }

    Raises:
        404 Not Found: If job not found.
    """
    if _scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler not initialized",
        )

    metrics = _scheduler.get_job_health(job_name)
    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_name} not found",
        )

    next_run_times = _scheduler.get_next_run_times()

    return {
        "job_name": job_name,
        "last_run_at": metrics.last_run_at.isoformat() if metrics.last_run_at else None,
        "success_count": metrics.success_count,
        "failure_count": metrics.failure_count,
        "success_rate": metrics.success_rate,
        "is_healthy": metrics.is_healthy,
        "last_error": metrics.last_error,
        "next_run_time": next_run_times.get(job_name),
    }
