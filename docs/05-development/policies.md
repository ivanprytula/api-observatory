# Development Policies & Gotchas

Track: A — Product and Onboarding

---

## CI Policy: Merge & Release Gates

### Merge Gate (must be green before merging to `develop`/`main`)
- Ruff lint + format
- mypy type check (`ty`)
- Unit tests
- pip-audit (no CRITICAL/HIGH CVEs)
- Docker build (all services)
- Trivy scan (HIGH+CRITICAL block)
- CodeQL analysis
- Integration tests
- Secrets scan
- Docs-impact gate (service change requires docs update)
- Contracts-versioning gate (schema change requires version bump)

### Release Gate (before `v*` tag on `main`)
- Tag on `origin/main`
- CI passed on the commit
- Image build + push to GHCR (immutable `tree-${SHA}` tag)
- Cosign signing (keyless)
- Provenance attestation + SBOM generation

### Advisory Only (never block)
- Trivy MEDIUM scan
- Daily full audit
- Dependabot-age-guard

**Image promotion model:** Built once in CI (tagged `tree-${SHA}`). Release pulls same candidate. CD deploys by immutable digest.

---

## Dependabot Policy

### Configuration
- `target-branch: develop` on every update block
- Ecosystems covered: `pip`, `uv`, `docker`, `github-actions`
- Explicit schedules, labels, reviewers
- `open-pull-requests-limit` set

### Cooldown Policy
- Python package updates: monthly
- Early releases: `early-dependency` label via age-guard (7-day maturation)
- `uv` config: `exclude-newer = "7 days"` locally
- Security updates may bypass branch policy

---

## GitHub Actions Security

- All `uses:` references pinned to **immutable full commit SHAs** (not `@v4`, `@latest`), with human-readable version comment
- Explicit `permissions:` blocks with least privilege (default: `contents: read`)
- OIDC `id-token: write` only where needed
- Monthly Dependabot checks, quarterly manual audit, annual full review

See `docs/_archive/06-ci-cd/github-actions-security.md` for action SHA reference table and migration guide.

---

## Common Pitfalls (Gotchas)

### Python / Async
- Forgetting `await` — coroutine returns immediately without executing
- Blocking sync code in async handler (use `run_in_executor` for CPU work)
- Connection pool exhaustion with Semaphore(5) — 5 concurrent, not 100

### Database
- **N+1 queries:** SQLAlchemy `selectinload()` for relationships
- **Table bloat:** Long-running transactions prevent VACUUM cleanup. Batch and commit frequently
- **Missing indexes:** Run `EXPLAIN ANALYZE` before blaming Postgres
- **Alembic on async:** Use `async_engine_from_config` + `asyncio.run()` for migration context

### FastAPI / APIs
- Query params without defaults are optional (not required)
- Form data vs JSON body: FastAPI distinguishes by `Form()` vs `Body()` type annotation
- Uncaught `HTTPException` defaults to 500 — always raise explicitly

### Docker / Deployment
- Layer caching order: `pyproject.toml` + `uv.lock` before source code
- Running as root in container — always use `USER appuser` (UID 1001)

### Testing
- Test DB isolation: each test gets its own session, rollback after test
- Async fixtures: `ScopeMismatch` = mixing sync/async scopes

### Security
- Secrets in env vars are visible in process listings
- Never hardcode API keys or connection strings
- Parameterized queries only — no SQL string interpolation

### Observability
- Logging sensitive data (PII, tokens) — redact before logging
- Missing correlation IDs — always propagate `X-CID` header
