# Security Architecture

Track: B — Engineering Execution

Authentication, authorization, and security controls implemented in this project.
For learning context on the auth patterns, see Pillar 5 Security (design).

---

## Auth Layers

Production v1 uses signed JWTs, role guards, and tenant claims. The older authentication
mechanisms remain available only in the opt-in learning lab, gated by
`AUTH_DEMO_ROUTES_ENABLED=true`.

| Layer          | Scope                              | Mechanism                         |
| -------------- | ---------------------------------- | --------------------------------- |
| HTTP Basic     | `/docs`, `/redoc`, `/openapi.json` | Username + password, env-sourced  |
| JWT HS256      | `/api/v1/*` production routes      | Signed token with role and tenant claims |
| Learning lab   | `/api/v1/observations/auth/login`, `/api/v1/observations/{id}/secure`, `/api/v2/observations/*` | Session cookie, fixed-window/token-bucket/sliding-window rate limiting; disabled by default |
| Session cookie | Dashboard / admin UI               | Stateful session, `HttpOnly`      |

Authentication settings and their environment mappings are owned by
[`config.py`](../../services/ingestor/core/config.py); safe configuration shape is documented in
[`.env.example`](../../.env.example). This includes optional documentation credentials, JWT
signing keys, and the opt-in authentication lab flag.

None of these have safe defaults. The service fails fast at startup if any secret is still the
default placeholder value (see [Production Guardrails](#production-guardrails)).

---

## RBAC Roles

Role-based access control applies to production v1 routes.

Roles (from lowest to highest privilege): `viewer` → `writer` → `admin`

### Role-controlled endpoints

| Endpoint                                         | Minimum role      | Auth mechanism    |
| ------------------------------------------------ | ----------------- | ----------------- |
| Production v1 reads and normal writes | authenticated / `writer` | JWT claim (`role`) |
| Administrative v1 operations | `admin` | JWT role claim |
| Session-protected routes (learning lab) | `writer` / `admin` | Session cookie + role guard |

The signed JWT carries both role and tenant claims. Tenant middleware accepts the verified
claim in preference to `X-Tenant-ID`, so a request header cannot override tenant context.
Tokens are verified on every request — no server-side state is required for access checks.

The session endpoints live on `observations.demo_router` and are
only mounted when `auth_demo_routes_enabled` is `True`. They are not part of the
production surface.

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

The check is implemented in `services/ingestor/core/security/` and runs in the lifespan startup hook.

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

| Control                | Owner              | Trigger   | What it does                          |
| ---------------------- | ------------------ | --------- | ------------------------------------- |
| `gitleaks`             | `CI / Quality`     | push / PR | Blocks committed secrets              |
| `ruff` security rules  | `CI / Quality`     | push / PR | Lints security anti-patterns          |
| SHA-pinned action refs | `CI / Quality`     | push / PR | Guards the Actions supply chain       |
| `pip-audit`            | Manual Assurance   | manual    | Audits locked Python dependencies     |
| CodeQL SAST            | Manual Assurance   | manual    | Performs deep Python static analysis  |
| Trivy image scans      | Manual Assurance   | manual    | Reports vulnerabilities in each image |

All GitHub Actions refs in `.github/workflows/` are pinned to full commit SHAs.
See GitHub Actions Security for the
pinning methodology and rotation process.

See Docker Security Scanning Setup for Trivy
configuration and severity thresholds.

---

## OWASP Top 10 Coverage & Review Cadence

This maps OWASP themes (Web Top 10 and API Top 10) to the control that owns them in this repo.
The coding rules behind these controls live in
[security-and-owasp.instructions.md](../../../agent-forge/instructions/security-and-owasp.instructions.md);
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
| API4 Unrestricted Resource Consumption | Token bucket keyed by tenant and subject | [Auth Layers](#auth-layers) |
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
| Cache-backed session store        | Implemented | Cache is used when enabled; startup fails closed for the rate limiter if unavailable |
| Full persisted auth flows         | Implemented | Registration and refresh-token rotation are available |
| Broader RBAC coverage             | Implemented | Default mounted v1 routers have JWT and role dependencies |
| Rate limiting per tenant          | Implemented | Atomic Redis token bucket, keyed by tenant and subject |
| PostgreSQL tenant RLS             | Opt-in | `RLS_ENABLED=true` protects observations and dependency incidents; global rows remain visible and administrators retain cross-tenant API access. Each additional table requires its own migration and PostgreSQL proof |
| mTLS between services             | Planned | Service-to-service auth                |

---

## Related

- Architecture Overview — full auth/RBAC table in context
- Pillar 5 Security (design) — deep auth pattern learning reference
- GitHub Actions Security — CI SHA pinning
- Docker Security Scanning Setup — Trivy setup
