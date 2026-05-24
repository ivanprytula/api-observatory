name: async-patterns
description: "Comprehensive async Python patterns for FastAPI + SQLAlchemy apps. Covers practical patterns (batch inserts, pagination, retries, rate-limiting, background tasks, connection-pool tuning, validators) and core async concepts (coroutines, event loop, Task vs Future, cancellation, timeouts, structured concurrency). Includes step-by-step implementation guidance and testing checklist."
metadata:
  applyTo: "app/**/*.py, src/**/*.py, **/*.py"
argument-hint: "pattern: batch|pagination|retry|rate-limit|background-tasks|connection-pool|validator|structured-concurrency|timeouts"
---

# Async Patterns — Skill

Purpose: implement production-ready async patterns with concise explanations, safe implementations, and tests.

When to invoke: `async-patterns <pattern>` where `<pattern>` is one of the supported patterns in the `argument-hint` above.

Supported patterns (quick reference):

- `batch` — bulk inserts vs single inserts; `session.add_all()`, transactions, chunking for memory control.
- `pagination` — offset/limit or keyset pagination; return `items` + `has_more` and avoid N+1 queries.
- `retry` — cancellation-safe exponential backoff, idempotency considerations, when *not* to retry.
- `rate-limit` — per-route or per-user limits (slowapi/redis), 429 responses, headers for rate info.
- `background-tasks` — `BackgroundTasks` vs `create_task()` vs `TaskGroup`; lifecycle and cleanup.
- `connection-pool` — `asyncpg` pool sizing, `pool_pre_ping`, monitoring pool exhaustion and tuning.
- `validator` — Pydantic v2 `field_validator` / `model_validator` patterns and cross-field validation.
- `structured-concurrency` — use `asyncio.TaskGroup` for scoped tasks and predictable cancellation.
- `timeouts` — `asyncio.timeout()` usage and sensible deadlines for downstream calls.

Core concepts (short):

- Async is a concurrency model for I/O-bound work, not a substitute for parallelism (GIL still applies).
- Coroutines are suspended computations; `await` yields control to the event loop.
- The event loop schedules tasks; avoid blocking the loop with CPU work or blocking I/O.
- `Task` runs a coroutine; `Future` is a result placeholder. Use `TaskGroup` for structured concurrency.
- Cancellation and timeouts are control-flow primitives — always preserve `CancelledError` and clean up resources.

Procedure (practical checklist):

1. Identify pattern from the argument; if missing, prompt selection.
2. Read current files that will change: `app/crud.py`, `app/database.py`, `app/schemas.py`, `app/main.py`, and related tests.
3. Explain the pattern in 3–5 sentences: what, why, trade-offs.
4. Implement minimal, safe changes following project conventions (SQLAlchemy 2.0 mapped style; `AsyncSession` first arg; dependency aliasing). Keep changes small and testable.
5. Add/modify tests that demonstrate behavior; prefer focused unit/integration tests using existing test fixtures.
6. Run tests and fix failures. Provide a short summary: implemented change, test outcome, next steps.

Testing hints:

- Use `asyncio_mode = "auto"` (no `@pytest.mark.asyncio`).
- For DB-heavy tests that must be parallel, run against PostgreSQL (set `DATABASE_URL_TEST`).
- Measure performance when demonstrating `batch` vs single inserts (use `time.perf_counter()` in tests to compare relative improvements).

Example invocation flow (short):

1. User: `async-patterns batch`
2. Skill: explains batch benefits and trade-offs, inspects `app/crud.py` and `app/database.py`, suggests a patch.
3. Skill: applies patch, adds a test comparing single vs bulk insert, and runs `pytest -k batch`.
4. Skill: reports results and offers follow-ups (`connection-pool` tuning, monitoring metrics).

Security & Safety notes:

- Avoid introducing blocking calls in async routes; wrap CPU-bound work in a process pool if needed.
- For retries, require idempotency or use safe backoff windows; do not retry non-idempotent writes blindly.

References:

- See `async-patterns.instructions.md` for deeper explanations of coroutines, event loop, Task vs Future, structured concurrency, cancellation, and timeouts.
- Project conventions: follow `python.instructions.md`, `crud.instructions.md`, and `tests.instructions.md`.

Finish: always summarize the change, the observable test results, and one next-step suggestion.
