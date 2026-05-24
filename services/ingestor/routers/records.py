"""Records resource — all CRUD routes."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

import services.ingestor.vector_search as vs_bridge
from services.ingestor import cache, events
from services.ingestor.api_schemas.records import (
    BatchCreateResponse,
    BatchRecordsRequest,
    PaginationMeta,
    RecordClassification,
    RecordListResponse,
    RecordRequest,
    RecordResponse,
    SessionResponse,
    UpdateRecordRequest,
)
from services.ingestor.auth import (
    DEFAULT_ROLE,
    create_session,
    session_role_guard,
    verify_bearer_token,
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
    records_created_total,
)
from services.ingestor.rate_limiting import limiter
from services.ingestor.repositories.records import (
    create_record as create_record_op,
)
from services.ingestor.repositories.records import (
    create_records_batch as create_records_batch_op,
)
from services.ingestor.repositories.records import (
    create_records_batch_naive as create_records_batch_naive_op,
)
from services.ingestor.repositories.records import (
    delete_record as delete_record_op,
)
from services.ingestor.repositories.records import (
    get_record as get_record_op,
)
from services.ingestor.repositories.records import (
    get_records,
    mark_processed,
    soft_delete_record,
    update_record,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/records", tags=["records"])

_R404 = {
    404: {
        "description": "Record not found.",
        "content": {"application/json": {"example": {"detail": "Record not found"}}},
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


# ---------------------------------------------------------------------------
# Records — single create
# ---------------------------------------------------------------------------
@router.post(
    "",
    summary="Create a record",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R422, **_R429},
)
@limiter.limit(V1_RATE_LIMIT)
async def create_record(
    request: Request,
    body: RecordRequest,
    db: DbDep,
) -> RecordResponse:
    """Create a single record.

    Logs are automatically tagged with correlation ID.
    Rate limit: 1000/minute per IP.
    """
    record = await create_record_op(db, body)
    records_created_total.labels(endpoint="single").inc()
    # Publish event after successful DB write (Observer pattern — fail-open)
    await events.publish_record_created(
        record_id=record.id,
        payload={"source": record.source},
    )
    return RecordResponse.model_validate(record)


# ---------------------------------------------------------------------------
@router.post(
    "/batch",
    summary="Batch-create records",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R422},
    description=(
        "Bulk-create records.\n\n"
        "**`?impl` query parameter** — internal implementation toggle:\n"
        "- `optimized` *(default)* — single `INSERT … RETURNING` round-trip\n"
        "- `naive` — `add_all` + N individual `REFRESH` calls (N+1 queries)\n\n"
        "Both return identical JSON. The difference is only observable as latency "
        "(use `?impl=naive` vs `?impl=optimized` with a large batch to feel it).\n\n"
        "This pattern — same contract, swappable internals — mirrors how "
        "feature flags and A/B performance experiments work in production."
    ),
)
async def create_records_batch(
    body: BatchRecordsRequest,
    db: DbDep,
    impl: str = Query(
        default="optimized",
        pattern="^(optimized|naive)$",
        description="Batch insert implementation: 'optimized' (INSERT RETURNING) or 'naive' (add_all + N refreshes).",  # noqa: E501
    ),
) -> BatchCreateResponse:
    """Create multiple records in batch.

    The `?impl=` parameter selects the internal database strategy without
    changing the response contract — identical JSON either way.
    """
    impl_fn = (
        create_records_batch_op
        if impl == "optimized"
        else create_records_batch_naive_op
    )
    logger.info("batch_create", extra={"count": len(body.records), "impl": impl})
    records = await impl_fn(db, body.records)
    batch_size_histogram.observe(len(records))
    records_created_total.labels(endpoint="batch").inc(len(records))
    logger.info("batch_created", extra={"count": len(records), "impl": impl})
    return BatchCreateResponse(created=len(records), impl=impl)


# ---------------------------------------------------------------------------
# Records — list with pagination
# ---------------------------------------------------------------------------
@router.get(
    "",
    summary="List records",
    response_model=RecordListResponse,
    responses={**_R422},
)
async def list_records(
    db: DbDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    source: str | None = None,
) -> RecordListResponse:
    """List records with pagination and optional filtering by source."""
    records, total = await get_records(db, skip, limit, source)
    return RecordListResponse(
        records=[RecordResponse.model_validate(r) for r in records],
        pagination=PaginationMeta(
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + limit) < total,
        ),
    )


# ---------------------------------------------------------------------------
# Records — get by ID
# ---------------------------------------------------------------------------
@router.get(
    "/{record_id}",
    summary="Get a record by ID",
    response_model=RecordResponse,
    responses={**_R404},
)
async def get_record(record_id: int, db: DbDep) -> RecordResponse:
    """Retrieve a single record by ID.

    Check cache first (Redis); on miss, fetch from DB and cache for 1 hour.
    Redis connection errors are transparent (fail-open).
    """
    # Try cache first
    cached_record = await cache.get_record(record_id)
    if cached_record is not None:
        cache_hits_total.labels(operation="get").inc()
        return cached_record

    # Cache miss: fetch from DB
    record = await get_record_op(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )

    # Store in cache for future hits
    response = RecordResponse.model_validate(record)
    await cache.set_record(record_id, response)
    cache_misses_total.labels(operation="get").inc()
    return response


# ---------------------------------------------------------------------------
# Records — update by ID (partial)
# ---------------------------------------------------------------------------
@router.patch(
    "/{record_id}",
    summary="Partially update a record",
    response_model=RecordResponse,
    responses={**_R404, **_R422},
)
async def update_record_endpoint(
    record_id: int, body: UpdateRecordRequest, db: DbDep
) -> RecordResponse:
    """Update a record with provided fields (partial update).

    All fields are optional. Only provided fields are updated; others are
    left unchanged.

    Example (update source and tags):
    ```json
    {"source": "new-source", "tags": ["updated", "tags"]}
    ```
    """
    record = await update_record(db, record_id, body)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    return RecordResponse.model_validate(record)


# ---------------------------------------------------------------------------
# Records — mark as processed
# ---------------------------------------------------------------------------
@router.patch(
    "/{record_id}/process",
    summary="Mark a record as processed",
    response_model=RecordResponse,
    responses={**_R404},
)
async def process_record(record_id: int, db: DbDep) -> RecordResponse:
    """Mark a record as processed.

    Invalidates any cached version so next GET reflects updated state.
    """
    record = await mark_processed(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    # Invalidate cache so next read gets fresh data
    await cache.invalidate_record(record_id)
    return RecordResponse.model_validate(record)


# ---------------------------------------------------------------------------
# Records — soft-delete (archive)
# ---------------------------------------------------------------------------
@router.patch(
    "/{record_id}/archive",
    summary="Archive (soft-delete) a record",
    response_model=RecordResponse,
    responses={**_R404},
)
async def archive_record(record_id: int, db: DbDep) -> RecordResponse:
    """Soft-delete (archive) a record.

    Logs are automatically tagged with request correlation ID (cid).
    """
    logger.info("record_archive", extra={"id": record_id})
    record = await soft_delete_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found or already archived",
        )
    logger.info("record_archived", extra={"id": record_id})
    return RecordResponse.model_validate(record)


# ---------------------------------------------------------------------------
# Records — delete
# ---------------------------------------------------------------------------
@router.delete(
    "/{record_id}",
    summary="Hard-delete a record",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_R404},
)
async def delete_record(record_id: int, db: DbDep) -> None:
    """Hard-delete a record.

    Invalidates any cached version.
    Logs are automatically tagged with request correlation ID (cid).
    """
    logger.info("record_delete", extra={"id": record_id})
    record = await delete_record_op(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    # Invalidate cache since record no longer exists
    await cache.invalidate_record(record_id)
    logger.info("record_deleted", extra={"id": record_id})


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
    "/{record_id}/secure",
    summary="Get record with session auth",
    response_model=RecordResponse,
    responses={**_R401, **_R404},
)
async def get_record_secured(
    record_id: int,
    db: DbDep,
    session: SessionDep,
) -> RecordResponse:
    """Get record with session-based auth (learning example).

    Requires valid session cookie. Try:
    1. POST /api/v1/records/auth/login?user_id=testuser
    2. GET /api/v1/records/1/secure (with cookie from step 1)

    Production: Use JWT or centralized session store (Redis).
    """
    logger.info(
        "get_record_secured",
        extra={"record_id": record_id, "user_id": session.get("user_id")},
    )
    record = await get_record_op(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    return RecordResponse.model_validate(record)


@router.patch(
    "/{record_id}/secure/archive",
    summary="Archive record with session RBAC (writer/admin)",
    response_model=RecordResponse,
    responses={**_R401, **_R403, **_R404},
)
async def archive_record_secured(
    record_id: int,
    db: DbDep,
    session: WriterSessionDep,
) -> RecordResponse:
    """Archive a record with session RBAC (writer/admin)."""
    logger.info(
        "record_archive_secure",
        extra={"id": record_id, "user_id": session.get("user_id")},
    )
    record = await soft_delete_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found or already archived",
        )
    return RecordResponse.model_validate(record)


@router.delete(
    "/{record_id}/secure/delete",
    summary="Hard-delete record with session RBAC (admin only)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_R401, **_R403, **_R404},
)
async def delete_record_secured(
    record_id: int,
    db: DbDep,
    session: AdminSessionDep,
) -> None:
    """Hard-delete a record with session RBAC (admin-only)."""
    logger.info(
        "record_delete_secure",
        extra={"id": record_id, "user_id": session.get("user_id")},
    )
    record = await delete_record_op(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    await cache.invalidate_record(record_id)


@router.post(
    "/batch/protected",
    summary="Batch-create records with bearer token auth",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R401, **_R422},
)
async def create_records_batch_protected(
    body: BatchRecordsRequest,
    db: DbDep,
    token: BearerTokenDep,
) -> BatchCreateResponse:
    """Batch create with bearer token auth (learning example).

    Requires: Authorization: Bearer <token>
    Set API_V1_BEARER_TOKEN in .env, then:

    curl -X POST http://localhost:8000/api/v1/records/batch/protected \\
      -H "Authorization: Bearer dev-secret-bearer-token" \\
      -H "Content-Type: application/json" \\
      -d '{"records": [...]}'

    Production: Use API key rotation, rate limiting per key, audit logs.
    """
    logger.info(
        "batch_protected_create",
        extra={"count": len(body.records), "token_prefix": token[:10]},
    )
    records = await create_records_batch_op(db, body.records)
    logger.info("batch_protected_created", extra={"count": len(records)})
    return BatchCreateResponse(created=len(records), impl="optimized")


# ============================================================================
# LLM Integration (Phase 2)
# ============================================================================


@router.post(
    "/{record_id}/analyze",
    summary="Analyze a record with AI (RAG + OpenAI)",
    response_model=RecordClassification,
    responses={**_R404},
)
async def analyze_record(
    record_id: int,
    db: DbDep,
) -> RecordClassification | None:
    """Analyze a record using OpenAI and RAG context.

    1. Fetches record from DB.
    2. Retrieves context from vector search.
    3. Calls OpenAI with structured output (RecordClassification).
    4. Logs prompt token usage to Prometheus.
    """
    record = await get_record_op(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )

    if not settings.openai_enabled or not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="LLM analysis is disabled or OPENAI_API_KEY is missing",
        )

    # RAG: Search for similar records to provide context
    query_text = f"Source: {record.source}, Data: {json.dumps(record.raw_data)}"
    try:
        context_results = await vs_bridge.search_record_documents(
            query=query_text,
            top_k=3,
        )
        context_docs = [r.get("text", "") for r in context_results.get("results", [])]
        context_text = "\n---\n".join(context_docs)
    except Exception as exc:
        logger.warning("rag_context_failed", extra={"error": str(exc)})
        context_text = "No additional context available."

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Build augmented prompt
    system_prompt = (
        "You are a senior data analyst. Analyze the following record. "
        "Use the provided context from similar records if relevant. "
        "Return the analysis as a structured JSON object matching the requested schema."
    )
    user_prompt = (
        f"Context from similar records:\n{context_text}\n\n"
        f"Record to analyze:\n"
        f"Source: {record.source}\n"
        f"Timestamp: {record.timestamp}\n"
        f"Data: {json.dumps(record.raw_data)}\n"
        f"Tags: {', '.join(record.tags)}"
    )

    try:
        # Using beta.chat.completions.parse for Pydantic structured output
        completion = await client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=RecordClassification,
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


@router.post("/{record_id}/analyze/stream")
async def analyze_record_stream(
    record_id: int,
    db: DbDep,
) -> StreamingResponse:
    """Stream record analysis from OpenAI (Server-Sent Events)."""
    record = await get_record_op(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )

    if not settings.openai_enabled or not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="LLM analysis is disabled or OPENAI_API_KEY is missing",
        )

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
                        "content": "Analyze this record and provide insights.",
                    },
                    {
                        "role": "user",
                        "content": f"Source: {record.source}, Data: {json.dumps(record.raw_data)}",
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
            yield f"data: [ERROR] {exc}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
