# Security Architecture

Track: B — Engineering Execution

Authentication, authorization, and security controls implemented in this project.
For learning context on the auth patterns, see [pillar-5-security.md](design/pillar-5-security.md).

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

| Control                  | CI job               | Wave  | What it does                              |
| ------------------------ | -------------------- | ----- | ----------------------------------------- |
| `pip-audit`              | `dependency-audit`   | 5     | Checks all Python deps for known CVEs     |
| Trivy image scan         | `build-images`       | 5     | Scans built container images for CVEs     |
| SHA-pinned action refs   | all workflows        | —     | Supply chain security for Actions         |
| `ruff` security rules    | `prechecks`          | 2     | Lints for security anti-patterns (S rules)|

All GitHub Actions refs in `.github/workflows/` are pinned to full commit SHAs.
See [github-actions-security-hardening.md](github-actions-security-hardening.md) for the
pinning methodology and rotation process.

See [docker-security-scanning-setup.md](setup/docker-security-scanning-setup.md) for Trivy
configuration and severity thresholds.

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

- [Architecture Overview](04-architecture-overview.md) — full auth/RBAC table in context
- [pillar-5-security.md](progress/pillar-5-security.md) — deep auth pattern learning reference
- [github-actions-security-hardening.md](github-actions-security-hardening.md) — CI SHA pinning
- [docker-security-scanning-setup.md](setup/docker-security-scanning-setup.md) — Trivy setup
