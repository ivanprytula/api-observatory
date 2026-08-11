"""Observation query helpers, cursor pagination, enrichment, and tag counts."""

import asyncio
import base64
import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import EnrichedObservation
from services.ingestor.fetch import fetch_with_retry
from services.ingestor.models import Observation


def _encode_cursor(observation_id: int, timestamp: datetime) -> str:
    """Encode a cursor as base64(JSON) for opaque pagination positioning."""
    cursor_data = {
        "id": observation_id,
        "timestamp": timestamp.isoformat() if timestamp else None,
    }
    json_str = json.dumps(cursor_data, separators=(",", ":"))
    return base64.b64encode(json_str.encode()).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[int, datetime | None] | None:
    """Decode a cursor back into (observation_id, timestamp) pair."""
    if not cursor:
        return None
    try:
        json_str = base64.b64decode(cursor).decode("utf-8")
        data = json.loads(json_str)
        observation_id = data.get("id")
        ts_str = data.get("timestamp")
        timestamp = datetime.fromisoformat(ts_str) if ts_str else None
        return (observation_id, timestamp)
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


async def get_observations_cursor_paginated(
    session: AsyncSession,
    cursor: str | None = None,
    limit: int = 50,
    source: str | None = None,
) -> tuple[list[Observation], str | None, bool]:
    """Fetch observations using cursor-based pagination (stable under concurrent inserts)."""
    cursor_data = _decode_cursor(cursor)
    last_id = cursor_data[0] if cursor_data else 0
    last_timestamp = cursor_data[1] if cursor_data else None

    query = (
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .order_by(Observation.timestamp, Observation.id)
    )

    if cursor_data:
        query = query.where(
            (Observation.timestamp > last_timestamp)
            | ((Observation.timestamp == last_timestamp) & (Observation.id > last_id))
        )

    if source:
        query = query.where(Observation.source == source)

    query = query.limit(limit + 1)
    result = await session.execute(query)
    observations_all = list(result.scalars().all())

    has_more = len(observations_all) > limit
    observations = observations_all[:limit]

    next_cursor = None
    if observations and has_more:
        last_observation = observations[-1]
        next_cursor = _encode_cursor(last_observation.id, last_observation.timestamp)

    return observations, next_cursor, has_more


async def get_observations_with_tag_counts_naive(
    session: AsyncSession, limit: int = 10
) -> list[dict]:
    """Fetch observations with tag counts using N+1 pattern (deliberate inefficiency)."""
    query = (
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .order_by(Observation.id.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    observations = list(result.scalars().all())

    data = []
    for observation in observations:
        tag_count = len(observation.tags) if observation.tags else 0
        data.append(
            {
                "id": observation.id,
                "source": observation.source,
                "timestamp": observation.timestamp.isoformat(),
                "tag_count": tag_count,
            }
        )
    return data


async def get_observations_with_tag_counts(
    session: AsyncSession, limit: int = 10
) -> list[dict]:
    """Fetch observations with tag counts using a single optimized query."""
    query = (
        select(
            Observation.id,
            Observation.source,
            Observation.timestamp,
            Observation.tags,
        )
        .where(Observation.deleted_at.is_(None))
        .order_by(Observation.id.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    rows = result.all()

    return [
        {
            "id": row.id,
            "source": row.source,
            "timestamp": row.timestamp.isoformat(),
            "tag_count": len(row.tags) if row.tags else 0,
        }
        for row in rows
    ]


async def enrich_observations_concurrent(
    session: AsyncSession,
    observation_ids: list[int],
    semaphore: asyncio.Semaphore,
) -> list[EnrichedObservation]:
    """Enrich a batch of observations with external API data concurrently."""
    logger = logging.getLogger(__name__)

    result = await session.execute(
        select(Observation)
        .where(Observation.id.in_(observation_ids))
        .where(Observation.deleted_at.is_(None))
    )
    observations_by_id: dict[int, Observation] = {
        r.id: r for r in result.scalars().all()
    }

    async def enrich_one(observation_id: int) -> EnrichedObservation:
        """Fetch external metadata for a single observation, respecting semaphore."""
        observation = observations_by_id.get(observation_id)
        if observation is None:
            return EnrichedObservation(
                observation_id=observation_id,
                source="unknown",
                enriched=False,
                error=f"Observation {observation_id} not found",
            )

        async with semaphore:
            try:
                post_id = (observation_id % 100) or 1
                url = f"https://jsonplaceholder.typicode.com/posts/{post_id}"
                data = await fetch_with_retry(url, max_retries=2)

                logger.info(
                    "observation_enriched",
                    extra={"observation_id": observation_id, "post_id": post_id},
                )
                return EnrichedObservation(
                    observation_id=observation_id,
                    source=observation.source,
                    external_title=data.get("title"),
                    external_body=data.get("body"),
                    enriched=True,
                )
            except Exception as exc:
                logger.warning(
                    "observation_enrich_failed",
                    extra={"observation_id": observation_id, "error": str(exc)},
                )
                return EnrichedObservation(
                    observation_id=observation_id,
                    source=observation.source,
                    enriched=False,
                    error=str(exc),
                )

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(enrich_one(rid)) for rid in observation_ids]

    return [t.result() for t in tasks]
