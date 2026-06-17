# Pillar 5: Security

Track: E — Archive and Historical Snapshots

**Tier**: Middle (🟡) → Senior (🔴)
**Project**: Required for any public API

---

## Current Repository Implementation Status

Implemented baseline in this repository:

- RBAC guard helpers for session and JWT auth paths.
- Role-aware protected routes for secure archive/delete and JWT-protected writes.
- Security headers middleware on all responses.
- Production startup guardrails that reject weak default secrets.
- `users` table added via Alembic migration as foundation for persisted auth.
- Unit/integration coverage for RBAC behaviors and security headers.

Not implemented yet (planned hardening):

- Cache-backed persistent session store (current session store is in-memory for learning scope).
- Full persisted user auth flows (registration, credential verification, logout/session revocation).
- Broader RBAC coverage across all write/admin endpoints.

See also:

- Roadmap (personal)
- Architecture Overview

---

## Authentication Mechanisms

This project demonstrates three distinct auth patterns for different use cases:

### 1. HTTP Basic Auth (Documentation)

**Use case:** Protecting sensitive documentation endpoints (`/docs`, `/redoc`, `/openapi.json`).

#### Mechanism

- Credentials embedded in `Authorization: Basic base64(user:pass)` header
- No server state (credentials validated against environment variables)
- No expiry; credentials must be manually rotated

#### Production hardening

- Always use HTTPS (never HTTP)
- Rotate credentials quarterly
- Store secrets in Secrets Manager (AWS, Vault, not .env)
- Set rate limits on docs endpoints separately (e.g., 1 req/sec per IP)
- Log all auth attempts (success + failure)
- Place behind ALB or edge for centralized auth logging

**Best practice:** Use 2-3 overlapping keys with grace periods during rotation.

---

### 2. Bearer Token (v1 API, Stateless)

**Use case:** Service-to-service or static token authentication. No server-side session needed.

#### Mechanism

- Static `Authorization: Bearer <token>` header
- Validated via exact string match (no lookup, no expiry)
- Simple but cannot be revoked before expiry

#### Production hardening

- No static bearer tokens in production (cannot revoke)
- Solution: **Key versioning**
  - Maintain N active keys (e.g., current + 1 old)
  - Every 30 days: generate new key, promote to "current"
  - Old key gets grace period (7 days) before deactivation
  - Clients update config within grace period
- Alternative: **API Key Service**
  - Issue short-lived API keys stored in database
  - Keys have: issue_time, expiry, last_used, revoked_at columns
  - Instant revocation without client update
  - Lookup key in cache (Cache) or database on each request
- Anonymize rate-limit keys: map token to client_id instead of IP
- Token format best practice: `sk_prod_v1_abc1234567890...` (type + env + version + random)

---

### 3. Session-Based Auth (v1 API, Stateful)

**Use case:** Traditional web apps, browser-based UIs, need immediate revocation.

#### Mechanism

- Server generates session ID and stores in Cache (or database)
- `session_id` cookie sent to client (HttpOnly, Secure, SameSite=Strict)
- Client returns cookie on future requests
- Server looks up session in Cache and validates TTL

#### Production hardening

- Use Cache (not in-memory dict) for session store
- Set TTL on session key (expire after N hours of inactivity)
- Use secure cookie flags: `HttpOnly=true` (no JS access), `Secure=true` (HTTPS only), `SameSite=Strict` (CSRF protection)
- On logout: `DELETE session:{session_id}` from Cache (immediate revocation)
- Monitor session count as metric (detect credential stuffing)
- Use rotating session IDs: generate new ID on privilege escalation

#### Decision tree

```text
Need to revoke NOW (not at expiry)?           -> Session-based (Cache)
Need stateless (no server lookup)?             -> Bearer token (with key versioning)
Multiple services, shared auth?                -> JWT (with refresh tokens)
Documentation only, no revocation needed?      -> HTTP Basic Auth
```

---

## Middle Tier (🟡)

### Authentication / Authorization

**JWT (JSON Web Tokens)**:

```python
from datetime import datetime, timedelta
from jose import JWTError, jwt

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

def create_access_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

**OAuth2 with FastAPI**:

```python
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = verify_credentials(form_data.username, form_data.password)
    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/observations")
async def list_observations(token: str = Depends(oauth2_scheme)):
    user_id = await verify_token(token)
    # User is authenticated
```

**RBAC (Role-Based Access Control)**:

```python
async def require_admin(user_id: int) -> User:
    user = await db.get(User, user_id)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

@app.delete("/observations/{id}")
async def delete_observation(observation_id: int, user: User = Depends(require_admin)):
    # Only admin can delete
