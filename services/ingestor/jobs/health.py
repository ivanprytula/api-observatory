import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import Observation


logger = logging.getLogger(__name__)


async def get_ingestion_health(db: AsyncSession) -> dict[str, Any]:
    """Get ingestion pipeline health status."""
    try:
        stmt = select(Observation).where(
            Observation.created_at >= datetime.now(UTC) - timedelta(days=1)
        )
        result = await db.execute(stmt)
        observations_24h = len(result.scalars().all())

        stmt = select(Observation).order_by(Observation.created_at.desc()).limit(1)
        result = await db.execute(stmt)
        last_observation = result.scalar_one_or_none()
        last_observation_time = (
            last_observation.created_at if last_observation else None
        )

        return {
            "status": "healthy",
            "observations_24h": observations_24h,
            "last_observation_time": last_observation_time.isoformat()
            if last_observation_time
            else None,
            "ingestion_enabled": True,
        }

    except Exception:
        logger.exception("ingestion_health_check_failed")
        return {
            "status": "unhealthy",
            "error": "Internal ingestion health check failure",
            "ingestion_enabled": False,
        }
