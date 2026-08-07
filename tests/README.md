# Tests — Architecture & Patterns

Top-level tests cover repository-level platform utilities and external-stack checks. Ingestor
application behavior belongs in `services/ingestor/tests/`.

Fixture strategy:

- Layer 1 (shared): `fixtures_shared.py` — database mode selection (`aiosqlite` in-memory vs. PostgreSQL)
- Layer 2 (platform): `tests/unit/` — shared-library, script, and lab checks
- Layer 3 (external lab): `tests/e2e/` — opt-in Compose chaos checks
- Ingestor tests: `services/ingestor/tests/` — API, schema, auth, and scraper behavior

Test hierarchy (quick):

```text
tests/
  ├─ conftest.py          # Global: database mode, asyncio_mode=auto
  ├─ fixtures_shared.py   # Database fixture selection
  ├─ unit/
  ├─ e2e/
  └─ shared/
```

When to write each type:

- Unit: single function/method, no I/O — fast
- E2E: Compose/external-stack workflows — slow and opt-in

Fixture patterns:

- Database mode controlled by `PYTEST_DB_MODE` (default: `aiosqlite`)
- Run ingestor integration tests against PostgreSQL: `uv run pytest -m integration`

Coverage expectations:

- Local platform checks: `uv run pytest tests/unit/ -m unit`
- CI covers root platform checks plus `services/ingestor/tests/` by marker.
