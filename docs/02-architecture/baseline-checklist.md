# Baseline Checklist — Never-Regress Application Controls

Track: B — Engineering Execution

This is the single, consolidated reference for the application controls that must never regress.
It does not re-teach ACROSS, OWASP, or testing conventions — it *cites* the real control that
enforces each item (a `pyproject.toml` tool config, a pre-commit hook id, a CI job name, an OWASP
rule, a `Dockerfile` line, or an ADR). Scattered controls live in many files; this list points at
all of them from one place so they stay enforced as the project grows.

Scope is Track B (engineering execution) with Track C touch-points (data/API design). The platform
half of the baseline (Terraform, Kubernetes, SRE, GitOps) is owned by the sibling infra repo — see
[Sibling repo](#sibling-repo).

## Never-Regress Stance

An item on this list is **table stakes**, not a feature to be scoped or deferred.

ACROSS "Simple As Possible" and anti-overengineering (see [CLAUDE.md](../../CLAUDE.md) and
[AGENTS.md](../../AGENTS.md)) govern **feature scope** — they decide what *new behavior* is worth
building. They never govern this baseline. You do not "YAGNI" a quality gate, a secret scan, or a
non-root container. If an item here is failing, that is a regression to fix, not a trade-off to
weigh.

How this differs from the planning docs:

- [evolution-playbook.md](../03-planning/evolution-playbook.md) decides *how to evolve* (decision
  flow, change types, governance). This list is the floor that evolution must not sink below.
- [mvp-roadmap.md](../03-planning/mvp-roadmap.md) decides *what ships in which phase*. This list
  applies in every phase, MVP included.

New tooling is added to this baseline **only** to close a named gap (see
[Flagged Gaps](#flagged-gaps) and the OWASP review cadence), never preemptively.

## Testing & Quality Gates

- [ ] **Format + lint pass** — `ruff-format` and `ruff-check` hooks
      ([.pre-commit-config.yaml](../../.pre-commit-config.yaml)) and the `lint` CI job
      ([.github/workflows/ci.yml](../../.github/workflows/ci.yml)). Config: `[tool.ruff]`
      (`line-length = 88`, `target-version = "py314"`) and `[tool.ruff.lint]`
      (`select = ["E", "F", "I", "UP", "B", "SIM"]`) in [pyproject.toml](../../pyproject.toml).
- [ ] **Type-check is clean** — `ty` local hook (`uv run ty check`) and `[tool.ty.overrides]`
      (`include = ["services/ingestor", "tests"]`) in [pyproject.toml](../../pyproject.toml).
- [ ] **Unit tests pass on SQLite** — `unit-tests` CI job; `[tool.pytest.ini_options]` with
      `asyncio_mode = "auto"` and `addopts = "… -m 'not e2e'"` in
      [pyproject.toml](../../pyproject.toml).
- [ ] **Integration tests pass on real PostgreSQL + Redis** — `integration-tests` CI job using
      testcontainers for ephemeral PG/Redis (not mocks).
- [x] **Protected v1 OpenAPI contract is gated** — `contract-tests` runs Schemathesis against the
      in-process ASGI application, requiring every documented protected `/api/v1/*` operation to
      reject an anonymous generated request with its documented JSON `401` response. The public
      registration, login, refresh, and logout routes are deliberately excluded.
- [ ] **End-to-end tests are gated, not skipped silently** — `e2e` marker excluded from the default
      run (`-m 'not e2e'`) and run explicitly where applicable.
- [ ] **Coverage is measured on the ingestor** — `[tool.coverage.run]`
      (`source = ["services.ingestor"]`, `branch = true`) in [pyproject.toml](../../pyproject.toml);
      reported via `--cov=services/ingestor`.
- [ ] **`inference` has its own integration test suite** — `services/inference/tests/` runs against
      real pgvector-enabled Postgres (no SQLite fallback — `Vector` columns need the extension) via
      its own `conftest.py` reusing the shared testcontainers fixture; embeddings are mocked
      deterministically so tests don't depend on network/model download. Not yet wired into the
      root `--cov` config (tracked as a gap, not measured today). Its downgrade fixture is scoped to
      only its own tables (`command.downgrade(cfg, "base")`, not `DROP SCHEMA public CASCADE`) since
      it shares the session-scoped test Postgres with the ingestor's own suite — the ingestor's
      equivalent fixture (`tests/fixtures_shared.py::_alembic_downgrade`) re-enables the `vector`
      extension after its own schema recreate for the same reason.
- [x] **The LangGraph agent has a dedicated test suite** (closes gap 🟠#7 from
      `docs/03-planning/audit-gaps.md` for node/graph-level coverage) —
      `services/ingestor/tests/unit/agent/` (nodes + full graph pause/resume cycle via
      `MemorySaver`, LLM/RAG/notification calls mocked) and
      `services/ingestor/tests/integration/test_agent_router.py` (GET/resume HTTP contract). All
      run with zero network dependency and zero API cost. The mechanics these tests exercise
      (Postgres checkpointer, real Anthropic structured output, RAG retrieval finding a prior
      indexed incident) were additionally verified live against the real stack — see
      `docs/.plans/ai-augmented-observatory-agent-mcp.md` Phase 3 Status Log.
- [x] **`services/mcp` has its own unit test suite** (Phase 5 of
      `docs/.plans/ai-augmented-observatory-agent-mcp.md`) — `services/mcp/tests/` mocks the
      ingestor's HTTP responses via `respx` at the transport boundary; no DB, no testcontainers,
      since this service holds no state of its own. Not in root `testpaths`/`--cov`, matching the
      existing `services/inference/tests/` precedent above, not a new gap. No `/health`/`/metrics`
      endpoint — it's a stdio process, not a long-running server (see `app-repo-contract.md`'s
      Health & Probes section) — verified live against the real stack (real login, real reads,
      real 409 on an invalid resume) in the same session, not just against mocks.
- [ ] **Every endpoint has the three-test set** — happy path (2xx, full-shape assertion), not-found
      (404), validation error (422) — and uses the `AsyncClient` + `ASGITransport` pattern. See
      [fastapi-testing.instructions.md](../../.github/instructions/fastapi-testing.instructions.md).
- [ ] **Pre-commit parity with CI** — the same `ruff`, `bandit`, `gitleaks`, and `hadolint` checks
      run locally ([.pre-commit-config.yaml](../../.pre-commit-config.yaml)) and in CI; the
      `ci-gate` job aggregates the required checks.

## App Security (OWASP / SAST / Deps)

- [ ] **SAST clean (Python)** — `bandit` hook + `[tool.bandit]`
      (`exclude_dirs = ["tests", ".venv", "venv"]`) in [pyproject.toml](../../pyproject.toml).
- [ ] **Deep SAST clean** — `codeql` CI job (CodeQL analyze, Python) in
      [.github/workflows/ci.yml](../../.github/workflows/ci.yml), plus the scheduled `codeql-audit`
      job in [.github/workflows/security.yml](../../.github/workflows/security.yml).
- [ ] **No known-vulnerable dependencies** — `pip-audit` hook + the `python-deps` CI job; daily
      `security-audit` in [.github/workflows/security.yml](../../.github/workflows/security.yml).
- [ ] **No secrets committed** — `gitleaks` hook + the `gitleaks-scan` job in
      [.github/workflows/security-secrets-lite.yml](../../.github/workflows/security-secrets-lite.yml).
- [ ] **OWASP Top 10 + API Top 10 controls applied** — coding rules in
      [security-and-owasp.instructions.md](../../.github/instructions/security-and-owasp.instructions.md);
      theme→control mapping and review cadence in
      [security-architecture.md](security-architecture.md#owasp-top-10-coverage--review-cadence).
- [ ] **SSRF guard on user-supplied URLs** — outbound requests validated against an allow-list
      before the server fetches (see Input Validation in [security-architecture.md](security-architecture.md)).
- [ ] **Secrets read from environment, never files or logs** — app reads `os.environ`; no secret
      values in logs (see Security in [app-repo-contract.md](../07-deployment/app-repo-contract.md));
      startup guardrail rejects default placeholders (see Production Guardrails in
      [security-architecture.md](security-architecture.md)).
- [ ] **Auth layers enforced per API surface** — HTTP Basic for docs, Bearer for `/api/v1/*`, JWT
      HS256 for `/api/v2/*`, session cookie for the UI (see Auth Layers in
      [security-architecture.md](security-architecture.md)).

## Data & API Design

- [ ] **Migrations are forward-only and run before rollout** — Alembic ([alembic.ini](../../alembic.ini),
      `alembic/versions/`); one-shot migration runner before service start
      ([ADR 007](adr/007-migration-runner-vs-sidecar.md)).
- [ ] **API surfaces are versioned** — `/api/v1` and `/api/v2` namespaces (see Auth Layers in
      [security-architecture.md](security-architecture.md)); a breaking change ships a new version,
      not a mutated one.
- [ ] **DTO boundaries are explicit (Pydantic v2)** — request bodies validated at the schema layer
      before any handler (see Input Validation in [security-architecture.md](security-architecture.md)).
- [ ] **Cross-service contracts are versioned** — [libs/contracts/VERSION](../../libs/contracts/VERSION)
      bumped with [libs/contracts/CHANGELOG.md](../../libs/contracts/CHANGELOG.md) on any contract
      change.
- [ ] **Service-boundary import rule holds** — services import only `libs.contracts` and
      `libs.platform` across boundaries; no reaching into another service's internals or reading its
      DB columns directly.
- [ ] **Eventing is idempotent** — Redpanda/Kafka topics ([ADR 001](adr/001-kafka-vs-rabbitmq.md));
      consumers dedupe via `ProcessedEvent` / `InboxConsumption` and publish via the transactional
      `OutboxEvent` (`services/ingestor/models.py`).
- [x] **Observation retention is bounded and operator-controlled** — one verified batch copies
      eligible observations to `observations_archive` before deleting them from the hot table;
      archival is disabled by default and requires both `RETENTION_ENABLED=true` and the CLI
      `--apply` flag ([jobs.py](../../services/ingestor/jobs.py),
      [run-retention.py](../../scripts/run-retention.py)).

## Runtime & Supply Chain

- [ ] **Image is multi-stage with a pinned base digest** — `python:3.14-slim@sha256:…` and a
      builder/final split ([Dockerfile](../../Dockerfile),
      [services/inference/Dockerfile](../../services/inference/Dockerfile);
      [ADR 004](adr/004-docker-buildkit-and-security-scanning.md)).
- [ ] **Dependencies installed frozen, no dev deps in final** — `uv sync --no-dev --frozen`
      ([Dockerfile](../../Dockerfile)).
- [x] **Container runs non-root as UID 10001** — `USER appuser` ([Dockerfile](../../Dockerfile),
      [services/dashboard/Dockerfile](../../services/dashboard/Dockerfile),
      [services/inference/Dockerfile](../../services/inference/Dockerfile)), matching
      `runAsUser: 10001` in [app-repo-contract.md](../07-deployment/app-repo-contract.md).
- [ ] **Secrets sourced via `secretKeyRef`, delivery mechanism owned by infra** — production Key
      Vault sync pattern (CSI Secret Store driver or External Secrets Operator) documented in
      [app-repo-contract.md](../07-deployment/app-repo-contract.md#secret-source-in-production).
- [ ] **Image is scanned for CVEs** — Trivy via the `docker-scan-security` CI job
      ([.github/workflows/ci.yml](../../.github/workflows/ci.yml)) and the scheduled `docker-scan`
      job in [.github/workflows/security.yml](../../.github/workflows/security.yml).
- [ ] **Tags are `tree-<SHA>`, never `latest` in prod** — see CI/CD Image Tagging in
      [app-repo-contract.md](../07-deployment/app-repo-contract.md).
- [ ] **Compose runtime drops privileges** — `security_opt: [no-new-privileges:true]` and
      `cap_drop: [ALL]` for application services.
- [ ] **Health and readiness contract is honoured** — `GET /health` (liveness) and `GET /readyz`
      (readiness, checks DB/broker) on the service's port; non-root + read-only-rootfs compatible.
      See [app-repo-contract.md](../07-deployment/app-repo-contract.md).

## Flagged Gaps

These are known deviations surfaced here so they are tracked, not silently carried. They are
**not** fixed in the docs PR that introduced this checklist — each needs its own change with its own
testing.

| Gap | Current state | Contract / expectation | Follow-up |
| --- | --- | --- | --- |
| Stale CI job names in security doc | [security-architecture.md](security-architecture.md) "CI Security Controls" previously cited `dependency-audit` / `build-images` / `prechecks` | Real jobs are `python-deps` / `docker-build` + `docker-scan-security` / `lint` ([.github/workflows/ci.yml](../../.github/workflows/ci.yml)) | Corrected in-place in the PR that added this checklist; logged here so the drift cause (doc/CI rename skew) is tracked. |

**Resolved:** Container UID mismatch (Dockerfile baked 1001 vs. contract's 10001) — fixed by aligning
both [Dockerfile](../../Dockerfile) and [services/dashboard/Dockerfile](../../services/dashboard/Dockerfile)
to `useradd --uid 10001`.

## Sibling Repo

The sibling infra repo (`api-observatory-infra`:
`docs/architecture/evolution-plan.md` and `docs/architecture/baseline-checklist.md`) owns the
**platform** half of the baseline — Terraform, Kubernetes, SRE, and GitOps controls. This repo owns
the **application** half above. The shared boundary both halves cite is
[app-repo-contract.md](../07-deployment/app-repo-contract.md) (UID, `/health` + `/readyz`, non-root,
`tree-<SHA>` tagging). Keep the two checklists complementary, not overlapping: container/runtime
*expectations* live in the contract; how the app *satisfies* them lives here; how the platform
*enforces* them lives in infra.

## Maintenance

This list is kept current through the update triggers in [CLAUDE.md](../../CLAUDE.md) (Plan
Maintenance) and the yearly OWASP review in
[security-architecture.md](security-architecture.md#owasp-top-10-coverage--review-cadence). When you
add a service, a dependency, or advance a roadmap phase, revisit the rows that control names — do not
let a rename silently orphan a citation.
