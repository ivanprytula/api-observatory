"""Observations v2 — advanced rate-limiting showcase.

This module exists as a side-by-side comparison with v1 (*the "before"*).

  v1  POST /api/v1/observations           — token bucket (production policy)
  v2  POST /api/v2/observations/fixed-window   — fixed-window comparison
  v2  POST /api/v2/observations/token-bucket   — in-memory token-bucket comparison
  v2  POST /api/v2/observations/sliding-window — exact sliding window

  The business logic (creating a observation) is identical in every route.  Only the
rate-limiting strategy or auth mechanism changes.  This makes the algorithmic
difference the *only* variable, useful for demos, benchmarks, and architecture discussions.

Observable difference
---------------------
Every v2 response carries these headers so clients (and interviewers) can
*see* the limiter state in real time:

  X-RateLimit-Limit     — configured maximum
  X-RateLimit-Remaining — requests still allowed in the current window/bucket
  X-RateLimit-Retry-After — seconds to wait on 429 (omitted when allowed)
  X-RateLimit-Strategy  — "token-bucket" or "sliding-window"

Try it with httpie:
    # Fire 15 rapid requests and watch the headers change
    for i in $(seq 1 15); do
        http POST :8000/api/v2/observations/token-bucket source=demo \\
             timestamp=2024-01-15T10:00:00 data:='{"v":1}' tags:='[]'
    done
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from services.ingestor.api_schemas.observations import (
    CursorPaginationResponse,
    EnrichRequest,
    EnrichResponse,
    ObservationRequest,
    ObservationResponse,
    UpsertRequest,
    UpsertResponse,
)
from services.ingestor.constants import (
    API_V2_PREFIX,
    ENRICH_SEMAPHORE_LIMIT,
    JITTER_MAX_SECONDS,
    JITTER_MIN_SECONDS,
    SLIDING_WINDOW_LIMIT,
    SLIDING_WINDOW_SECONDS,
    TOKEN_BUCKET_CAPACITY,
    TOKEN_BUCKET_REFILL_PER_SEC,
    UPSERT_MODE_IDEMPOTENT,
    UPSERT_MODE_STRICT,
    V1_RATE_LIMIT,
)
from services.ingestor.core.database import get_db
from services.ingestor.metrics import (
    enrich_duration_seconds,
    observations_created_total,
    observations_upsert_conflicts_total,
)
from services.ingestor.rate_limiting import limiter
from services.ingestor.rate_limiting_advanced import (
    SlidingWindowLimiter,
    TokenBucketLimiter,
)
from services.ingestor.repositories.observations import (
    create_observation,
    enrich_observations_concurrent,
    get_observations_cursor_paginated,
    get_observations_with_tag_counts,
    get_observations_with_tag_counts_naive,
    upsert_observation,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=f"{API_V2_PREFIX}/observations",
    tags=["observations-v2 — advanced rate limiting"],
)

_R404 = {
    404: {
        "description": "Observation not found.",
        "content": {
            "application/json": {"example": {"detail": "Observation not found"}}
        },
    }
}
_R409 = {
    409: {
        "description": "Conflict - a observation with the same (source, ts) key already exists.",
        "content": {
            "application/json": {
                "example": {
                    "detail": {
                        "error": "conflict",
                        "message": (
                            "A observation with source='sensor-1' and "
                            "timestamp=2024-01-15T10:00:00 already exists."
                        ),
                        "existing_id": 42,
                    }
                }
            }
        },
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

# ---------------------------------------------------------------------------
# Shared limiter instances — module-level singletons (per-process, in-memory).
# In production: construct once in lifespan() and inject via app.state or DI.
# ---------------------------------------------------------------------------

# Token bucket: burst up to TOKEN_BUCKET_CAPACITY, refill at TOKEN_BUCKET_REFILL_PER_SEC
# Great for: mobile apps, clients that batch requests occasionally
_token_bucket = TokenBucketLimiter(
    capacity=TOKEN_BUCKET_CAPACITY,
    refill_per_second=TOKEN_BUCKET_REFILL_PER_SEC,
)

# Sliding window: hard limit of SLIDING_WINDOW_LIMIT requests per SLIDING_WINDOW_SECONDS
# Great for: APIs where you need a *guaranteed* max rate, no burst exceptions
_sliding_window = SlidingWindowLimiter(
    limit=SLIDING_WINDOW_LIMIT,
    window_seconds=SLIDING_WINDOW_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Extract the best available client IP for rate-limit keying."""
    # Respect reverse-proxy headers first (edge, ALB, Cloudflare)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rl_headers(strategy: str, limit: int, remaining: float | int) -> dict[str, str]:
    """Build the standard rate-limit response headers."""
    return {
        "X-RateLimit-Strategy": strategy,
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(int(remaining)),
    }