```

#### When to use each auth mechanism

- HTTP Basic Auth: Protecting internal dashboards, documentation
- Bearer Token: API keys for services, automation, integrations (with key versioning)
- Session-Based: Browser clients, user-facing apps (need revocation)
- JWT: Multi-service auth, SPA frontends (with refresh tokens and short TTL)

---

### Input Validation & Injection Prevention

**Pydantic** validates at boundary:

```python
class RecordRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=255)
    timestamp: str  # Validated as ISO 8601
    data: dict = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v):
        from datetime import datetime
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("Invalid ISO 8601")
        return v
```

**SQL Injection prevention** (always use ORM or parameterized queries):

```python
# SAFE: ORM handles parameterization
stmt = select(Record).where(Record.source == user_input)
records = await db.scalars(stmt)

# UNSAFE: string concatenation (never do this)
stmt = f"SELECT * FROM records WHERE source = '{user_input}'"  # ❌
```

---

### API Hardening

**CORS** (restrict domains):

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myapp.com"],  # NOT "*"
    allow_methods=["GET", "POST"],
    allow_credentials=True,
)
```

**Security Headers**:

```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

**Rate Limiting** (see Pillar 1) prevents brute force on `/login`

---

## Senior (🔴)

### HMAC Webhook Verification

```python
import hmac
import hashlib

@app.post("/webhooks/stripe")
async def handle_webhook(request: Request):
    signature = request.headers.get("X-Signature-256")
    body = await request.body()

    expected = hmac.new(
        b"webhook-secret",
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Process webhook
```

---

### Docker Security

**Always use**:

```dockerfile
FROM python:3.14-slim
USER appuser  # Non-root
RUN useradd -m appuser
```

In Kubernetes:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
```

---

### CI Secret Scanning

Use `gitleaks` or `truffleHog` in GitHub Actions:

```yaml
- uses: gitleaks/gitleaks-action@v2
```

Prevents accidentally committing API keys

---

## You Should Be Able To

✅ Implement JWT authentication + refresh tokens
✅ Add CORS + security headers
✅ Validate all input with Pydantic
✅ Explain SQL injection + why parameterized queries prevent it
✅ Implement RBAC with role checks
✅ Verify HMAC webhook signatures
✅ Run secret scanning in CI
✅ Explain why `os.environ["SECRET"]` is wrong (use Secrets Manager)

---

## References

- [python-jose](https://github.com/mpdavis/python-jose)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [gitleaks](https://github.com/gitleaks/gitleaks)

---

## Checklist — Pillar 5: Security

### Foundation 🟢

- [ ] Describe JWT structure: header.payload.signature
  - [ ] Know what `alg`, `exp`, `sub`, `iss` claims mean
  - [ ] Know that the payload is Base64-encoded but NOT encrypted
- [ ] Implement `X-API-Key` header auth with `Depends()` in FastAPI
- [ ] List OWASP Top 10 from memory (at least 5)
  - [ ] Know: Injection (A03), Broken Auth (A07), IDOR (A01), SSRF (A10)
- [ ] Use parameterized queries (never string interpolation for SQL)

### Middle 🟡

- [ ] Explain OAuth2 flows: authorization code vs client credentials
  - [ ] Know client credentials = machine-to-machine, no user interaction
- [ ] Implement RBAC: role assignment → permission check in a FastAPI dependency
- [ ] Explain short-lived access tokens + refresh token pattern
  - [ ] Know that short TTL (15 min) limits blast radius of a stolen token
- [ ] Use `secrets.compare_digest` to prevent timing attacks in token comparison
- [ ] Know why rate limiting mitigates brute-force (OWASP A07 mitigation)

### Senior 🔴

- [ ] Explain envelope encryption: why encrypt the data encryption key, not just data
- [ ] Describe Row-Level Security (RLS) in PostgreSQL and a real use case
- [ ] Run `pip-audit` and explain what a CVE entry means
- [ ] Apply STRIDE threat model to the records API
  - [ ] Spoofing, Tampering, Repudiation, Info Disclosure, DoS, Elevation of Privilege
- [ ] Explain supply chain attack and how `gitleaks` + Dependabot mitigate it

### Pre-Interview Refresh ✏️

- [ ] What is IDOR (Insecure Direct Object Reference)? Give an example and the fix
- [ ] Why keep JWT access token TTL to 15 minutes?
- [ ] Authentication vs authorization — what is the difference?
- [ ] How does `secrets.compare_digest` prevent timing attacks?
- [ ] Why is `os.environ["SECRET"]` wrong? What should you use instead?
