# Testing Architecture

Last reviewed: 2025-07 | Owner: ingestor team

## Test tree layout

```text
tests/
  unit/            # top-level unit tests        → marker: unit
  integration/     # top-level integration tests → marker: integration
  e2e/             # end-to-end / Floci / AWS    → marker: e2e / aws
  fixtures_shared.py   # single source of shared fixtures
  conftest.py          # re-exports fixtures_shared.__all__ only

services/ingestor/tests/
  unit/            # service unit tests          → marker: unit
  integration/     # service integration tests  → marker: integration
  conftest.py      # re-exports fixtures_shared.__all__ only
```

## Marker policy

| Marker | What belongs here | DB needed | Docker needed |
|---|---|---|---|
| `unit` | Pure logic, no I/O, no DB, mocks only | no | no |
| `integration` | ASGI client, DB, Cache, Kafka | yes (Postgres + Cache) | optional (testcontainers auto-provisions) |
| `e2e` | Full stack, Bruno API suite, Floci/AWS | yes | yes |
| `aws` | LocalStack / Floci AWS emulation | yes | yes |

Markers are applied at the directory level via `conftest.py` (`pytestmark = pytest.mark.integration`). Per-file overrides are only needed for exceptions (e.g. `pytest.mark.skip`).

## Fixture ownership model

1. Shared fixtures (DB session, HTTP client, Cache, migrations) live only in [`tests/fixtures_shared.py`](../../tests/fixtures_shared.py).
2. `tests/conftest.py` and `services/ingestor/tests/conftest.py` re-export `fixtures_shared.__all__` — no logic of their own.
3. Tree-local fixtures (if any) stay in the owning tree's `conftest.py`.
4. Never import fixtures across trees in either direction.

## Database strategy

- Unit tests: `sqlite+aiosqlite:///:memory:` (no external dep).
- Integration tests local: testcontainers auto-provisions `pgvector/pgvector:pg17` when Docker is available and `DATABASE_URL_TEST` is not set.
- Integration tests CI: `DATABASE_URL_TEST` injected by GitHub Actions service container (Postgres + Cache).
- The `DATABASE_URL_TEST` in `.env` is intentionally ignored by the fixture bootstrap to prevent suppressing testcontainers auto-provisioning.

## Local repro commands

```bash
just test-unit
just test-integration
just test-e2e        # requires full stack running
```

Or directly:

```bash
uv run pytest -m unit -q
uv run pytest -m integration -q
uv run pytest -m e2e -q
```
