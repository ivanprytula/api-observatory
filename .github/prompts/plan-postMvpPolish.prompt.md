# Plan: Post-MVP Polish — 6 Questions → 4 Commits

**Created**: 2026-05-26
**Status**: Draft — awaiting user approval

## TL;DR

All 13 MVP commits are done. These 6 questions map to 4 focused commits (14a-14d) addressing behavioral gaps (Alembic), DX polish (Justfile), new docs (C4 + dev guide), and CI cleanup (14 → 5 workflows).

---

## Phase 1 — Loose ends + Alembic switch (Commit 14a) [done]

Commit: `feat(migrations): switch to alembic-first schema bootstrap`

**Steps:**
1. Commit untracked `scripts/setup/03-verify-system-requirements.sh` (git status shows `??` — left over from commit 13b unstage)
2. Remove `create_all` block from `services/ingestor/main.py` L233-L249 (the `if settings.environment.lower() in {"development",...}` guard)
3. Update `db-reset` recipe in Justfile: insert `just migrate` after DB readiness check, before `docker compose up -d ingestor`
4. Update `docs/02-first-time-setup.md`: remove implication that schema auto-applies in dev, make `just migrate` explicit required step

**Note**: `alembic check` requires Postgres — add to integration lane only (post-MVP CI gate), not unit test job.

---

## Phase 2 — Justfile DX (Commit 14b) [done]

Commit: `dx(justfile): add section headers and workflow phase comments`

Add 5 section headers to the Justfile (2 already exist: Backup & Restore, API Testing):
- `# ─── CORE STACK ───` before `up`
- `# ─── DAILY DEV WORKFLOW ───` before `seed-demo`
- `# ─── DOCKER IMAGE TOOLS ───` before `docker-build-image`
- `# ─── FLOCI / AWS SANDBOX ───` before `floci-up` / `floci-dev`
- `# ─── PRE-RELEASE GATE ───` before `deploy-audit` (move after Docker tools section)

**No behavioral changes** — comments only.

---

## Phase 3 — Documentation (Commit 14c) [done]

Commit: `docs: C4 system design diagram, developer guide`

**Steps:**
1. Create `docs/design/system-design-c4.md`:
   - L1 Context (user → system → external APIs/AWS)
   - L2 Container (ingestor, Postgres, Redis, Redpanda, Streamlit, Trivy)
   - L3 Component (ingestor internals: routers, jobs, security, observability, agent, repos)
   - Future services as dashed nodes in L2 (inference, dashboard, analytics, webhook, timeseries, search)
   - Note: `docs/04-architecture-overview.md` has a flowchart — C4 goes in separate file (different model)

2. Create `docs/dev/developer-guide.md` as master admin/dev guide:
   - Prerequisites + `just doctor`
   - First-time setup sequence
   - Daily dev loop
   - Running tests (unit vs integration)
   - Debugging (uvicorn reload, pytest -x, container logs)
   - Load testing (hey/httpie baseline, k6 when script exists)
   - Adding endpoints (6-step recipe)
   - Adding future services (libs/platform pattern)
   - Floci sandbox workflow
   - Pre-deployment gate checklist
   - Extending observability
   - Note: supplements (does not replace) `docs/02-first-time-setup.md`, `docs/03-daily-development.md`

---

## Phase 4 — CI overhaul (Commit 14d) [done]

Commit: `ci: replace 9 legacy multi-service workflows with MVP-scoped pipeline`

**Delete 9 files:**
- `build-ci-image.yml` (builds custom CI image — no longer needed)
- `cd-deploy.yml` (multi-environment ECS deploy, complex)
- `chaos.yml` (chaos testing, out of scope)
- `deploy-reusable.yml` (multi-service reusable deploy)
- `docker-build-reusable.yml` (multi-service reusable docker build)
- `docker-build.yml` (manual multi-service build)
- `release-preflight.yml` (multi-service release checks)
- `release-promote.yml` (multi-service promotion)
- `contracts-bump.yml.disabled` (already disabled, clean delete)

**Rewrite `ci.yml`** (3 jobs, no custom CI image, no change routing):
- `lint`: ruff check + format check on `services/` + `libs/`
- `unit-tests`: SQLite-backed pytest (no Docker), `DATABASE_URL_TEST=sqlite+aiosqlite:///:memory:`
- `docker-build`: build image, check size (no push)
- Remove: `container: ghcr.io/.../data-pipeline-ci:latest`, `dorny/paths-filter` change routing, multi-wave job structure

