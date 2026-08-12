# Rate Limiting Design

Two complementary rate-limiting mechanisms protect the ingestor. They serve
different layers of the stack and are not redundant.

## Mechanisms

### Edge limiter (slowapi)

- **File**: `services/ingestor/rate_limiting.py`
- **Scope**: `/health`, `/version` endpoints only
- **Key function**: `get_user_or_ip_address(request)` — extracts `sub` from JWT
  (without signature verification), session cookie, or client IP
- **Storage**: in-memory (default) or Redis when `CACHE_ENABLED=true`
- **Why here**: These endpoints are unauthenticated or lightly authenticated and
  are the most likely abuse targets (scraping, enumeration). slowapi's decorator
  model keeps the limiter close to the route without adding a dependency.

**Tradeoff**: The JWT decode at line 18 uses `verify_signature=False` to extract
the subject without knowing which key to use. This is acceptable because
rate-limiting does not require authentication — it only needs a stable key. The
limiter never makes an auth decision based on the decoded payload.

### Authenticated token bucket

- **File**: `services/ingestor/rate_limiting_token_bucket.py`
- **Scope**: All v1 non-auth routers (applied via `enforce_v1_token_bucket`
  dependency in `main.py`)
- **Key function**: `tenant:{tenant_id}:subject:{sub}` — per-tenant, per-user
  bucket
- **Storage**: Redis Lua script for atomic consume; local `TokenBucketLimiter`
  fallback when `CACHE_ENABLED=false`
- **Why here**: Authenticated routes need distributed enforcement because the
  ingestor may run multiple replicas behind a load balancer. A Redis-backed
  token bucket gives a shared rate-limit state across replicas.

**Constants** (from `services/ingestor/constants.py`):

- `V1_TOKEN_BUCKET_CAPACITY` — max tokens per key
- `V1_TOKEN_BUCKET_REFILL_PER_SEC` — refill rate

## Why not consolidate?

Both mechanisms exist because they solve different problems:

| Criterion | slowapi | Token bucket |
| --- | --- | --- |
| Authenticated? | No (JWT decode is best-effort) | Yes (requires valid JWT) |
| Distributed? | Optional (Redis storage) | Yes (Redis Lua script) |
| Endpoint scope | `/health`, `/version` | All v1 non-auth routes |
| Key granularity | user / session / IP | tenant + subject |
| Response headers | `Retry-After` | `X-RateLimit-*` + `Retry-After` |
| Failure mode | In-memory fallback | 503 if Redis unavailable |

Consolidating to one mechanism would require either:

- Downgrading authenticated routes to IP-based slowapi (loses tenant isolation), or
- Upgrading `/health` to JWT-dependent token bucket (breaks unauthenticated monitoring).

The current split preserves the correct security and operational properties for
each layer.

## Response headers

Authenticated routes return:

```http
X-RateLimit-Strategy: token-bucket
X-RateLimit-Limit: <capacity>
X-RateLimit-Remaining: <tokens>
Retry-After: <seconds>  (only on 429)
```

Edge-limited `/health` and `/version` return slowapi's default headers.

## Configuration

Rate limiting is always on. There is no feature flag to disable it. The token
bucket falls back to an in-memory limiter when Redis is unavailable, so rate
limiting never blocks application startup.
