# Plan: api-observatory — Vertical Slice MVP

**Status**: Active ✅
**Updated**: 2026-05-24
**Repo**: https://github.com/ivanprytula/api-observatory.git
**Local dir**: /home/ivanp/PersonalProjects/data-pipeline-async (orphan branch `foundation`, index cleared)
**Job context**: Middle/middle+ Python dev role — prioritise shippable demo over completeness

## TL;DR

Build the repo with ~13 atomic commits, starting from a full `services/ingestor/` baseline import in Commit 1, then hardening each vertical slice (DB → repo → route → test). Start applying to jobs after commit 2 (docs + runnable demo). Then layer in auth normalization, observability polish, and a full ECS deployment as portfolio depth. During MVP, keep schema churn minimal; after MVP ship, switch to migration-first DB changes with clean incremental history. Docker volumes removed from default stack.

**Commit sequence**: 1 (setup) → 2 (docs) → 3 (infra) → 4-8 (stabilize slices) → 8b (Streamlit UI) → 8c (Bruno collections) → 9 (auth) → 10 (observability) → 11 (resilience) → 12 (agent) → 13a-c (deploy).

**Overengineering guard** (read before every commit): prefer the stdlib or a well-known PyPI package over a custom implementation. The simplest solution that satisfies the functional requirement is the correct solution. Custom abstractions only when the same pattern repeats 3+ times.

**Test Gate policy (required from first test-bearing commit onward):**
- During MVP stabilization: do not require Alembic-backed Postgres integration/e2e gates.
- On every PR/feature commit during MVP: run lane 1 (`unit`) and optional SQLite-backed API smoke tests for touched slices.
- After MVP ships: enable lane 2 (`integration or e2e`) as a required release/deploy gate on real PostgreSQL/Redis via `testcontainers[postgres,redis]`.

**Canonical test commands:**
```bash
# Lane 1: fast unit tests (SQLite/aiosqlite)
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"

# Optional MVP smoke (SQLite-backed API slice checks)
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest services/ingestor/tests/integration/test_source_registry_api.py -q

# Post-MVP full gate (required before release/deploy)
# integration/e2e on real Postgres/Redis via testcontainers
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```

---

## PHASE 0: Preserve History ✅ DONE

1. ~~Tag pushed to `develop` branch on current remote~~ ✅
2. ~~New GitHub repo created~~ — https://github.com/ivanprytula/api-observatory.git ✅
3. ~~Add new remote~~ `git remote add observatory ...` ✅
4. ~~Create orphan branch~~ `git checkout --orphan foundation` ✅
5. ~~Unstage everything~~ `git rm -rf --cached .` ✅
6. First baseline commit created on `foundation`:
  - `fef4440` — `chore: project setup + ingestor baseline import` ✅

---

## PHASE -1: Triage the 800 Files (before first commit)

Current state: 800+ files staged on orphan `foundation` branch. Do not commit them as-is — build up deliberately.

### Delete from the index

```bash
# Services not in MVP scope
git rm -r services/portal/
git rm -r services/inference/ services/dashboard/ services/analytics/
git rm -r services/webhook/ services/timeseries/ services/search/

# Artefacts — add to .gitignore instead
git rm -r htmlcov/
git rm secrets-findings.json

# Old learning archive (kept on old remote)
git rm -r _archive/learning_docs/
```

### Move (isolate, not delete)

```bash
# Create archive destination
mkdir -p examples/archived-services

# Move (don't delete) out-of-scope services
mv services/portal examples/archived-services/
mv services/inference examples/archived-services/
mv services/dashboard examples/archived-services/
mv services/analytics examples/archived-services/
mv services/webhook examples/archived-services/
mv services/timeseries examples/archived-services/
mv services/search examples/archived-services/

# Move the other items as planned
mv services/processor examples/kafka-consumer/
mv services/ingestor/fetch_aiohttp.py examples/http-clients/aiohttp_example.py
mv services/ingestor/storage/mongo.py _archive/mongo-storage.py

# Only delete build artifacts (not code)
rm -rf htmlcov/
rm -f secrets-findings.json
rm -rf _archive/learning_docs/

# Verify
ls -la examples/
```

### Review every remaining file before staging

1. Does it serve the MVP feature? If no → archive or delete.
2. Is there a simpler stdlib/PyPI equivalent for what it implements? If yes → replace.
3. Does it follow the Copilot instructions? If no → refactor first.