**Create `release.yml`**: on tag `v*` → build + push to GHCR

**Consolidate security**: `security-full.yml` uses `container: ghcr.io/.../data-pipeline-ci:latest` — must replace with `ubuntu-latest` + inline uv install after `build-ci-image.yml` is deleted. Option: merge `security-full.yml` + `security-codeql-dependency.yml` into single `security.yml`.

**Keep unchanged**: `security-secrets-lite.yml`, `dependabot-age-guard.yml`

---

## Relevant Files

| File | Phase | Change |
|------|-------|--------|
| `services/ingestor/main.py` | 1 | Remove `create_all` block (L233-L249) |
| `Justfile` | 1+2 | Update `db-reset`, add 5 section headers |
| `docs/02-first-time-setup.md` | 1 | Make `just migrate` explicit |
| `scripts/setup/03-verify-system-requirements.sh` | 1 | Commit (currently untracked) |
| `docs/design/system-design-c4.md` | 3 | New file |
| `docs/dev/developer-guide.md` | 3 | New file |
| `.github/workflows/ci.yml` | 4 | Rewrite (3-job MVP pipeline) |
| `.github/workflows/release.yml` | 4 | New file |
| `.github/workflows/security.yml` | 4 | New consolidated file |
| 9 workflow files | 4 | Delete |

---

## Verification

1. **Phase 1**: `just up` (no `create_all` warnings) → `just migrate` (20 migrations, exit 0) → `just api-check` (200). `uv run pytest -q -m unit` passes. `just db-reset` still works end-to-end.
2. **Phase 2**: `just --list` output shows section headers. All recipes still functional.
3. **Phase 3**: C4 diagrams render in GitHub markdown. `markdownlint docs/design/system-design-c4.md` and `docs/dev/developer-guide.md` pass.
4. **Phase 4**: `.github/workflows/` shows 5-6 files not 14. New `ci.yml` triggers on PR and completes in <5 min. No reference to deleted CI image.

---

## Decisions

- `alembic check` in CI: integration lane only (needs Postgres). Not in unit test job.
- `db-reset` must call `just migrate` after DB ready, before ingestor start (preserves one-command DX).
- Developer guide supplements (not replaces) existing numbered docs.
- C4 diagram is a new file — `docs/04-architecture-overview.md` has a flowchart (different format).
- `security-full.yml` must be updated (not just deleted) because it references the CI image.
- Defer `fetch_aiohttp` alternative to post-MVP/extensions; MVP stays `httpx`-first.
- Defer scraping functionality/tests to post-MVP/extensions scope.
- Defer MongoDB functionality/tests to post-MVP/extensions scope.

---

## Ongoing Work — `records` → `observations` Rename

**Status**: MVP-scoped rename complete (2026-05-29)

**Completed**:
- ✅ Renamed the 3 MVP CRUD functions in `services/ingestor/repositories/observations.py`:
   - `create_record()` → `create_observation()`
   - `create_records_batch()` → `create_observations_batch()`
   - `create_records_batch_naive()` → `create_observations_batch_naive()`
- ✅ Updated MVP callsites/imports in `services/ingestor/jobs.py` (`ingest_api_batch()`), `services/ingestor/routers/observations.py`, `tests/conftest.py`, and unit tests.
- ✅ Verified no stale `create_record*` references remain in integration/unit test paths.
- ✅ Rename-scope integration verification passed:
   - `uv run pytest services/ingestor/tests/integration/observations/test_processed_at.py services/ingestor/tests/integration/observations/test_n_plus_one_demo.py services/ingestor/tests/integration/observations/test_query_analysis.py -q`
   - Result: `31 passed`

**Scope boundary (unchanged by design)**:
- Deferred to post-MVP: non-MVP CRUD APIs (`get_observations()`, `get_observation()`, `mark_processed()`, `update_observation()`, etc.) and unrelated variable-name cleanup.

**Validation note**:
- A full integration run (`uv run pytest services/ingestor/tests/integration -q`) still reports failures outside this rename scope (for example `/api/v1/sources` returning `422` in insights/reporting/subscriptions tests, plus an ETL pandas-path failure). These are not caused by the MVP create-function rename.

**Next Step**:
1. Proceed with Phase 1 (Alembic-first schema bootstrap switch).

---

## Open Questions

1. Should `security-full.yml` + `security-codeql-dependency.yml` merge into one `security.yml` (cleaner) or stay separate (less disruption)?
2. Phase 3 and 4 can be done in parallel (independent). User may choose to do only some.
