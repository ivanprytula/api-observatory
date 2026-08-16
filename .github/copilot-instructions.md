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

## Proven Solutions & SSRF Prevention

See [`.github/proven-solutions.md`](proven-solutions.md) for project-level defaults and SSRF requirements.

## Skill Discovery

For a lightweight catalog of all available skills, see `../agent-forge/skills/manifest.json` or `../agent-forge/skills/index.md`. Load the full `SKILL.md` only when the task matches the skill's trigger.
