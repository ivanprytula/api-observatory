# Tests — Architecture & Patterns

Overview: Test architecture for api-observatory uses a three-layer strategy (unit, integration, e2e) with shared fixtures and selectable database modes.

Fixture strategy:

- Layer 1 (shared): `fixtures_shared.py` — database mode selection (`aiosqlite` in-memory vs. PostgreSQL)
- Layer 2 (unit): `tests/unit/conftest.py` — unit test marker, lightweight mocks
- Layer 3 (integration): `tests/integration/conftest.py` — full app context, real database
- Custom fixtures: reusable factories in `tests/shared/factories.py`

Test hierarchy (quick):

```text
tests/
  ├─ conftest.py          # Global: database mode, asyncio_mode=auto
  ├─ fixtures_shared.py   # Database fixture selection
  ├─ unit/
  ├─ integration/
  ├─ e2e/
  └─ shared/
```

When to write each type:

- Unit: single function/method, no I/O — fast
- Integration: API routes, DB round-trips — medium
- E2E: full workflows — slow, CI-only or nightly

Fixture patterns:

- Database mode controlled by `PYTEST_DB_MODE` (default: `aiosqlite`)
- Run integration against Postgres: `PYTEST_DB_MODE=postgres pytest tests/integration/`

Coverage expectations:

- Local: `pytest tests/unit/ tests/integration/ --cov`
- CI gate: 80% coverage on modified files (unit + integration)
