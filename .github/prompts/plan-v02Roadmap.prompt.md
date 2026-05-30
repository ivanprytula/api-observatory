## Plan: MVP v0.1 Assessment and v0.2 Scope

You are in a strong MVP+ place for a portfolio-ready vertical slice. The project is already beyond “prototype” and close to “early production candidate,” but v0.2 should focus on trustworthiness (tests/CI/release rigor) before adding many new features.

### Current v0.1 state (what is solid)

1. Core product slice is coherent and documented.
- API observability + drift + scorecards + agent enrichment are clearly positioned in [README.md](../../README.md).
- Architecture and supporting docs are broad and organized under [docs/README.md](../../docs/README.md), [docs/04-architecture-overview.md](../../docs/04-architecture-overview.md), and [docs/design/](../../docs/design/).

2. CI is simplified and practical for MVP speed.
- Lean 3-job CI in [ci.yml](../../.github/workflows/ci.yml): lint, unit-tests, docker-build.
- Good security baseline in [security.yml](../../.github/workflows/security.yml): immutable refs check, pip-audit, CodeQL, Trivy.

3. Release pathway exists.
- Tag-based image publish in [release.yml](../../.github/workflows/release.yml).

4. Secrets scanning is now targeted and lightweight.
- Changed-lines scan in [security-secrets-lite.yml](../../.github/workflows/security-secrets-lite.yml) with artifact output.

### Current v0.1 risks/gaps (what is holding back v0.2 feature expansion)

Status update (implemented baseline for v0.2 start):
1. Fixture topology stabilized with shared fixtures in [tests/fixtures_shared.py](../../tests/fixtures_shared.py), thin tree conftests, and contract doc updates in [docs/dev/testing-fixture-boundaries.md](../../docs/dev/testing-fixture-boundaries.md).
2. CI integration lane includes deterministic dependency health checks and fail-fast diagnostics artifacts in [ci.yml](../../.github/workflows/ci.yml).
3. Release workflow now publishes SBOM, signs images, verifies signatures, and uploads provenance attestations in [release.yml](../../.github/workflows/release.yml).

1. Test architecture is still fragile.
- You recently had fixture coupling issues in service-level tests, indicating fixture ownership/boundaries are not fully stable.
- Unit lane is green now, but it needed local fixture duplication and patching to get there.
- How to address now:
1. Define a single canonical fixture ownership model: shared fixtures only in [tests/conftest.py](../../tests/conftest.py), service-specific fixtures only in [services/ingestor/tests/conftest.py](../../services/ingestor/tests/conftest.py).
2. Remove cross-tree fixture imports and replace with explicit local fixtures or shared reusable factories in one direction only.
3. Add a short fixture contract document that defines what can be imported where.
- Exit criteria:
1. No fixture imports from service tests into top-level tests or vice versa.
2. Unit tests pass without temporary fixture aliases or fallback patches.

2. CI trust gap between unit and integration behavior.
- [ci.yml](../../.github/workflows/ci.yml) only enforces unit marker; integration and e2e remain optional.
- Your own planning notes mention integration failures outside current MVP scope in [plan-postMvpPolish.prompt.md](plan-postMvpPolish.prompt.md).
- How to address now:
1. Add an integration job to [ci.yml](../../.github/workflows/ci.yml) with required service dependencies and deterministic startup checks.
2. Enforce branch policy: unit required for pull requests, integration required on merge to main, e2e scheduled and non-blocking.
3. Add integration fail-fast diagnostics: dependency health logs and artifacted test reports.
- Exit criteria:
1. Integration lane runs on every merge to main and is required.
2. Red integration builds are reproducible locally with one documented command.

3. Release hardening is minimal.
- Release pushes images, but no SBOM/signing/provenance gate in [release.yml](../../.github/workflows/release.yml).
- This is fine for v0.1, but v0.2 should raise supply-chain confidence.
- How to address now:
1. Generate and publish SBOM in the release workflow for every pushed image.
2. Sign release images and verify signatures before publish-complete.
3. Add provenance attestations and keep verification as a required release step.
- Exit criteria:
1. Every release image has attached SBOM and signature artifacts.
2. Release workflow fails if signing or attestation verification fails.

### Immediate execution order for the risks/gaps

1. Week 1: fixture boundary cleanup and fixture contract doc.
2. Week 2: integration lane required on merge to main plus diagnostics.
3. Week 3: release SBOM and signing, then provenance verification.
4. Week 4: one full green cycle across all required lanes before expanding feature scope.

### Recommended v0.2 (what to include)

Prioritize in this order:

1. Reliability track (must-have first)
- Stabilize test fixture topology (single canonical fixture module strategy, no fragile cross-tree imports).
- Add required integration CI lane (Postgres + Redis service containers or testcontainers lane).
- Enforce clear marker policy:
1. unit required on PR
2. integration required on merge to main
3. e2e optional/nightly
- Add minimum coverage threshold on touched packages (pragmatic, not 100%).

2. Operability/security track
- Add release hardening: SBOM generation, image signing, optional provenance attestations.
- Add alerting checks for core SLOs (health/readiness latency, probe success rate, queue lag if enabled).
- Add a CI “smoke deploy” check against docker-compose.prod-like or equivalent.

3. Product track (feature work after gates are trustworthy)
- Strengthen source lifecycle and probe control:
1. per-source pause/resume
2. backoff/cooldown policy visibility
3. probe failure classification
- Expand drift insights:
1. richer severity dimensions
2. better diff metadata
3. scorecard-to-drift correlation endpoint/report

### Suggested v0.2 release shape

1. v0.2.0-alpha.1
- Test/fixture stabilization + integration CI lane only.

2. v0.2.0-alpha.2
- Release security hardening (SBOM/signing) + observability alerting checks.

3. v0.2.0
- Product improvements (source control + drift analytics) once alpha lanes stay green for a full cycle.

### Definition of done for v0.2

1. Required PR gates include unit and integration.
2. No fixture import hacks needed across test trees.
3. Release artifacts are verifiable (at least SBOM + signed image).
4. One new user-visible observability capability ships (not just refactor).

If you want, I can turn this into a concrete commit-by-commit v0.2 plan with exact files and workflow changes, in the same style as your 14a-14d plan.