# ---------------------------------------------------------------------------
# Fixed-window endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/fixed-window",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create observation — fixed-window rate limit",
    responses={**_R422, **_R429},
)
@limiter.limit(V1_RATE_LIMIT)
async def create_observation_fixed_window(
    request: Request,
    body: ObservationRequest,
    db: DbDep,
) -> ObservationResponse:
    """Preserve the former v1 fixed-window policy as a learning comparison."""
    observation = await create_observation(db, body)
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
# Token-bucket endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/token-bucket",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create observation — token bucket rate limit",
    responses={**_R422, **_R429},
    description=(
        "Identical to `POST /api/v1/observations` but protected by a **token bucket**.\n\n"
        "**Algorithm**: each client IP owns a bucket of up to 20 tokens.  "
        "Tokens refill at 10/min (≈1 every 6 seconds).  Bursting is allowed "
        "until the bucket drains; after that requests are throttled at the refill "
        "rate.\n\n"
        "**v1 vs v2 difference**: v1 uses a *fixed window* (counter resets every "
        "minute, enabling a 2× burst at window boundaries).  Token bucket smooths "
        "that out.\n\n"
        "**Response headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, "
        "`X-RateLimit-Strategy`, `Retry-After` (on 429 only)."
    ),
)
async def create_observation_token_bucket(
    request: Request,
    body: ObservationRequest,
    db: DbDep,
    response: Response,
) -> ObservationResponse:
    """Create a observation — rate-limited via token bucket."""
    ip = _client_ip(request)
    allowed, remaining = await _token_bucket.consume(ip)

    if not allowed:
        retry_after = _token_bucket.seconds_until_token(
            ip, min_jitter=-JITTER_MIN_SECONDS, max_jitter=JITTER_MAX_SECONDS
        )
        logger.warning(
            "rate_limit_token_bucket",
            extra={"ip": ip, "retry_after": retry_after},
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded (token bucket drained)",
            headers={
                **_rl_headers("token-bucket", _token_bucket.capacity, remaining),
                "Retry-After": str(int(retry_after) + 1),
            },
        )

    response.headers.update(
        _rl_headers("token-bucket", _token_bucket.capacity, remaining)
    )
    observation = await create_observation(db, body)
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
# Sliding-window endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/sliding-window",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create observation — sliding window rate limit",
    responses={**_R422, **_R429},
    description=(
        "Identical to `POST /api/v1/observations` but protected by a **sliding "
        "(rolling) window**.\n\n"
        "**Algorithm**: tracks the exact timestamps of the last N requests.  "
        "On each request the window `[now - 60 s, now]` is evaluated.  At most "
        "10 requests are allowed in any 60-second span, regardless of where the "
        "clock sits within a minute.\n\n"
        "**Fixed-window vulnerability this fixes**: a client can send 10 requests "
        "at 00:59 and 10 more at 01:01 — all 20 pass a fixed-window limiter.  "
        "Sliding window blocks the second batch because the first 10 are still in "
        "scope at 01:01.\n\n"
        "**Response headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, "
        "`X-RateLimit-Strategy`, `Retry-After` (on 429 only)."
    ),
)
async def create_observation_sliding_window(
    request: Request,
    body: ObservationRequest,
    db: DbDep,
    response: Response,
) -> ObservationResponse:
    """Create a observation — rate-limited via sliding window."""
    ip = _client_ip(request)
    allowed, remaining = await _sliding_window.is_allowed(ip)

    if not allowed:
        retry_after = _sliding_window.reset_in(
            ip, min_jitter=-JITTER_MIN_SECONDS, max_jitter=JITTER_MAX_SECONDS
        )
        logger.warning(
            "rate_limit_sliding_window",
            extra={"ip": ip, "retry_after": retry_after},
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded (sliding window full)",
            headers={
                **_rl_headers("sliding-window", _sliding_window.limit, remaining),
                "Retry-After": str(int(retry_after) + 1),
            },
        )

    response.headers.update(
        _rl_headers("sliding-window", _sliding_window.limit, remaining)
    )
    observation = await create_observation(db, body)
    return ObservationResponse.model_validate(observation)