---

## Commit Sequence (~13 commits, 3-4 weeks part-time)

```bash
# Git setup — run once, not a commit
git remote add observatory https://github.com/ivanprytula/api-observatory.git
# already done: checkout --orphan foundation && git rm -rf --cached .
```

---

## PHASE 1: Foundation (Commits 1-3)

### Commit 1 — `chore: project setup + ingestor baseline import` [DONE]

**Contents**: `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, `.gitignore`, `.editorconfig`, `.env.example`, `Justfile` (recipes: `up`, `down`, `test`, `lint` only), `.pre-commit-config.yaml`, `infra/database/Dockerfile`, `infra/database/postgresql.conf`, `infra/database/pg_hba.conf`, `infra/database/init.sql` + whole `services/ingestor/` service tree (code, routers, schemas, repositories, tests) + `libs/` (shared code used by ingestor).

**Retrospective note (what was required to make foundation verify pass)**:
- Add local/default runtime values for app startup checks (for example `SERVICE_VERSION` via compose env).
- Keep optional integrations fail-open when modules are intentionally absent in baseline (Mongo/scraper/agent optional paths).
- Fix duplicate ORM index declarations that break `Base.metadata.create_all` startup bootstrap.

**Infra simplicity checks**:
- `pyproject.toml`: remove `celery`, `django-celery-beat`, `motor`, `qdrant-client`; move `aiohttp` to `[dependency-groups.examples]`. Keep only what the ingestor service imports.
- `docker-compose.yml`: default stack = `db`, `redis`, `redpanda`, `ingestor` only. No named volumes — ephemeral containers are fine for dev. Remove mongodb and qdrant from default.
- `Dockerfile`: multi-stage only if it reduces final image size by >30%. Don't add layers for complexity's sake. Remove any deps (playwright, browser libs) that aren't in `pyproject.toml`.
- `.gitignore`: add `htmlcov/`, `secrets-findings.json`, `.env`, `__pycache__`, `.venv`

**Baseline import guardrails**:
- Keep existing runtime behavior intact; Commit 1 is a baseline snapshot, not a refactor.
- Verify `config.py` still uses `pydantic-settings` `BaseSettings` and `database.py` uses async SQLAlchemy 2.0 patterns.
- Keep local dev simple (`create_all`), but if integration tests fail due schema drift, add a proper forward migration (no ad-hoc schema hotfix).
- Defer cleanup/refactors to later commits; do not mix large behavioral changes into baseline import.

**Verify**:
```bash
docker compose build --no-cache ingestor   # exit 0
docker compose up -d
docker compose ps                          # db/redis/redpanda healthy, ingestor warming up
curl -s http://localhost:8000/health       # 200
curl -s http://localhost:8000/readyz       # 200
curl -s http://localhost:8000/docs         # 200
docker compose down
```

---

### Commit 2 — `docs: README, tech-map, learning-paths` [DONE]

**Contents**: `README.md` (rewrite), `docs/tech-map.md`, `docs/learning-paths.md`

**README**: mission (1 sentence), quick start (3 commands max), What's Running table (service → port → purpose), links to tech-map and learning-paths.

**tech-map.md** — interview topic → exact `file:function` reference:

| Topic | Where in code |
|-------|---------------|
| Async Python | `fetch.py:BaseFetcher`, `database.py:get_db` |
| SQLAlchemy 2.0 async | `models.py`, `repositories/` |
| APScheduler jobs | `jobs.py`, `jobs_registry.py` |
| Redis cache + pub/sub | `cache.py`, `rate_limiting.py`, `routers/ws.py` |
| Circuit breaker | `libs/resilience/circuit_breaker.py` |
| RLS multi-tenancy | `alembic/versions/*rls*`, `security/` |
| Observability | `metrics.py`, `main.py` lifespan |
| LangGraph HITL + SSE | `agent/graph.py`, `routers/agent.py` |
| WebSocket | `routers/ws.py` |
| Contract drift | `routers/contract_drift.py`, `routers/scorecards.py` |
| GitHub Actions CI/CD | `.github/workflows/` |
| Terraform ECS | `infra/terraform/` |

**learning-paths.md**: three tracks — Backend Interview Prep, Distributed Systems, DevOps/Cloud.

**Verify**: all README links resolve. `docker compose up -d && curl -s http://localhost:8000/docs` — quick-start works end-to-end. `docker compose down`.

---

### Commit 3 — `chore: .github instructions, hooks, skills` [DONE]

**Contents**: `.github/copilot-instructions.md` (updated), `.github/instructions/`, `.github/skills/`, `.husky/` pre-commit hooks, `.vscode/settings.json` + `launch.json`

The 14 existing workflows stay as-is — do not modify them.

**Verify**: pre-commit hook fails on a deliberate `ruff` lint error.

---

## PHASE 2: Stabilize Existing Vertical Slices (Commits 4-8)

### Commit 4 — `refactor(vs1): stabilize source-registry — SourceProfile CRUD` [DONE]

**Scope**: existing `SourceProfile` model/repository/router/schemas/tests — harden behavior and trim complexity.

**Functional requirement**: Create, list, get, update, deactivate SourceProfile (name, base_url, health_check_path, probe_interval_seconds, is_active).

**Simplicity checks**:
- Repository: 5 plain async functions. No base class until 3+ repositories share the same pattern.
- Schemas: `SourceProfileCreate` + `SourceProfileResponse`. No `SourceProfileUpdate` unless PATCH is in scope.
- Pagination: `limit: int = 20, offset: int = 0`. Offset is fine for < 10k rows.
- URL validation: `pydantic.AnyHttpUrl` — no custom regex.

**⚠️ SSRF prevention** (security-critical — `base_url` will be used in server-side HTTP requests):
- Scheme: `https` only (or explicitly allowed `http`)
- Resolved IP must not be in private ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1`
- Use `ipaddress` stdlib module to validate the resolved IP.

**Tests**: create, list (pagination), get (404 on missing), deactivate (idempotent).

**Verify**:
```bash
docker compose up -d
curl -s -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{"name":"httpbin","base_url":"https://httpbin.org","health_check_path":"/get","probe_interval_seconds":60}' | jq .id
# → 1
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest services/ingestor/tests/integration/test_source_registry_api.py -q
docker compose down
```

---

## PHASE 3: Stabilize Probe Loop (Commit 5)

### Commit 5 — `refactor(vs2): stabilize probe-scheduler — APScheduler background HTTP probe loop` [DONE]

**Scope**: existing `HealthSample`/scheduler/lifespan wiring/tests — keep behavior, reduce accidental complexity.

**Functional requirement**: On startup, schedule one probe job per active SourceProfile. Each job: HTTP GET → record `status_code`, `response_time_ms`, `response_body_hash`. Persist to `provider_health_samples`.

**Simplicity checks**:
- APScheduler: `AsyncScheduler` from `apscheduler>=3.10,<4.0`. **Do not upgrade to 4.x** — API changed incompatibly.
- HTTP client: use existing `fetch.py` httpx client. One HTTP client per project.
- SHA-256: `hashlib.sha256(body).hexdigest()` — stdlib. No extra dependency.
- Response time: `time.monotonic()` before/after call — stdlib.
- Circuit breaker: wire existing `libs/resilience/circuit_breaker.py`. If open → skip and log, do not raise.
- Job isolation: `asyncio.gather(*tasks, return_exceptions=True)`.
- Timeout: `httpx.AsyncClient(timeout=10.0)` — not configurable yet.

**Overengineering trap**: no job queue, worker pool, or message bus. APScheduler + asyncio is sufficient for hundreds of sources.

**Verify**:
```bash
docker compose up -d
just seed-demo
docker compose restart ingestor
# Wait ~70s for first probe cycle (probe jobs are registered on startup)
docker compose exec db psql -U postgres api_observatory -c "SELECT count(*) FROM provider_health_samples;"
# → count > 0
docker compose down
```

---

## PHASE 4: Stabilize Scorecard (Commit 6)

### Commit 6 — `refactor(vs3): stabilize scorecard — rolling 24h uptime and latency` ✅ DONE

**Scope**: existing `ProviderScorecard` model/repository/compute/router/tests — validate SQL-first aggregation path.

**Simplicity checks**:
- Computation: one SQL query with `AVG`, `PERCENTILE_CONT(0.5)`, `PERCENTILE_CONT(0.95)`, `COUNT FILTER`. Aggregation in SQL — do not pull rows into Python.
- Upsert: `insert().on_conflict_do_update()` — not SELECT then INSERT (race condition).
- Window: `WHERE created_at > now() - interval '24 hours'`. No windowing library.
- No Redis caching yet — add only if Prometheus shows p95 query time > 50ms under load.

**Tests**: correct stats from 3 samples, handles zero samples (null stats), upsert idempotent.

**Verify**:
```bash
docker compose up -d
curl -s http://localhost:8000/api/v1/scorecards/1 | jq '{uptime_pct,p50_latency_ms,p95_latency_ms,error_rate}'
docker compose down
```

---

## PHASE 5: Stabilize Contract Drift (Commit 7) ✅ DONE

### Commit 7 — `refactor(vs4): stabilize contract-drift — snapshot diff, DriftEvent`

**Scope**: existing `ContractSnapshot`/`DriftEvent` models, repositories, detector, router, tests.

**Simplicity checks**:
- Diff detection: `new_hash != last_hash` — one query for last snapshot. No diff library.
- Severity: `breaking` (HTTP status class changed), `minor` (same status, body changed). Three enum values max.
- Store hash only, not full response body — bodies can be megabytes.

**⚠️ APPLY TO JOBS NOW** — if Commit 2 demo is stable, start sending applications immediately; commits 4-7 are quality hardening.

**Verify**:
```bash
docker compose up -d
# Let probes run; target must return two distinct bodies
curl -s http://localhost:8000/api/v1/drift-events | jq '. | length'
# → > 0 after body change; no increment on identical response
docker compose down
```

---

## PHASE 6: Stabilize Real-time Push (Commit 8) ✅ DONE — 6f77c5c

### Commit 8 — `refactor(vs5): stabilize websocket — Redis pub/sub, live drift notifications`

**Scope**: existing WebSocket/pubsub/publisher/tests — reliability and auth handshake hardening.

**Simplicity checks**:
- Connection manager: plain `dict[str, WebSocket]`. No custom pub/sub manager class.
- Redis pub/sub: `redis-py` async `PubSub` — already in project. No separate message broker.
- Publisher: `redis.publish(channel, json.dumps(event))` from the repository, after persisting DriftEvent.
- Auth: JWT as `?token=` query param on the WebSocket handshake. Validate before upgrading connection.

**Verify**:
```bash
docker compose up -d
docker compose down
```

---

## PHASE 6b: Streamlit Dashboard (Commit 8b)

### Commit 8b — `feat(ui): Streamlit dashboard — drift events, source health, live WS tail`

**Purpose**: Give recruiters and non-technical reviewers a visual entry point. The entire portfolio is
API-first; this adds a single-page dashboard without introducing a separate frontend service.

**Scope**: one `streamlit_app.py` file at the repo root. No new service, no new DB access —
connects to the ingestor API over HTTP and WebSocket only.

**Simplicity checks**:
- Single file, ≤ 300 lines. No custom components, no extra CSS framework.
- All I/O goes through the ingestor REST API — no direct DB or Redis access from the dashboard.
- `INGESTOR_URL` env var (default `http://localhost:8000`). Bearer token via `st.secrets` or env var.
- Three panels only: **Source Health** (scorecards table), **Drift Events** (recent events list),
  **Live Stream** (WebSocket tail, last 20 messages).
- Auto-refresh: `st.rerun()` on a timer for the health + drift panels. Manual "connect" button for WS.
- Dependencies: `streamlit`, `httpx` (already in project), `websockets`.

**Files**:
- `streamlit_app.py` — main app
- `docs/dev/streamlit-dashboard.md` — how to run, env vars, screenshot description

**Verify**:
```bash
# Start the ingestor stack first
docker compose up -d

# Run dashboard — no secrets.toml required; token is optional
uv run streamlit run streamlit_app.py
# → opens http://localhost:8501, shows three panels

# With a bearer token (if API_V1_BEARER_TOKEN is set on the server)
BEARER_TOKEN=mysecret uv run streamlit run streamlit_app.py

# Alternative: create .streamlit/secrets.toml (gitignored)
# mkdir -p .streamlit && echo 'BEARER_TOKEN = "mysecret"' > .streamlit/secrets.toml
# uv run streamlit run streamlit_app.py
```

**Note**: `st.secrets.get()` raises `StreamlitSecretNotFoundError` when no `secrets.toml`
exists — the app wraps the call in `try/except` and falls back to `os.environ`.

---

## PHASE 6c: API Collections for Testing & Documentation (Commit 8c)

### Commit 8c — `docs(api): Bruno collections — living API documentation`

**Purpose**: Replace curl snippets in README/docs with a CLI-testable, version-controlled API collection.
Bruno's `.bru` files are plain text (no binary JSON blobs), run locally without accounts/cloud, and serve as
living documentation — clone repo, run `just api-test`, all endpoints verified.

**Scope**: five collections covering all MVP endpoints.

**Simplicity checks**:
- One `bruno/` directory at repo root. Collections organized by slice: `bruno/sources/`, `bruno/records/`, etc.
- Plain text `.bru` files — Git-friendly, no vendor lock-in.
- Single environment file: `bruno/environments/local.bru` — `baseUrl = "http://localhost:8000"`, optional `token`.
- No CI blocker — `bru run` can stay local-only initially or run in CI if needed.
- No npm dependencies in main `pyproject.toml` — Bruno CLI installed separately or run via `npx`.
- Collections mirror the repo's API surface: GET/POST/DELETE on each resource slice.

**Files**:
- `bruno/sources/collection.bru` — SourceProfile endpoints (list, create, get, deactivate)
- `bruno/records/collection.bru` — ContractSnapshot + drift-events (list, POST snapshot)
- `bruno/contracts/collection.bru` — DriftEvent endpoints (list per source, list all)
- `bruno/scorecards/collection.bru` — ProviderScorecard endpoints (list, get)
- `bruno/websocket/collection.bru` — WebSocket connection test (wscat-like example)
- `bruno/environments/local.bru` — env vars: `baseUrl`, `token` (optional), `source_id` (placeholder)
- `Justfile` — add `api-test` recipe: `bru run bruno/ --env local`
- `docs/dev/bruno-collections.md` — how to install Bruno, run collections, add new requests
- `README.md` — link to `docs/dev/bruno-collections.md`, replace curl snippets with `just api-test`

**Key requests per collection** (each should be a real, working request against the running stack):

| Collection | Requests |
|------------|----------|
| sources | GET all, POST create, GET by ID, PATCH deactivate |
| records | POST new snapshot, GET drift-events for source, GET all drift-events |
| scorecards | GET all scorecards, GET scorecard for source |
| websocket | WS connect example (commented note: use wscat for interactive) |

**Verify**:
```bash
# Install Bruno if not already present
npm install -g @usebruno/cli    # or: npx @usebruno/cli

# Start ingestor stack
docker compose up -d

# Run all collections against the running stack
just api-test
# → all requests return 200/2xx
# → output is human-readable (request name, status, response summary)

# Alternative: run a single collection
bru run bruno/sources --env local

# Alternative: run with verbose output
bru run bruno/ --env local --verbose

docker compose down
```

**Bruno CLI notes**:
- `bru run [collection path] --env [env name]` — runs all requests in sequence.
- `--env local` matches the `bruno/environments/local.bru` file.
- Exit code 0 if all requests pass (2xx response codes), non-zero if any fail.
- No account/login required — all auth is via `BEARER_TOKEN` env var.

**Integration with CI** (post-MVP):
```yaml
# Example GitHub Actions step (do not add to .github/workflows yet)
- name: Test API with Bruno
  run: |
    npm install -g @usebruno/cli
    docker compose up -d
    bru run bruno/ --env local
    docker compose down
```

---

## PHASE 7: Auth Cross-cut (Commit 9)

### Commit 9 — `feat: JWT auth, RBAC, apply to all routes`

**Simplicity checks**:
- JWT: use `python-jose` or `PyJWT`. Do not write your own encoder/decoder.
- Passwords: `passlib[bcrypt]`. Do not use `hashlib.sha256` for password storage.
- RBAC: two roles only — `admin` (write) and `viewer` (read). No permission matrices yet.
- Token TTL: 30min access, 7 days refresh.
- Error responses: `401` for both wrong password and unknown user — prevents user enumeration.
- `get_current_user` dependency: one implementation, shared across all routers via `Depends`.

**Verify**:
```bash
docker compose up -d
docker compose down
```

---

## PHASE 8: Observability (Commit 10)

### Commit 10 — `feat: structured logging, Prometheus metrics, OTEL traces`

**Simplicity checks**:
- Structured logging: `structlog` — do not hand-roll a JSON formatter on stdlib `logging`.
- HTTP metrics: `prometheus-fastapi-instrumentator` — one line, all standard HTTP metrics included.
- OTEL: `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-sqlalchemy` auto-instrumentation. No manual span creation per function.
- Health probes: `/health` (liveness, no I/O), `/readiness` (checks DB + Redis). ~20 lines — no health framework.
- Cache scorecard only after measuring: Redis `SETEX` 30s TTL is sufficient if needed. No caching library.

**Verify**:
```bash
docker compose up -d
docker compose down
```

---

## PHASE 9: Resilience Patterns (Commit 11)

### Commit 11 — `feat: rate limiting, circuit breaker applied`

**Simplicity checks**:
- Rate limiting: `slowapi` (Starlette-compatible, Redis backend, per-user + per-IP). Do not implement a token bucket from scratch.
- Circuit breaker: review `libs/resilience/circuit_breaker.py`. If > 80 lines of state machine code, compare to `pybreaker` — prefer the established library unless the custom code is demonstrably simpler.
- Return `Retry-After` header on 429 (built into `slowapi`).

**Verify**:
```bash
docker compose up -d
docker compose down
```

---

## PHASE 10: LangGraph Agent (Commit 12)

### Commit 12 — `feat(agent): LangGraph HITL, SSE streaming`

**Simplicity checks**:
- Review existing `agent/graph.py` before modifying — it is a real implementation.
- SSE: `StreamingResponse(media_type="text/event-stream")` — no separate SSE library.
- Agent tools must call existing repository functions — no raw SQL inside tool definitions.

**Verify**:
```bash
docker compose up -d
docker compose down
```

---

## PHASE 11: Deployment (Commits 13a-13c)

### Commit 13a — `chore(docker): image size audit, multi-stage verify`

Verify image < 500MB. `docker scan` passes (no critical CVEs).

**Verify (tests)**:
```bash
docker compose up -d
docker compose down
```

### Commit 13b — `infra(floci): local AWS sim, Terraform plan, E2E tests`

Cost-guard: comment out `module "messaging"` in `infra/terraform/environments/dev/main.tf` (MSK = $2.64/day). Without MSK: ~$2.50/day → 2-day test ≈ $5.

```bash
just sandbox-up && just tf-plan-local && just sandbox-test && just tf-destroy-local
```

### Commit 13c — `docs(deploy): AWS ECS step-by-step, cost teardown`

Docs only (`docs/deployment/aws-ecs.md`, `docs/deployment/cost-teardown.md`). No code changes.

**Verify**:
```bash
DATABASE_URL_TEST=sqlite+aiosqlite://:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```

---

## Justfile DX Recipes (added in Commit 3, extended in Commit 8c)

- `just probe-once` — run one full probe cycle manually
- `just scorecard SOURCE_ID` — print current scorecard for a source
- `just seed-demo` — seed 3 demo SourceProfiles (httpbin.org, jsonplaceholder.typicode.com, postman-echo.com)
- `just tech-map` — `bat docs/tech-map.md || cat docs/tech-map.md`
- `just api-test` — `bru run bruno/ --env local` (added Commit 8c)

---

## Pre-Commit Checklist (apply before every `git commit`)

**Correctness**
- [ ] Feature works end-to-end (manually tested or covered by a test)
- [ ] `docker compose exec ingestor uv run pytest -x` passes
- [ ] `docker compose exec ingestor uv run python -c "from services.ingestor.main import app"` — zero import errors

**Simplicity (anti-overengineering)**
- [ ] Is there a stdlib or well-known PyPI solution I should use instead?
- [ ] Does each class/function have only one reason to exist?
- [ ] Is any abstraction used by fewer than 3 callers? If yes, inline it.
- [ ] Did I add a dependency for something I could write in < 20 stdlib lines?

**Code quality**
- [ ] `docker compose exec ingestor uv run ruff check services/` — zero errors
- [ ] `docker compose exec ingestor uv run black --check services/` — no diffs
- [ ] Type hints 100% on all new public functions
- [ ] No `print()` — use `logger`
- [ ] No bare `except:` — catch specific exceptions

**Security (OWASP)**
- [ ] No hardcoded secrets, passwords, tokens
- [ ] User-controlled URLs validated against private IP ranges (SSRF)
- [ ] Parameterised SQL only — no f-string queries
- [ ] Error responses do not leak internal state

**Async**
- [ ] No blocking I/O on the event loop (`time.sleep`, `requests.get`, sync `open()`)
- [ ] `asyncio.gather` used for parallel independent tasks

---

## Proven Solutions Reference

Check this table before writing any new code. If the need is listed here, use the solution in the "Use" column — do not build a custom alternative.

| Need | Use | Do NOT build |
|------|-----|--------------|
| Settings/config | `pydantic-settings BaseSettings` | Custom env-var parser |
| HTTP client | `httpx.AsyncClient` | Custom session wrapper |
| URL validation | `pydantic.AnyHttpUrl` | Custom regex |
| Password hashing | `passlib[bcrypt]` | `hashlib.sha256` on passwords |
| JWT encode/decode | `python-jose` or `PyJWT` | Custom base64 encoder |
| Structured logging | `structlog` | JSON formatter on stdlib `logging` |
| HTTP metrics | `prometheus-fastapi-instrumentator` | Manual `Counter`/`Histogram` per route |
| OTEL tracing | `opentelemetry-instrumentation-fastapi` auto | Manual spans per function |
| Rate limiting | `slowapi` | Custom token bucket |
| SHA-256 body hash | `hashlib.sha256` (stdlib) | Any PyPI hash library |
| Response time | `time.monotonic()` (stdlib) | Timing decorator library |
| Pagination | `limit`/`offset` query params | Cursor pagination (add only at > 50k rows) |
| Job scheduling | `apscheduler>=3.10,<4.0 AsyncScheduler` | Custom asyncio task manager |
| Redis pub/sub | `redis-py` async `PubSub` | Custom broker or message bus |
| SSE | `StreamingResponse(media_type="text/event-stream")` | Separate SSE library |
| Circuit breaker | `pybreaker` or existing `libs/resilience/` | Custom state machine > 80 lines |
| DB upsert | `insert().on_conflict_do_update()` | SELECT then INSERT (race condition) |
| Percentile stats | `PERCENTILE_CONT` in SQL | Python `statistics` on fetched rows |

---

## Verification Gates

### During MVP stabilization (default)

```bash
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest services/ingestor/tests/integration/test_source_registry_api.py -q
```

### After commit 2 — start applying to jobs

```bash
docker compose up -d && just seed-demo
curl -s http://localhost:8000/api/v1/scorecards | jq .
# Returns uptime_pct, p50_latency_ms, p95_latency_ms
docker compose exec ingestor uv run pytest tests/ -m "not e2e" -q
# All pass
docker compose down
```

### After commit 8c — API collections live

```bash
docker compose up -d && just seed-demo
just api-test
# → all requests pass (2xx responses)
docker compose exec ingestor uv run pytest tests/ -q
docker compose down
```

### After commit 11 — full MVP+

```bash
docker compose up -d
docker compose exec ingestor uv run pytest tests/ -q
docker compose exec ingestor uv run ruff check services/ && docker compose exec ingestor uv run black --check services/
docker build -t api-obs:test .
# WebSocket: connect client, trigger drift, assert event received
docker compose down
```

### After commit 13 — deployment

```bash
just sandbox-up && just sandbox-test && just tf-destroy-local
terraform output | grep alb_dns_name
curl https://<alb-dns>/docs        # 200 OK
terraform destroy                  # clean, no billable resources remain
# Post-MVP release gate:
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```

---

## Decisions

- **Repo**: `api-observatory`, public. Old remote keeps full 8-phase history.
- **Local dir**: stay in place (orphan branch) — VS Code workspace unchanged.
- **Alembic**: post-MVP policy is migration-first for any schema change (one revision per change, forward-only in feature branches, no manual hotfix SQL in tests/runtime).
- **Docker volumes**: default stack has no volumes. Named volumes in `docker-compose.dev.yml` only.
- **Service scope**: `services/ingestor/` only for MVP. Other services archived or moved to `examples/`.
- **APScheduler**: `>=3.10,<4.0` locked. Do not upgrade to 4.x.
- **MSK/Kafka**: commented out in dev Terraform. ~$2.50/day without it → 2-day test ≈ $5.
- **Auth timing**: normalize/lock auth behavior in commit 9 (if baseline diverges). Routes can remain open temporarily during earlier stabilization commits.
- **aiohttp**: moved to `examples/http-clients/` — deliberate comparison file, not deleted.
- **LangGraph agent**: keep as-is, document in tech-map — real HITL + SSE implementation.

## Excluded from Scope

- Other services (inference, dashboard, analytics, webhook, timeseries, search)
- Kubernetes manifests (ECS is the deploy target)
- CI/CD workflow changes (14 workflows already solid)
- Semantic diff for contract drift (hash comparison is sufficient)
- Cursor pagination (offset is fine for MVP scale)
