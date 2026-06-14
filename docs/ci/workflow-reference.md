# CI Workflow Reference

Track: B — Engineering Execution

Practical reference for the GitHub Actions pipeline. For deployment strategy, IaC, and GitOps
design, see [cicd-iac-gitops-portable-strategy.md](../cicd-iac-gitops-portable-strategy.md).

---

## Workflow File

`.github/workflows/ci.yml`

---

## Trigger Model

| Event                    | What runs                   |
| ------------------------ | --------------------------- |
| `pull_request`           | Waves 0–3, then 5–6 (fast path) |
| `push` to any branch     | Same as pull_request        |
| `workflow_dispatch`      | All waves including Wave 4 (slow checks) |

Wave 4 (migrations, integration, e2e, compose smoke) is gated behind `workflow_dispatch`
(or a `run_slow_checks` input) to keep PR feedback fast.

---

## Wave Structure

The pipeline is split into sequential waves. Within each wave, jobs run in parallel.

### Wave 0 — Change Impact

**Job**: `change-impact`

Detects which services and subsystems changed using path filters.
All Wave 1 jobs depend on this output to skip or run downstream work.

Always runs, no dependencies.

### Wave 1 — Infrastructure and Gate Jobs

Runs after Wave 0 in parallel:

| Job                            | Purpose                                                   |
| ------------------------------ | --------------------------------------------------------- |
| `build-prebuilt-image`         | Builds (or pulls) the prebuilt CI image                   |
| `set-service-version`          | Computes semantic version from `pyproject.toml` + git tag |
| `service-matrix`               | Produces a matrix of changed services for later jobs      |
| `docs-impact-gate`             | Fails if service code changed but docs were not touched   |
| `impact-summary`               | Annotates the PR with a human-readable change summary     |
| `contracts-versioning-gate`    | Ensures API contract changes include a version bump       |
| `gateway-service-discovery-guard` | Validates gateway routes match registered services     |

### Wave 2 — Prechecks

**Job**: `prechecks` (runs after `build-prebuilt-image`)

Runs all fast static analysis inside the prebuilt CI image:

- `ruff check` — lint and import sort
- `ruff format --check` — format check (no auto-fix in CI)
- `ty check` — type checking (Pyright-based)
- `python -m compileall` — syntax validation

If `prechecks` fails, no further jobs run (unit, integration, images are all blocked).

### Wave 3 — Unit Tests and Schema Guards

Runs after `prechecks` in parallel:

| Job                        | Purpose                                         |
| -------------------------- | ----------------------------------------------- |
| `unit`                     | `pytest tests/` with the in-memory test DB      |
| `outbox-inbox-schema-guard`| Validates outbox/inbox message schema contracts |

### Wave 4 — Slow Checks (workflow_dispatch only)

Runs after Wave 3, only when `run_slow_checks` is true:

| Job                   | Purpose                                              |
| --------------------- | ---------------------------------------------------- |
| `migrations`          | Runs Alembic upgrade + downgrade against a live DB   |
| `integration`         | `pytest tests/integration/` with Docker Compose up   |
| `e2e`                 | End-to-end tests against the full stack              |
| `compose-smoke-test`  | Spins up `docker-compose.yml`, checks all healthchecks |

### Wave 5 — Audit and Image Build

Runs after `e2e` (or after Wave 3 on PR/push):

| Job                | Purpose                                           |
| ------------------ | ------------------------------------------------- |
| `dependency-audit` | `pip-audit` — checks all deps for CVEs            |
| `build-images`     | Builds service images, runs Trivy scan, pushes to GHCR |

### Wave 6 — Summary

**Job**: `build-summary` (runs after `build-images`)

Collects all wave outcomes and writes a PR status summary comment with image digests.

---

## Prebuilt CI Image

All jobs run inside `ghcr.io/${{ github.repository_owner }}/data-pipeline-ci`.

The image provides:

- Python 3.14
- `uv` pre-installed
- All project dependencies pre-cached as wheels
- `ruff`, `ty`, and test tooling available without install step

This eliminates per-job `pip install` time (typically saves 60–90 seconds per job).

See [ci/prebuilt-ci-image.md](prebuilt-ci-image.md) for:

- How to build and push a new version of the prebuilt image
- How to pin the image to a specific digest
- How to roll back a bad image

---

## Running CI Steps Locally

Simulate Wave 2 prechecks locally:

```bash
# Lint check (no fix)
uv run ruff check .

# Format check (no fix)
uv run ruff format --check .

# Type check
uv run ty check

# Syntax validation
uv run python -m compileall services/ libs/ -q
```

Run unit tests:

```bash
uv run pytest tests/ -x -q
```

Run with coverage:

```bash
uv run pytest tests/ --cov=services --cov=libs --cov-report=term-missing
```

Run slow checks locally (requires Docker):

```bash
just up          # start compose stack with direct HTTP API by default
just migrate     # run Alembic migrations
just test-int    # integration tests
just down        # tear down

# Optional HTTPS parity for slow checks that use local URL helpers
LOCAL_API_SCHEME=https just up-https
LOCAL_API_SCHEME=https just api-test
```

---

## Common CI Failures

### Prechecks — ruff lint error

```text
error[E501]: Line too long (120 > 119 characters)
```

Fix locally: `uv run ruff check --fix .` then commit.

### Prechecks — ruff format error

```text
Would reformat: services/ingestor/main.py
```

Fix locally: `uv run ruff format .` then commit.

### Prechecks — ty check error

Usually a missing return type annotation or mismatched `Annotated` type.
Read the full `ty` output — it prints the exact file, line, and expected type.

### Unit tests — async fixture error

If you see `ScopeMismatch` or `RuntimeError: no event loop`, check that the test file uses `asyncio_mode = auto` (set globally in `pyproject.toml`) and does not manually mark coroutines with `@pytest.mark.asyncio`.

### docs-impact-gate blocked

The gate fails when a service changed but no docs file in `docs/` was updated.
Add or touch a relevant doc file in the same PR.

### contracts-versioning-gate blocked

An API schema changed without a version bump in `pyproject.toml` or the schema file.
Bump the version and update the contract file.

---

## Branch Model

| Branch         | Role                                  |
| -------------- | ------------------------------------- |
| `main`         | Stable, deployable                    |
| `develop`      | Default integration branch            |
| `feature/*`    | Feature development, merged to develop |
| `fix/*`        | Bug fixes, merged to develop or main  |

All PRs target `develop`. `main` receives only tested, reviewed merges from `develop`.

---

## Related

- [cicd-iac-gitops-portable-strategy.md](../cicd-iac-gitops-portable-strategy.md) — deployment strategy, IaC, GitOps design
- [ci/prebuilt-ci-image.md](prebuilt-ci-image.md) — prebuilt CI image lifecycle
- [github-actions-security-hardening.md](../github-actions-security-hardening.md) — SHA pinning for action refs
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml) — source of truth
