# Project Guidelines — api-observatory

Async FastAPI + SQLAlchemy 2.0 services for ingesting, processing, and querying pipeline data.

> For universal agent behavior (priority, read scope, execution rules, response style, privacy, and technical conventions), read `AGENTS.md` in the repository root. This file holds only project-specific overrides and conventions.

## Project Layout

Primary backend surface:

- `services/ingestor/main.py`: FastAPI app, lifespan, router wiring, OpenAPI metadata
- `services/ingestor/auth.py`: session and JWT auth helpers
- `services/ingestor/security/`: authn/authz/security helpers
- `services/ingestor/repositories/`: async persistence helpers
- `services/ingestor/models/`: SQLAlchemy ORM models
- `services/ingestor/api_schemas/`: Pydantic request/response schemas
- `services/ingestor/database.py`: engine, sessionmaker, DB dependency
- `libs/platform/`: shared cross-service code; `libs/*` must not import from `services/*`
- `tests/` and `services/ingestor/tests/`: pytest coverage
- `alembic/`: schema migrations

## Core Conventions

### Python

- Python 3.14 style, full type hints, modern typing syntax.
- Async everywhere for I/O paths.
- Use Google-style docstrings only where they add value.
- Use `raise ... from None` when translating exceptions.

### FastAPI

- Use `Annotated[T, Depends(...)]` dependencies.
- Keep route handlers thin; move logic into security/services/repositories.
- Use `HTTPException` with precise status codes.

### SQLAlchemy

- SQLAlchemy 2.0 only: `Mapped[...]` + `mapped_column()`.
- `AsyncSession` is the first parameter in repository/CRUD helpers.
- Keep `expire_on_commit=False` on async sessions.

### Pydantic

- Separate request and response schemas.
- Response schemas use `model_config = {"from_attributes": True}` when fed from ORM objects.

### Tests

- `asyncio_mode = auto`; do not add `@pytest.mark.asyncio` unless required by a specific file pattern.
- Prefer focused tests for the slice you changed.
- For fakeredis async calls, use the existing narrow type-ignore pattern only where needed.

## Security

- Deny by default.
- Never hardcode secrets.
- Validate user-controlled input and URLs.
- Use parameterized DB access only.
- Prefer tenant-scoped checks and explicit authz inputs over ad hoc role checks.

## Migrations

- Alembic is the schema source of truth.
- Any model change that affects schema needs a migration.
- Validate upgrade/downgrade paths when touching migrations.

## Dependency and Tooling

- `uv.lock` is the reproducible source for installs.
- Do not regenerate lockfiles in CI logic.
- Use `uv sync --frozen` semantics where reproducibility matters.

## Naming and Decomposition

- One module, one reason to change.
- Extract constants instead of repeating magic values.
- Prefer small, explicit modules over large mixed-purpose files.

## Documentation Rules

Only for `.md` edits:

- Use real headings, never bold-only headings.
- Use lowercase kebab-case filenames in `docs/`.
- Add language tags to fenced code blocks.
- Keep docs concrete; prefer diagrams/tables when they genuinely clarify.

## Avoid Stale Assumptions

- Follow the current repo state, not older patterns.
- If instructions and code disagree, trust the codebase and update the touched docs or notes if needed.

## Critical Review & Anti-Overengineering

Be objective and critical about existing code. When reviewing or extending any file:

1. **Check for reinvented wheels first.** Before suggesting any custom implementation, check whether stdlib or a well-known PyPI package solves the same problem. If one exists, recommend it. Examples:
   - `hashlib` for hashing (not a custom hash class)
   - `pydantic-settings` for config (not custom env-var parsing)
   - `structlog` for structured logging (not a custom JSON formatter on `logging`)
   - `slowapi` for rate limiting (not a custom token bucket)
   - `prometheus-fastapi-instrumentator` for HTTP metrics (not manual `Counter` per route)

2. **Flag overengineering explicitly.** If an abstraction is used by fewer than 3 callers, say so and suggest inlining. If a class has more than one reason to change, say so. If a file exceeds ~300 lines, flag it for splitting.

3. **Simplest solution wins.** When multiple approaches satisfy the functional requirement, always recommend the one with fewest lines, fewest dependencies, and fewest moving parts. Complexity must be justified by a concrete, current requirement — not a future hypothetical.

4. **Probe for necessity.** Before adding a dependency, ask: can stdlib do this in < 20 lines? If yes, use stdlib.

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
