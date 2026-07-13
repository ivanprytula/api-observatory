# Security Architecture

Track: B — Engineering Execution

Authentication, authorization, and security controls implemented in this project.
For learning context on the auth patterns, see Pillar 5 Security (design).

---

## Auth Layers

The ingestor service runs four authentication mechanisms in parallel — each scoped to a different API surface.

| Layer          | Scope                              | Mechanism                         |
| -------------- | ---------------------------------- | --------------------------------- |
| HTTP Basic     | `/docs`, `/redoc`, `/openapi.json` | Username + password, env-sourced  |
| Bearer token   | `/api/v1/*`                        | Opaque token, stateless           |
| JWT HS256      | `/api/v2/*`                        | Signed token with role claims     |
| Session cookie | Dashboard / admin UI               | Stateful session, `HttpOnly`      |

Environment variables that control auth:

```bash
DOCS_USERNAME=<value>          # HTTP Basic — username for OpenAPI UI
DOCS_PASSWORD=<value>          # HTTP Basic — password for OpenAPI UI
API_TOKEN=<value>              # Bearer token for v1 routes
JWT_SECRET=<value>             # Signing key for v2 JWT tokens
SESSION_SECRET=<value>         # Session cookie signing key
```

None of these have safe defaults. The service fails fast at startup if any secret is still the
default placeholder value (see [Production Guardrails](#production-guardrails)).

---

## RBAC Roles

Role-based access control applies to v1 and v2 secured endpoints.

Roles (from lowest to highest privilege): `viewer` → `writer` → `admin`

### Role-controlled endpoints

| Endpoint                                         | Minimum role      | Auth mechanism    |
| ------------------------------------------------ | ----------------- | ----------------- |
| `PATCH /api/v1/observations/{observation_id}/secure/archive` | `writer`        | Bearer token      |
| `DELETE /api/v1/observations/{observation_id}/secure/delete` | `admin`         | Bearer token      |
| `POST /api/v2/observations/jwt`                       | `writer`          | JWT claim (`role`) |

For the JWT layer, the role is embedded as the `role` claim in the signed token.
Tokens are verified on every request — no server-side state required.

For the Bearer token layer, role resolution is stateless and tied to the token value
(role stored in the in-memory token registry; not persisted between restarts in the current implementation).

---

## Security Headers Middleware

All HTTP responses from the ingestor include the following headers:

| Header                    | Value                          | Protects against      |
| ------------------------- | ------------------------------ | --------------------- |
| `X-Content-Type-Options`  | `nosniff`                      | MIME sniffing attacks |
| `X-Frame-Options`         | `DENY`                         | Clickjacking          |
| `Referrer-Policy`         | `strict-origin-when-cross-origin` | Referrer leakage    |
| `Permissions-Policy`      | (camera, mic, geolocation off) | Feature policy abuse  |
| `Content-Security-Policy` | (restrictive, no inline)       | XSS                   |

HTTPS enforcement (HSTS) is handled at the reverse proxy / load balancer layer in production.

---

## Production Guardrails

The ingestor service performs a startup check before accepting traffic.
It compares all security-relevant environment variables against known weak/default values.

If any variable is still set to its default placeholder, the service exits immediately
with a clear error message and a non-zero exit code.

This prevents accidental deployment with:

- Demo credentials leaking into production
- Unsigned JWT tokens (empty `JWT_SECRET`)
- Predictable session keys

The check is implemented in `services/ingestor/security/` and runs in the lifespan startup hook.

---

## Input Validation

All inbound request bodies are validated with Pydantic v2 before reaching any handler.
This enforces type, size, and format constraints at the schema layer.

SQL access uses parameterized queries exclusively via SQLAlchemy 2.0 `select()` / `insert()` DSL —
no raw SQL string interpolation.

User-supplied URLs (e.g., webhooks) are validated against an allow-list before the server makes
outbound requests (SSRF mitigation).

---

## CI Security Controls

| Control                  | CI job                 | Trigger      | What it does                              |
| ------------------------ | ---------------------- | ------------ | ----------------------------------------- |
| `pip-audit`              | `python-deps`          | push / PR    | Checks all Python deps for known CVEs     |
| CodeQL SAST              | `codeql`               | push / PR    | Deep static analysis for Python           |
| Trivy image scan         | `docker-scan-security` | push / PR    | Scans built container images for CVEs     |
| `gitleaks`               | `gitleaks-scan`        | PR           | Secret scan over the commit range         |
| `ruff` security rules    | `lint`                 | push / PR    | Lints for security anti-patterns (S rules)|
| SHA-pinned action refs   | all workflows          | —            | Supply chain security for Actions         |
| Scheduled deep audit     | `security-audit`       | daily cron   | Full deps + SAST + image scan (security.yml) |

All GitHub Actions refs in `.github/workflows/` are pinned to full commit SHAs.
See GitHub Actions Security for the
pinning methodology and rotation process.

See Docker Security Scanning Setup for Trivy
configuration and severity thresholds.

---

## OWASP Top 10 Coverage & Review Cadence

This maps OWASP themes (Web Top 10 and API Top 10) to the control that owns them in this repo.
The coding rules behind these controls live in
[security-and-owasp.instructions.md](../../.github/instructions/security-and-owasp.instructions.md);
this table records *which enforcement* covers each theme so gaps are visible.

| OWASP theme | Owned by | Where |
| --- | --- | --- |
| A01 Broken Access Control / API1 BOLA / API5 BFLA | Auth layers + RBAC role checks | [Auth Layers](#auth-layers), [RBAC Roles](#rbac-roles) |
| A02 Cryptographic Failures | Startup guardrail (no default secrets), HS256 signing | [Production Guardrails](#production-guardrails) |
| A03 Injection | Parameterized SQLAlchemy DSL + Pydantic v2 validation | [Input Validation](#input-validation) |
| A04 Insecure Design | *Gap* — no automated control | trigger: yearly OWASP review |
| A05 Security Misconfiguration | Security headers middleware + `bandit` (`B*` rules) | [Security Headers](#security-headers-middleware), `bandit` hook |
| A06 Vulnerable & Outdated Components | `pip-audit` (`python-deps`) + Trivy (`docker-scan-security`) + Dependabot | [CI Security Controls](#ci-security-controls) |
| A07 Identification & Authentication Failures | Auth layers, `HttpOnly` session cookie, basic rate limiting | [Auth Layers](#auth-layers) |
| A08 Software & Data Integrity Failures | SHA-pinned action refs + frozen lockfile (`uv sync --frozen`) | [CI Security Controls](#ci-security-controls) |
| A09 Logging & Monitoring Failures | *Partial* — OTel traces; no security alerting | trigger: yearly OWASP review |
| A10 SSRF / API7 SSRF | Outbound URL allow-list | [Input Validation](#input-validation) |
| API4 Unrestricted Resource Consumption | *Partial* — basic rate limit, not per-tenant | see [Planned](#planned--not-yet-implemented) |
| (all categories — deep static analysis) | CodeQL (`codeql`) | [CI Security Controls](#ci-security-controls) |
| (all categories — secret leakage) | `gitleaks` (`gitleaks-scan`) | [CI Security Controls](#ci-security-controls) |

Acknowledged gaps carry an explicit trigger rather than being silent. A04 and A09 are design/process
themes a scanner cannot fully own; they are reassessed at the yearly review. API4 is tracked as a
Planned control below.

### Yearly OWASP Review

Every **June**, re-read the current OWASP Web Top 10 and API Security Top 10 and reconcile this table
with them:

1. Confirm each owned control still maps to a current category (categories are renumbered between
   editions).
2. Update the rows; for any newly relevant theme with no control, add a row marked *Gap* with a
   trigger.
3. File each real gap as an issue. Add a new scanner **only** to close a named gap — never
   preemptively (this respects the [baseline-checklist](baseline-checklist.md) "new tooling only on
   a named gap" rule).

---

## Planned / Not Yet Implemented

| Control                           | Status  | Notes                                  |
| --------------------------------- | ------- | -------------------------------------- |
| Cache-backed session store        | Planned | Currently in-process; lost on restart  |
| Full persisted auth flows         | Planned | Registration, refresh tokens           |
| Broader RBAC coverage             | Planned | Extend role checks to more endpoints   |
| Rate limiting per tenant          | Planned | Basic rate limit exists; not per-user  |
| mTLS between services             | Planned | Service-to-service auth                |

---

## Related

- Architecture Overview — full auth/RBAC table in context
- Pillar 5 Security (design) — deep auth pattern learning reference
- GitHub Actions Security — CI SHA pinning
- Docker Security Scanning Setup — Trivy setup
