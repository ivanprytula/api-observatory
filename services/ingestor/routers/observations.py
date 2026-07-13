"""Observations resource — all CRUD routes."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import services.ingestor.vector_search as vs_bridge
from services.ingestor import cache, events
from services.ingestor.api_schemas.observations import (
    BatchCreateResponse,
    BatchObservationsRequest,
    ObservationClassification,
    ObservationListResponse,
    ObservationRequest,
    ObservationResponse,
    PaginationMeta,
    SessionResponse,
    UpdateObservationRequest,
)
from services.ingestor.auth import (
    DEFAULT_ROLE,
    create_session,
    jwt_role_guard,
    session_role_guard,
    verify_bearer_token,
    verify_jwt_token,
    verify_session,
)
from services.ingestor.config import settings
from services.ingestor.constants import (
    API_V1_PREFIX,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    V1_RATE_LIMIT,
)
from services.ingestor.database import get_db
from services.ingestor.metrics import (
    batch_size_histogram,
    cache_hits_total,
    cache_misses_total,
    llm_prompt_tokens_total,
    observations_created_total,
)
from services.ingestor.rate_limiting import limiter
from services.ingestor.repositories.observations import (
    create_observation,
    create_observations_batch,
    create_observations_batch_naive,
    get_observations,
    mark_processed,
    soft_delete_observation,
    update_observation,
)
from services.ingestor.repositories.observations import (
    delete_observation as delete_observation_op,
)
from services.ingestor.repositories.observations import (
    get_observation as get_observation_op,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/observations", tags=["observations"])

_R404 = {
    404: {
        "description": "Observation not found.",
        "content": {
            "application/json": {"example": {"detail": "Observation not found"}}
        },
    }
}
_R401 = {
    401: {
        "description": "Not authenticated - missing or invalid session cookie or bearer token.",
        "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
    }
}
_R403 = {
    403: {
        "description": "Forbidden - authenticated but lacking the required role.",
        "content": {"application/json": {"example": {"detail": "Insufficient role"}}},
    }
}
_R422 = {
    422: {
        "description": "Validation error - invalid request body or query parameters.",
        "content": {
            "application/json": {
                "example": {
                    "detail": [
                        {
                            "loc": ["body", "source"],
                            "msg": "field required",
                            "type": "value_error.missing",
                        }
                    ]
                }
            }
        },
    }
}
_R429 = {
    429: {
        "description": "Rate limit exceeded. Retry after the interval in the Retry-After header.",
        "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
    }
}

type DbDep = Annotated[AsyncSession, Depends(get_db)]
type SessionDep = Annotated[dict[str, Any], Depends(verify_session)]
type BearerTokenDep = Annotated[str, Depends(verify_bearer_token)]
type WriterSessionDep = Annotated[
    dict[str, Any], Depends(session_role_guard("writer", "admin", "tenant_admin"))
]
type AdminSessionDep = Annotated[
    dict[str, Any], Depends(session_role_guard("admin", "tenant_admin"))
]

# JWT-based auth for the primary (non-teaching) CRUD/analyze routes below —
# same jwt_role_guard pattern already applied in contract_drift.py,
# source_registry.py and scorecards.py (audit-gaps.md gap 🟠#6).
type JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]
type WriterJwtDep = Annotated[
    dict[str, Any], Depends(jwt_role_guard("writer", "admin", "tenant_admin"))
]
type AdminJwtDep = Annotated[
    dict[str, Any], Depends(jwt_role_guard("admin", "tenant_admin"))
]


# ---------------------------------------------------------------------------
# Observations — single create
# ---------------------------------------------------------------------------
@router.post(
    "",
    summary="Create a observation",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R401, **_R403, **_R422, **_R429},
)
@limiter.limit(V1_RATE_LIMIT)
async def create_observation_endpoint(
    request: Request,
    body: ObservationRequest,
    db: DbDep,
    _: WriterJwtDep,
) -> ObservationResponse:
    """Create a single observation.

    Logs are automatically tagged with correlation ID.
    Rate limit: 1000/minute per IP.
    """
    observation = await create_observation(db, body)
    observations_created_total.labels(endpoint="single").inc()
    # Publish event after successful DB write (Observer pattern — fail-open)
    await events.publish_observation_created(
        observation_id=observation.id,
        payload={"source": observation.source},
    )
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
@router.post(
    "/batch",
    summary="Batch-create observations",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R401, **_R403, **_R422},
    description=(
        "Bulk-create observations.\n\n"
        "**`?impl` query parameter** — internal implementation toggle:\n"
        "- `optimized` *(default)* — single `INSERT … RETURNING` round-trip\n"
        "- `naive` — `add_all` + N individual `REFRESH` calls (N+1 queries)\n\n"
        "Both return identical JSON. The difference is only observable as latency "
        "(use `?impl=naive` vs `?impl=optimized` with a large batch to feel it).\n\n"
        "This pattern — same contract, swappable internals — mirrors how "
        "feature flags and A/B performance experiments work in production."
    ),
)
async def create_observations_batch_endpoint(
    body: BatchObservationsRequest,
    db: DbDep,
    _: WriterJwtDep,
    impl: str = Query(
        default="optimized",
        pattern="^(optimized|naive)$",
        description="Batch insert implementation: 'optimized' (INSERT RETURNING) or 'naive' (add_all + N refreshes).",  # noqa: E501
    ),
) -> BatchCreateResponse:
    """Create multiple observations in batch.

    The `?impl=` parameter selects the internal database strategy without
    changing the response contract — identical JSON either way.
    """
    impl_fn = (
        create_observations_batch
        if impl == "optimized"
        else create_observations_batch_naive
    )
    logger.info("batch_create", extra={"count": len(body.observations), "impl": impl})
    observations = await impl_fn(db, body.observations)
    batch_size_histogram.observe(len(observations))
    observations_created_total.labels(endpoint="batch").inc(len(observations))
    logger.info("batch_created", extra={"count": len(observations), "impl": impl})
    return BatchCreateResponse(created=len(observations), impl=impl)


# ---------------------------------------------------------------------------
# Observations — list with pagination
# ---------------------------------------------------------------------------
@router.get(
    "",
    summary="List observations",
    response_model=ObservationListResponse,
    responses={**_R401, **_R422},
)
async def list_observations(
    db: DbDep,
    _: JwtDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    source: str | None = None,
) -> ObservationListResponse:
    """List observations with pagination and optional filtering by source."""
    observations, total = await get_observations(db, skip, limit, source)
    return ObservationListResponse(
        observations=[ObservationResponse.model_validate(r) for r in observations],
        pagination=PaginationMeta(
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + limit) < total,
        ),
    )


# ---------------------------------------------------------------------------
# Observations — get by ID
# ---------------------------------------------------------------------------
@router.get(
    "/{observation_id}",
    summary="Get a observation by ID",
    response_model=ObservationResponse,
    responses={**_R401, **_R404},
)
async def get_observation(
    observation_id: int, db: DbDep, _: JwtDep
) -> ObservationResponse:
    """Retrieve a single observation by ID.

    Check cache first (Cache); on miss, fetch from DB and cache for 1 hour.
    Cache connection errors are transparent (fail-open).
    """
    # Try cache first
    cached_observation = await cache.get_observation(observation_id)
    if cached_observation is not None:
        cache_hits_total.labels(operation="get").inc()
        return cached_observation

    # Cache miss: fetch from DB
    observation = await get_observation_op(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )

    # Store in cache for future hits
    response = ObservationResponse.model_validate(observation)
    await cache.set_observation(observation_id, response)
    cache_misses_total.labels(operation="get").inc()
    return response


# ---------------------------------------------------------------------------
# Observations — update by ID (partial)
# ---------------------------------------------------------------------------
@router.patch(
    "/{observation_id}",
    summary="Partially update a observation",
    response_model=ObservationResponse,
    responses={**_R401, **_R403, **_R404, **_R422},
)
async def update_observation_endpoint(
    observation_id: int, body: UpdateObservationRequest, db: DbDep, _: WriterJwtDep
) -> ObservationResponse:
    """Update a observation with provided fields (partial update).

    All fields are optional. Only provided fields are updated; others are
    left unchanged.

    Example (update source and tags):
    ```json
    {"source": "new-source", "tags": ["updated", "tags"]}
    ```
    """
    observation = await update_observation(db, observation_id, body)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
# Observations — mark as processed
# ---------------------------------------------------------------------------
@router.patch(
    "/{observation_id}/process",
    summary="Mark a observation as processed",
    response_model=ObservationResponse,
    responses={**_R401, **_R403, **_R404},
)
async def process_observation(
    observation_id: int, db: DbDep, _: WriterJwtDep
) -> ObservationResponse:
    """Mark a observation as processed.

    Invalidates any cached version so next GET reflects updated state.
    """
    observation = await mark_processed(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )
    # Invalidate cache so next read gets fresh data
    await cache.invalidate_observation(observation_id)
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
# Observations — soft-delete (archive)
# ---------------------------------------------------------------------------
@router.patch(
    "/{observation_id}/archive",
    summary="Archive (soft-delete) a observation",
    response_model=ObservationResponse,
    responses={**_R401, **_R403, **_R404},
)
async def archive_observation(
    observation_id: int, db: DbDep, _: WriterJwtDep
) -> ObservationResponse:
    """Soft-delete (archive) a observation.

    Logs are automatically tagged with request correlation ID (cid).
    """
    logger.info("observation_archive", extra={"id": observation_id})
    observation = await soft_delete_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observation not found or already archived",
        )
    logger.info("observation_archived", extra={"id": observation_id})
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
# Observations — delete
# ---------------------------------------------------------------------------
@router.delete(
    "/{observation_id}",
    summary="Hard-delete a observation",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_R401, **_R403, **_R404},
)
async def delete_observation(observation_id: int, db: DbDep, _: AdminJwtDep) -> None:
    """Hard-delete a observation.

    Invalidates any cached version.
    Logs are automatically tagged with request correlation ID (cid).
    """
    logger.info("observation_delete", extra={"id": observation_id})
    observation = await delete_observation_op(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )
    # Invalidate cache since observation no longer exists
    await cache.invalidate_observation(observation_id)
    logger.info("observation_deleted", extra={"id": observation_id})


# ============================================================================
# Auth Examples: v1 Bearer Token + Session-based Auth
# ============================================================================


@router.post(
    "/auth/login",
    summary="Create a session (learning example)",
    response_model=SessionResponse,
    responses={},
)
async def login_session(user_id: str, role: str = DEFAULT_ROLE) -> SessionResponse:
    """Create a session (learning example for session-based auth).

    In production: verify password hash, check rate limits, use HTTPS only, etc.
    Response includes Set-Cookie header with session_id.
    """
    normalized_role = role.strip().lower() if role.strip() else DEFAULT_ROLE
    session_id, cookie_value = await create_session(user_id, {"role": normalized_role})
    logger.info("login_success", extra={"user_id": user_id, "role": normalized_role})

    # Return token explicitly (FastAPI handles Set-Cookie automatically via Response)
    return SessionResponse(session_id=session_id, message="Session created")


@router.get(
    "/{observation_id}/secure",
    summary="Get observation with session auth",
    response_model=ObservationResponse,
    responses={**_R401, **_R404},
)
async def get_observation_secured(
    observation_id: int,
    db: DbDep,
    session: SessionDep,
) -> ObservationResponse:
    """Get observation with session-based auth (learning example).

    Requires valid session cookie. Try:
    1. POST /api/v1/observations/auth/login?user_id=testuser
    2. GET /api/v1/observations/1/secure (with cookie from step 1)

    Production: Use JWT or centralized session store (Cache).
    """
    logger.info(
        "get_observation_secured",
        extra={"observation_id": observation_id, "user_id": session.get("user_id")},
    )
    observation = await get_observation_op(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )
    return ObservationResponse.model_validate(observation)


@router.patch(
    "/{observation_id}/secure/archive",
    summary="Archive observation with session RBAC (writer/admin)",
    response_model=ObservationResponse,
    responses={**_R401, **_R403, **_R404},
)
async def archive_observation_secured(
    observation_id: int,
    db: DbDep,
    session: WriterSessionDep,
) -> ObservationResponse:
    """Archive a observation with session RBAC (writer/admin)."""
    logger.info(
        "observation_archive_secure",
        extra={"id": observation_id, "user_id": session.get("user_id")},
    )
    observation = await soft_delete_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observation not found or already archived",
        )
    return ObservationResponse.model_validate(observation)


@router.delete(
    "/{observation_id}/secure/delete",
    summary="Hard-delete observation with session RBAC (admin only)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_R401, **_R403, **_R404},
)
async def delete_observation_secured(
    observation_id: int,
    db: DbDep,
    session: AdminSessionDep,
) -> None:
    """Hard-delete a observation with session RBAC (admin-only)."""
    logger.info(
        "observation_delete_secure",
        extra={"id": observation_id, "user_id": session.get("user_id")},
    )
    observation = await delete_observation_op(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )
    await cache.invalidate_observation(observation_id)


@router.post(
    "/batch/protected",
    summary="Batch-create observations with bearer token auth",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R401, **_R422},
)
async def create_observations_batch_protected(
    body: BatchObservationsRequest,
    db: DbDep,
    token: BearerTokenDep,
) -> BatchCreateResponse:
    """Batch create with bearer token auth (learning example).

    Requires: Authorization: Bearer <token>
    Set API_V1_BEARER_TOKEN in .env, then:

    curl -X POST http://localhost:8000/api/v1/observations/batch/protected \\
      -H "Authorization: Bearer dev-secret-bearer-token" \\
      -H "Content-Type: application/json" \\
      -d '{"observations": [...]}'

    Production: Use API key rotation, rate limiting per key, audit logs.
    """
    logger.info(
        "batch_protected_create",
        extra={"count": len(body.observations), "token_prefix": token[:10]},
    )
    observations = await create_observations_batch(db, body.observations)
    logger.info("batch_protected_created", extra={"count": len(observations)})
    return BatchCreateResponse(created=len(observations), impl="optimized")


# ============================================================================
# LLM Integration (Phase 2)
# ============================================================================


@router.post(
    "/{observation_id}/analyze",
    summary="Analyze a observation with AI (RAG + OpenAI)",
    response_model=ObservationClassification,
    responses={**_R401, **_R403, **_R404},
)
async def analyze_observation(
    observation_id: int,
    db: DbDep,
    _: WriterJwtDep,
) -> ObservationClassification | None:
    """Analyze a observation using OpenAI and RAG context.

    1. Fetches observation from DB.
    2. Retrieves context from vector search.
    3. Calls OpenAI with structured output (ObservationClassification).
    4. Logs prompt token usage to Prometheus.
    """
    observation = await get_observation_op(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )

    if not settings.openai_enabled or not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="LLM analysis is disabled or OPENAI_API_KEY is missing",
        )

    # RAG: Search for similar observations to provide context
    query_text = (
        f"Source: {observation.source}, Data: {json.dumps(observation.raw_data)}"
    )
    try:
        context_results = await vs_bridge.search_observation_documents(
            query=query_text,
            top_k=3,
        )
        context_docs = [r.get("text", "") for r in context_results.get("results", [])]
        context_text = "\n---\n".join(context_docs)
    except Exception as exc:
        logger.warning("rag_context_failed", extra={"error": str(exc)})
        context_text = "No additional context available."

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Build augmented prompt
    system_prompt = (
        "You are a senior data analyst. Analyze the following observation. "
        "Use the provided context from similar observations if relevant. "
        "Return the analysis as a structured JSON object matching the requested schema."
    )
    user_prompt = (
        f"Context from similar observations:\n{context_text}\n\n"
        f"Observation to analyze:\n"
        f"Source: {observation.source}\n"
        f"Timestamp: {observation.timestamp}\n"
        f"Data: {json.dumps(observation.raw_data)}\n"
        f"Tags: {', '.join(observation.tags)}"
    )

    try:
        # Using beta.chat.completions.parse for Pydantic structured output
        completion = await client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=ObservationClassification,
        )
    except Exception as exc:
        logger.error("llm_analyze_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM analysis failed: {exc}",
        ) from exc

    # Log token usage
    usage = completion.usage
    if usage:
        llm_prompt_tokens_total.labels(
            model=settings.openai_model, endpoint="analyze"
        ).inc(usage.prompt_tokens)

    return completion.choices[0].message.parsed


@router.post(
    "/{observation_id}/analyze/stream",
    responses={**_R401, **_R403, **_R404},
)
async def analyze_observation_stream(
    observation_id: int,
    db: DbDep,
    _: WriterJwtDep,
) -> StreamingResponse:
    """Stream observation analysis from OpenAI (Server-Sent Events)."""
    observation = await get_observation_op(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found"
        )

    if not settings.openai_enabled or not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="LLM analysis is disabled or OPENAI_API_KEY is missing",
        )

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def event_gen() -> AsyncGenerator[str]:
        try:
            # Plan pattern: client.stream("POST", ...) or client.chat.completions.create(...)
            # We'll use the standard completions stream
            stream = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Analyze this observation and provide insights.",
                    },
                    {
                        "role": "user",
                        "content": f"Source: {observation.source}, "
                        f"Data: {json.dumps(observation.raw_data)}",
                    },
                ],
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield f"data: {content}\n\n"
        except Exception as exc:
            logger.error("llm_stream_failed", extra={"error": str(exc)})
            yield "data: [ERROR] LLM analysis failed — see server logs\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