# ---------------------------------------------------------------------------
# JWT authentication endpoint
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# N+1 Query Problem Demo
# ---------------------------------------------------------------------------


@router.get(
    "/n-plus-one-demo",
    status_code=status.HTTP_200_OK,
    summary="Demonstrate the N+1 query problem",
    responses={},
    description=(
        "Side-by-side comparison of naive (N+1) vs optimized (1 query) approaches "
        "to fetch observations with related data.\n\n"
        "**What is the N+1 problem?**\n"
        "When fetching 10 observations with tag counts:\n"
        "- **Naive**: 1 query to fetch observations + 10 queries to count tags per observation "
        "= **11 total queries**\n"
        "- **Optimized**: 1 query with `array_length(tags, 1)` computed server-side "
        "= **1 total query**\n\n"
        "**Response**:\n"
        "```json\n"
        "{\n"
        '  "naive_ms": 45.2,\n'
        '  "optimized_ms": 12.1,\n'
        '  "speedup": 3.73,\n'
        '  "observations_count": 10,\n'
        '  "limit": 10\n'
        "}\n"
        "```\n\n"
        "**Learning takeaways**:\n"
        "1. Aggregate queries server-side (use `array_length`, `count`, etc.) not in loops\n"
        "2. Measure before optimizing (the speedup magnitude depends on query cost)\n"
        "3. Query *shape* matters more than caching (50x speedup is not uncommon)\n\n"
        "**Try it**:\n"
        "```bash\n"
        "http GET :8000/api/v2/observations/n-plus-one-demo limit==50\n"
        "```"
    ),
)
async def demo_n_plus_one(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, float | int]:
    """Demonstrate N+1 query problem with timing comparison.

    Runs both naive and optimized approaches, measures their execution time,
    and returns the speedup ratio. This is a teaching endpoint designed for
    interviews and code reviews.

    Args:
        db: Async database session (injected).
        limit: Number of observations to fetch (1-100, default 10).

    Returns:
        Dict with keys: naive_ms, optimized_ms, speedup, observations_count, limit.
    """
    # Time the naive approach (N+1 queries)
    start_naive = time.perf_counter()
    naive_results = await get_observations_with_tag_counts_naive(db, limit=limit)
    time_naive = (time.perf_counter() - start_naive) * 1000  # Convert to ms

    # Time the optimized approach (1 query)
    start_opt = time.perf_counter()
    _ = await get_observations_with_tag_counts(db, limit=limit)
    time_opt = (time.perf_counter() - start_opt) * 1000  # Convert to ms

    speedup = time_naive / time_opt if time_opt > 0 else 1.0

    logger.info(
        "n_plus_one_demo",
        extra={
            "limit": limit,
            "naive_ms": round(time_naive, 2),
            "optimized_ms": round(time_opt, 2),
            "speedup": round(speedup, 2),
        },
    )

    return {
        "naive_ms": round(time_naive, 2),
        "optimized_ms": round(time_opt, 2),
        "speedup": round(speedup, 2),
        "observations_count": len(naive_results),
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# GET /api/v2/observations/cursor — cursor-based pagination (high-load)
# ---------------------------------------------------------------------------


@router.get(
    "/cursor",
    response_model=CursorPaginationResponse,
    status_code=status.HTTP_200_OK,
    summary="List observations with cursor-based pagination",
    responses={**_R422},
    description=(
        "Fetches observations using **cursor-based pagination** (ideal for high-load).\n\n"
        "**Advantages over offset/limit**:\n"
        "- No offset (avoids full table scan for deep pages)\n"
        "- Stable under concurrent inserts (offset doesn't shift)\n"
        "- Cache-friendly (cursor ties to a specific observation)\n\n"
        "**How it works**:\n"
        "1. First request: `GET /api/v2/observations/cursor?limit=50`\n"
        "2. Response includes `next_cursor` and `has_more`\n"
        "3. Next request: `GET /api/v2/observations/cursor?cursor=<next_cursor>&limit=50`\n"
        "4. Repeat until `has_more=false`\n\n"
        '**Cursor format**: Opaque base64-encoded JSON `{"id": ..., "timestamp": ...}`\n\n'
        "**Try it**:\n"
        "```bash\n"
        "# First page\n"
        "http GET :8000/api/v2/observations/cursor limit==10\n\n"
        "# Next page (copy next_cursor from response)\n"
        "http GET :8000/api/v2/observations/cursor cursor==<value> limit==10\n"
        "```"
    ),
)
async def list_observations_cursor(
    db: DbDep,
    cursor: Annotated[
        str | None, Query(description="Opaque cursor for pagination")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    source: Annotated[str | None, Query(description="Optional source filter")] = None,
) -> CursorPaginationResponse:
    """List observations using cursor-based pagination (stable under concurrent inserts).

    Args:
        db: Async database session (injected).
        cursor: Opaque cursor from the previous response (None for first page).
        limit: Number of observations per page (1–100, default 50).
        source: Optional source filter.

    Returns:
        CursorPaginationResponse with observations, next_cursor, and has_more flag.
    """
    observations, next_cursor, has_more = await get_observations_cursor_paginated(
        session=db,
        cursor=cursor,
        limit=limit,
        source=source,
    )
    return CursorPaginationResponse(
        observations=[ObservationResponse.model_validate(r) for r in observations],
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


@router.post(
    "/enrich",
    response_model=EnrichResponse,
    status_code=status.HTTP_200_OK,
    summary="Enrich observations with external API data concurrently",
    responses={**_R422},
    description=(
        "Fetches external metadata for up to 50 observations concurrently using "
        "`asyncio.gather` + `asyncio.Semaphore` to cap outbound HTTP to "
        f"{ENRICH_SEMAPHORE_LIMIT} concurrent calls.\n\n"
        "**Pattern demonstrated**: Semaphore-limited fan-out\n\n"
        "```\n"
        "POST /api/v2/observations/enrich\n"
        '{"observation_ids": [1, 2, 3, 4, 5]}\n'
        "```\n\n"
        "Each observation is enriched by fetching a matching post from "
        "`jsonplaceholder.typicode.com`. Failed enrichments are included in the "
        "response with `enriched: false` and an error message — partial failures "
        "**do not** fail the entire request.\n\n"
        "**Why semaphore**: Without it, 50 requests fire simultaneously. "
        f"Semaphore({ENRICH_SEMAPHORE_LIMIT}) ensures at most {ENRICH_SEMAPHORE_LIMIT} "
        "are in-flight at once, protecting the external API and the DB connection pool.\n\n"
        "**Try it**:\n"
        "```bash\n"
        "http POST :8000/api/v2/observations/enrich observation_ids:='[1,2,3]'\n"
        "```"
    ),
)
async def enrich_observations(
    payload: EnrichRequest,
    db: DbDep,
) -> EnrichResponse:
    """Concurrently enrich a batch of observations with external API metadata.

    Uses asyncio.Semaphore to prevent thundering herd against external API.
    Partial failures are tolerated — failed observations appear in results with
    enriched=False; the endpoint always returns 200 unless all observations fail.

    Args:
        payload: EnrichRequest with list of observation_ids (1–50).
        db: Async database session (injected).

    Returns:
        EnrichResponse with per-observation results, counts, and wall-clock duration.
    """
    start = time.perf_counter()
    semaphore = asyncio.Semaphore(ENRICH_SEMAPHORE_LIMIT)

    results = await enrich_observations_concurrent(
        session=db,
        observation_ids=payload.observation_ids,
        semaphore=semaphore,
    )

    duration_ms = (time.perf_counter() - start) * 1000
    enriched_count = sum(1 for r in results if r.enriched)
    failed_count = len(results) - enriched_count

    enrich_duration_seconds.observe(duration_ms / 1000)

    logger.info(
        "enrich_complete",
        extra={
            "total": len(results),
            "enriched": enriched_count,
            "failed": failed_count,
            "duration_ms": round(duration_ms, 2),
        },
    )

    return EnrichResponse(
        enriched_count=enriched_count,
        failed_count=failed_count,
        duration_ms=round(duration_ms, 2),
        results=results,
    )


# ---------------------------------------------------------------------------
# POST /api/v2/observations/upsert — idempotent upsert + race condition demo (Step 9)
# ---------------------------------------------------------------------------
@router.post(
    "/upsert",
    response_model=UpsertResponse,
    summary="Idempotent upsert — insert or return existing observation",
    responses={**_R409, **_R422},
    description=(
        "Insert a observation using `(source, timestamp)` as the idempotency key.\n\n"
        "A second call with the **same source + timestamp** pair returns the "
        "existing observation instead of inserting a duplicate.\n\n"
        "**Conflict resolution modes** (via `?mode=` query param):\n\n"
        "| mode | first call | duplicate call |\n"
        "|------|-----------|----------------|\n"
        "| `idempotent` (default) | 201 Created | 200 OK — same observation, `created: false` |\n"
        "| `strict` | 201 Created | 409 Conflict — explicit error |\n\n"
        "**Pattern demonstrated**: optimistic INSERT → catch `IntegrityError` → "
        "SELECT existing\n\n"
        "Why not SELECT-then-INSERT? That pattern has a TOCTOU race: two concurrent "
        "requests can both see no row, both attempt INSERT, and one fails with an "
        "unhandled error. Catching `IntegrityError` atomically handles the race.\n\n"
        "**Race condition demo**:\n"
        "```bash\n"
        "# Fire two concurrent upserts with the same key:\n"
        "for i in 1 2; do\n"
        "  http POST :8000/api/v2/observations/upsert \\\n"
        "    source=sensor-1 timestamp=2024-01-15T10:00:00 data:='{}' &\n"
        "done\n"
        "# One returns 201 (created: true), one returns 200 (created: false)\n"
        "```\n\n"
        "**Response fields**:\n"
        "- `observation`: the observation (new or existing)\n"
        "- `created`: `true` if inserted, `false` if conflict resolved\n"
        "- `mode`: the mode used"
    ),
)
async def upsert_observation_endpoint(
    payload: UpsertRequest,
    db: DbDep,
    mode: Annotated[
        str,
        Query(
            description="Conflict mode: 'idempotent'(200 on conflict) or 'strict'(409 on conflict)",
            pattern=f"^({UPSERT_MODE_IDEMPOTENT}|{UPSERT_MODE_STRICT})$",
        ),
    ] = UPSERT_MODE_IDEMPOTENT,
) -> Response:
    """Insert or return existing observation by (source, timestamp) key.

    Handles the race condition atomically: optimistic INSERT, catch IntegrityError,
    rollback, SELECT existing. Both concurrent requests receive a valid response.

    Args:
        payload: UpsertRequest with source, timestamp, data, tags.
        db: Async database session (injected).
        mode: "idempotent" (default) or "strict" conflict resolution.

    Returns:
        UpsertResponse with the observation, created flag, and mode used.

    Raises:
        HTTPException 409: Only in strict mode when a conflict is detected.
    """
    from fastapi import HTTPException

    observation, created = await upsert_observation(session=db, request=payload)

    if not created and mode == UPSERT_MODE_STRICT:
        logger.warning(
            "upsert_strict_conflict",
            extra={"source": payload.source, "timestamp": str(payload.timestamp)},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "message": (
                    f"A observation with source={payload.source!r} and "
                    f"timestamp={payload.timestamp} already exists."
                ),
                "existing_id": observation.id if observation else None,
            },
        )

    http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    if created:
        observations_created_total.labels(endpoint="upsert").inc()
    else:
        observations_upsert_conflicts_total.labels(mode=mode).inc()
    logger.info(
        "upsert_complete",
        extra={
            "was_created": created,
            "mode": mode,
            "observation_id": observation.id if observation else None,
        },
    )

    # FastAPI route return; status_code is set dynamically via Response injection
    # Since we can't easily return dynamic status codes from response_model routes,
    # we use a JSONResponse directly to set 201 vs 200.
    from fastapi.encoders import jsonable_encoder

    response_body = UpsertResponse(
        observation=ObservationResponse.model_validate(observation),
        created=created,
        mode=mode,
    )
    return JSONResponse(  # type: ignore[return-value]
        status_code=http_status,
        content=jsonable_encoder(response_body),
    )
