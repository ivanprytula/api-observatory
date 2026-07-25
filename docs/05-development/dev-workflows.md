# Development Workflows

Track: A — Product and Onboarding

Workflow intent, sequence, and canonical commands for active development.

---

## Daily Cadence

```text
1. just doctor                → verify tooling
2. just up                    → start dependencies + API (Docker-first)
3. just migrate               → apply Alembic migrations
4. uv run pytest -m unit -q   → fast unit checks (iterating)
5. uv run pytest -m integration -q  → integration checks (before merge)
6. pre-commit run --all-files → lint/format gates (before PR)
7. just down                  → shut down when done
```

## Two Development Modes

### Docker-first (default)

```bash
just up       # start full stack in Docker
just dev      # Docker infra + host uvicorn (hot reload)
```

Best for: integration parity, migration validation, CI-equivalent environment.

### Infra-only + local uvicorn

```bash
docker compose up -d db cache broker   # infrastructure containers only
uv run uvicorn ingestor.main:app --reload  # debugger-attachable
```

Best for: IDE debugging, breakpoint workflows, faster reload cycles.

---

## Canonical Commands

### Core

| Action | Command |
|--------|---------|
| Health check | `just doctor` |
| Start stack | `just up` |
| Stop stack | `just down` |
| Dev server (hot reload) | `just dev` |
| Apply migrations | `just migrate` |
| Reset DB | `just db-reset` |
| Bootstrap demo data | `just init` |

### Testing

| Action | Command |
|--------|---------|
| Unit tests | `just test-unit` or `uv run pytest -m unit -q` |
| Integration tests | `just test-integration` or `uv run pytest -m integration -q` |
| E2E tests | `just test-e2e` or `uv run pytest -m e2e -q` |
| All tests | `uv run pytest tests/ -v` |

### Linting & Type Checking

| Action | Command |
|--------|---------|
| Ruff lint | `uv run ruff check .` |
| Ruff format check | `uv run ruff format --check .` |
| mypy type check | `uv run mypy .` (via `ty`) |
| Pre-commit all | `pre-commit run --all-files` |

### API Testing (Bruno)

```bash
just api-test                # run Bruno collection against localhost
npm install -g @usebruno/cli # install Bruno CLI first
```

Collections live in `bruno/`: auth, sources, contracts, scorecards, ops, websocket.
Use Bruno Desktop (`just bruno`) for interactive work. WebSocket testing requires `wscat` or the Streamlit dashboard.

### Authenticated k6 Smoke

Start the local stack first with `just up`. The smoke test creates its own disposable
viewer account, checks `/health`, and reads the protected source list. It records a
local baseline but deliberately does not enforce a latency threshold yet.

```bash
export K6_USERNAME="k6local$(date +%s)"
read -rsp 'k6 password: ' K6_PASSWORD
export K6_PASSWORD
k6 run --summary-export=/tmp/api-observatory-k6-summary.json \
  scripts/load/k6-ci-smoke.js
```

The same test runs weekly and on demand in GitHub Actions as
[`performance-smoke.yml`](../../.github/workflows/performance-smoke.yml). Download
its `performance-smoke-*` artifact to compare JSON summaries before setting a
latency SLO gate.

### Database Ops

| Action | Command |
|--------|---------|
| Safe psql | `just psql-safe` (blocks RDS hostnames) |
| Dump local DB | `just pg-dump` |
| Restore from file | `just pg-restore <file>` |
| Restore from S3 | `just pg-restore-from-s3 s3://...` |

### Floci Sandbox

| Action | Command |
|--------|---------|
| Start Floci + seed | `just floci-up` |
| Dev against Floci | `just floci-dev` |
| Validate Floci health | `just floci-validate` |
| Run Floci E2E tests | `just floci-test` |

### Terraform

```bash
TF_ENV=sandbox just tf init   # sandbox (default)
TF_ENV=dev just tf init       # real AWS dev
TF_ENV=sandbox just tf plan
TF_ENV=sandbox just tf apply
```

---

## Testing Architecture

### Test Tree Layout

```text
tests/
  unit/              → marker: unit
  integration/       → marker: integration
  e2e/               → marker: e2e / aws
  fixtures_shared.py # single shared fixtures source
  conftest.py        # re-exports fixtures_shared.__all__

services/ingestor/tests/
  unit/              → marker: unit
  integration/       → marker: integration
  conftest.py        # re-exports fixtures_shared.__all__
```

### Marker Policy

| Marker | DB needed | Docker needed |
|--------|-----------|---------------|
| `unit` | no | no |
| `integration` | Postgres + Cache | optional (testcontainers) |
| `e2e` | yes | yes |
| `aws` | yes | yes |

### Database Strategy

- **Unit tests:** `sqlite+aiosqlite:///:memory:` (no external dep)
- **Integration tests local:** testcontainers auto-provisions `pgvector/pgvector:pg17`
- **Integration tests CI:** `DATABASE_URL_TEST` injected by GHA service container

### Fixture Ownership

1. Shared fixtures (DB session, HTTP client, Cache, migrations) live in `tests/fixtures_shared.py`.
2. `tests/conftest.py` and `services/ingestor/tests/conftest.py` re-export `fixtures_shared.__all__` — no logic of their own.
3. Never import fixtures across trees in either direction.

---

## Code Review Checklist

- New functions in `services/ingestor/` must include Google-style docstrings (purpose, Args, Returns, design patterns applied)
- Parameterized DB access (no raw SQL string interpolation)
- No hardcoded secrets or API keys
- Respect import boundaries: `libs/` must not import from `services/`

## Contract Drift Detection

Each ingest submits a **ContractSnapshot** with SHA-256 fingerprint. If fingerprint matches previous, diff is skipped. Otherwise field-level diff runs → **DriftEvent** with type (breaking/non-breaking/none), severity, score, summary. Events publish to Cache pub/sub channel `ingestor:events`.

## Bruno Collections

- Run: `just bruno` (Desktop) or `bru run` (CLI)
- Post-response scripts auto-set `token` and `source_id`
- To add a request: Desktop right-click → New Request, or create `.bru` file manually

## Contract Version Bumping

```bash
python scripts/bump_contracts_version.py --check                       # validate
python scripts/bump_contracts_version.py --apply --strategy patch --changelog-entry "..."  # bump
```

Pre-commit hook runs automatically. CI-side auto-bump is deferred (pre-commit hook sufficient for now).

---

## Related Documents

- [Setup Guide](../04-setup/setup-guide.md) — first-time bootstrap
- [Policies & Gotchas](policies.md) — CI policy, common pitfalls, dependency management
- [CI/CD Reference](../06-ci-cd/ci-cd.md) — workflow semantics and governance
- [Infrastructure Deployment Guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md) — canonical cloud deploy runbook
