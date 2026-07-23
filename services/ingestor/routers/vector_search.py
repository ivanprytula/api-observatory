"""Vector-search routes for Pillar 9 baseline."""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import services.ingestor.vector_search as vector_search
from libs.platform.bulkhead import BulkheadRejectedError
from libs.platform.circuit_breaker import CircuitOpenError
from services.ingestor.api_schemas.observations import (
    VectorSearchHealthResponse,
    VectorSearchIndexRequest,
    VectorSearchIndexResponse,
    VectorSearchQueryRequest,
    VectorSearchQueryResponse,
    VectorSearchReindexRecentRequest,
)
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.database import get_db
from services.ingestor.models import Observation


logger = logging.getLogger(__name__)
type DbDep = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix=f"{API_V1_PREFIX}/vector-search", tags=["vector-search"])


def _raise_inference_temporarily_unavailable(exc: Exception) -> None:
    """Translate resilience admission failures into a stable API response."""
    logger.warning("vector_search_resilience_rejected", extra={"error": str(exc)})
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI gateway temporarily unavailable",
    ) from exc


@router.get(
    "/health",
    response_model=VectorSearchHealthResponse,
    status_code=status.HTTP_200_OK,
)
async def vector_search_health() -> VectorSearchHealthResponse:
    """Report whether the AI gateway is reachable for semantic search."""
    try:
        raw = await vector_search.get_vector_search_health()
    except (BulkheadRejectedError, CircuitOpenError) as exc:
        _raise_inference_temporarily_unavailable(exc)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("vector_search_health_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI gateway unavailable",
        ) from exc

    return VectorSearchHealthResponse(
        status=str(raw.get("status", "ok")),
        inference_connected=bool(raw.get("qdrant_connected", True)),
        collection=vector_search.settings.vector_search_collection,
    )


@router.post(
    "/index/observations",
    response_model=VectorSearchIndexResponse,
    status_code=status.HTTP_200_OK,
)
async def index_observations_for_vector_search(
    payload: VectorSearchIndexRequest,
    db: DbDep,
) -> VectorSearchIndexResponse:
    """Index selected observations into the AI gateway vector collection."""
    observation_ids = list(dict.fromkeys(payload.observation_ids))
    stmt = (
        select(Observation)
        .where(Observation.id.in_(observation_ids), Observation.deleted_at.is_(None))
        .order_by(Observation.id)
    )
    observations = list((await db.execute(stmt)).scalars().all())
    if not observations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active observations found for indexing",
        )

    found_ids = {observation.id for observation in observations}
    missing_observation_ids = [
        observation_id
        for observation_id in observation_ids
        if observation_id not in found_ids
    ]

    try:
        raw = await vector_search.index_observation_documents(
            observations,
            collection=payload.collection,
        )
    except (BulkheadRejectedError, CircuitOpenError) as exc:
        _raise_inference_temporarily_unavailable(exc)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "vector_search_index_failed",
            extra={"error": str(exc), "requested_count": len(observation_ids)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI gateway indexing failed",
        ) from exc

    return VectorSearchIndexResponse(
        requested_count=len(observation_ids),
        indexed_count=int(raw.get("indexed_count", len(observations))),
        missing_observation_ids=missing_observation_ids,
        collection=str(
            raw.get(
                "collection",
                payload.collection or vector_search.settings.vector_search_collection,
            )
        ),
    )


@router.post(
    "/query",
    response_model=VectorSearchQueryResponse,
    status_code=status.HTTP_200_OK,
)
async def query_vector_search(
    payload: VectorSearchQueryRequest,
) -> VectorSearchQueryResponse:
    """Query semantically similar indexed observations via the AI gateway."""
    try:
        raw = await vector_search.search_observation_documents(
            query=payload.query,
            top_k=payload.top_k,
            collection=payload.collection,
            filters=payload.filters,
        )
    except (BulkheadRejectedError, CircuitOpenError) as exc:
        _raise_inference_temporarily_unavailable(exc)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("vector_search_query_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI gateway search failed",
        ) from exc

    return VectorSearchQueryResponse(
        results=raw.get("results", []),
        count=int(raw.get("count", 0)),
        query=str(raw.get("query", payload.query)),
        collection=payload.collection
        or vector_search.settings.vector_search_collection,
    )


@router.post(
    "/index/recent",
    response_model=VectorSearchIndexResponse,
    status_code=status.HTTP_200_OK,
)
async def index_recent_observations_for_vector_search(
    payload: VectorSearchReindexRecentRequest,
    db: DbDep,
) -> VectorSearchIndexResponse:
    """Index a recent window of active observations for operational backfill."""
    stmt = select(Observation).where(Observation.deleted_at.is_(None))
    if payload.source is not None:
        stmt = stmt.where(Observation.source == payload.source)

    stmt = stmt.order_by(Observation.timestamp.desc()).limit(payload.limit)
    observations = list((await db.execute(stmt)).scalars().all())
    if not observations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active observations found for recent indexing",
        )

    try:
        raw = await vector_search.index_observation_documents(
            observations,
            collection=payload.collection,
        )
    except (BulkheadRejectedError, CircuitOpenError) as exc:
        _raise_inference_temporarily_unavailable(exc)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "vector_search_recent_index_failed",
            extra={
                "error": str(exc),
                "source": payload.source,
                "limit": payload.limit,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI gateway recent indexing failed",
        ) from exc

    return VectorSearchIndexResponse(
        requested_count=len(observations),
        indexed_count=int(raw.get("indexed_count", len(observations))),
        missing_observation_ids=[],
        collection=str(
            raw.get(
                "collection",
                payload.collection or vector_search.settings.vector_search_collection,
            )
        ),
    )
