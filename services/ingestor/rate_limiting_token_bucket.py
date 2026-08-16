"""Production token-bucket enforcement for authenticated v1 routes."""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Response, status
from redis.exceptions import RedisError

from services.ingestor.auth import verify_jwt_token
from services.ingestor.cache import get_redis_client
from services.ingestor.config import settings
from services.ingestor.constants import (
    V1_TOKEN_BUCKET_CAPACITY,
    V1_TOKEN_BUCKET_REFILL_PER_SEC,
)
from services.ingestor.rate_limiting_advanced import TokenBucketLimiter


_TOKEN_BUCKET_LUA = """
local now = redis.call('TIME')
local now_seconds = tonumber(now[1]) + tonumber(now[2]) / 1000000
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens')) or capacity
local last = tonumber(redis.call('HGET', KEYS[1], 'last')) or now_seconds
tokens = math.min(capacity, tokens + math.max(0, now_seconds - last) * refill)
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
local retry_after = 0
if allowed == 0 then
  retry_after = math.ceil((1 - tokens) / refill)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'last', now_seconds)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return {allowed, tokens, retry_after}
"""

_local_bucket = TokenBucketLimiter(
    capacity=V1_TOKEN_BUCKET_CAPACITY,
    refill_per_second=V1_TOKEN_BUCKET_REFILL_PER_SEC,
)


def _rate_limit_headers(
    remaining: float, retry_after: int | None = None
) -> dict[str, str]:
    """Build response headers shared by admitted and rejected requests."""
    headers = {
        "X-RateLimit-Strategy": "token-bucket",
        "X-RateLimit-Limit": str(V1_TOKEN_BUCKET_CAPACITY),
        "X-RateLimit-Remaining": str(max(0, math.floor(remaining))),
    }
    if retry_after is not None:
        headers["Retry-After"] = str(max(1, retry_after))
    return headers


async def _consume(key: str) -> tuple[bool, float, int | None]:
    """Consume one token using Redis atomically or the local test fallback."""
    if not settings.cache_enabled:
        allowed, remaining = await _local_bucket.consume(key)
        retry_after = (
            math.ceil(_local_bucket.seconds_until_token(key)) if not allowed else None
        )
        return allowed, remaining, retry_after

    client = get_redis_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter is unavailable",
        )

    ttl_seconds = max(
        1,
        math.ceil(V1_TOKEN_BUCKET_CAPACITY / V1_TOKEN_BUCKET_REFILL_PER_SEC * 2),
    )
    try:
        allowed, remaining, retry_after = await client.eval(
            _TOKEN_BUCKET_LUA,
            1,
            f"rate-limit:v1:{key}",
            V1_TOKEN_BUCKET_CAPACITY,
            V1_TOKEN_BUCKET_REFILL_PER_SEC,
            ttl_seconds,
        )
    except RedisError:
        allowed, remaining = await _local_bucket.consume(key)
        retry_after = (
            math.ceil(_local_bucket.seconds_until_token(key)) if not allowed else None
        )
    return bool(int(allowed)), float(remaining), retry_after or None


async def enforce_v1_token_bucket(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(verify_jwt_token)],
) -> None:
    """Authenticate then apply the v1 token bucket by tenant and subject."""
    subject = str(claims.get("sub", "unknown"))
    tenant_id = claims.get("tenant_id")
    allowed, remaining, retry_after = await _consume(
        f"tenant:{tenant_id if tenant_id is not None else 'global'}:subject:{subject}"
    )
    headers = _rate_limit_headers(remaining, retry_after)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=headers,
        )
    response.headers.update(headers)


async def enforce_public_v1_token_bucket(
    request: Request,
    response: Response,
) -> None:
    """Apply the same v1 policy to public authentication bootstrap requests."""
    client_host = request.client.host if request.client is not None else "unknown"
    allowed, remaining, retry_after = await _consume(f"ip:{client_host}")
    headers = _rate_limit_headers(remaining, retry_after)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=headers,
        )
    response.headers.update(headers)
