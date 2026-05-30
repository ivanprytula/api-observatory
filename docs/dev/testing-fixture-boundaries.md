# Testing Fixture Boundaries

## Goal

Define a single fixture ownership model so test trees stay independent and predictable.

## Ownership Rules

1. Cross-tree shared fixtures live in [tests/fixtures_shared.py](../../tests/fixtures_shared.py).
2. [tests/conftest.py](../../tests/conftest.py) and [services/ingestor/tests/conftest.py](../../services/ingestor/tests/conftest.py) only re-export from shared fixtures (or define truly local fixtures).
3. Root [conftest.py](../../conftest.py) is for collection policy only (no fixture aliasing).
4. Tree-local overrides must stay in the owning tree's `conftest.py`.

## Import Policy

1. Do not import fixtures from `services/ingestor/tests/*` into `tests/*`.
2. Do not import fixtures from `tests/conftest.py` into `services/ingestor/tests/*`.
3. Reusable fixtures must be promoted to [tests/fixtures_shared.py](../../tests/fixtures_shared.py).

## CI Policy Alignment

1. Unit tests run on pull requests and pushes to main.
2. Integration tests run on pull requests and pushes to main with Postgres and Redis services.
3. Integration coverage gate is enforced at 80% in CI.

## Local Repro Commands

```bash
uv sync --frozen
uv run pytest -q -m unit
uv run pytest -q -m integration --cov=services/ingestor --cov=libs --cov-fail-under=80
```
