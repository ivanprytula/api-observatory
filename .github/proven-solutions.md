# Proven Solutions & SSRF Prevention

## Proven Solutions (project-level defaults)

Default to these when writing or reviewing code. Do not suggest custom alternatives unless the listed solution is genuinely insufficient.

| Need | Use |
|------|-----|
| HTTP client | `httpx.AsyncClient` |
| Config/settings | `pydantic-settings BaseSettings` |
| URL validation | `pydantic.AnyHttpUrl` |
| Password hashing | `passlib[bcrypt]` |
| JWT | `python-jose` or `PyJWT` |
| Structured logging | `structlog` |
| HTTP metrics | `prometheus-fastapi-instrumentator` |
| OTEL traces | `opentelemetry-instrumentation-fastapi` auto-instrumentation |
| Rate limiting | `slowapi` |
| Job scheduling | `apscheduler>=3.10,<4.0` `AsyncScheduler` |
| SHA-256 | `hashlib.sha256` (stdlib) |
| Response time | `time.monotonic()` (stdlib) |
| DB upsert | `insert().on_conflict_do_update()` |
| Percentile stats | `PERCENTILE_CONT` in SQL, not Python |
| Redis pub/sub | `redis-py` async `PubSub` |
| SSE | `StreamingResponse(media_type="text/event-stream")` |

## SSRF Prevention (required for all user-supplied URLs)

Any URL supplied by a user that will be used in a server-side HTTP request must be validated before use:

- Scheme: `https` only (or explicitly allowed `http` per config flag)
- Resolved IP must not fall in private ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1`
- Use `ipaddress` stdlib module to check the resolved IP after DNS resolution
- This applies to: `SourceProfile.base_url`, webhook URLs, scraper targets, any other user-controlled URL
