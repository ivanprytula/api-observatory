# Phase 7 — Security + Infrastructure (Terraform)

**Duration**: 2 weeks
**Goal**: JWT + refresh tokens, secrets rotation, rate limiting, Terraform multi-environment
**Success Metric**: 100% API endpoints authenticated, secrets rotated monthly, zero CVEs in dependencies

---

## Core Learning Objective

Master application security (authentication, authorization, secrets) and infrastructure-as-code (Terraform, multi-env, state management).

---

## Interview Questions

### Core Q: "Design Secure API with JWT + Refresh Token Rotation"

**Expected Answer:**

- Access token (short-lived, 15min): Included in requests via Bearer header
- Refresh token (long-lived, 30d): Stored securely (httpOnly cookie), used to get new access token
- Token rotation: Each refresh invalidates old refresh token, client gets new pair
- Revocation: Refresh token stored in Redis with TTL 30d. Logout removes from Redis.
- Rate limiting: 5 refresh attempts per hour per user (prevent brute force)
- Secrets: JWT signing key rotated quarterly, stored in AWS Secrets Manager

**Talking Points:**

- Stateless access token: Server doesn't need to store (reduces DB queries), validates via signature
- Stateful refresh token: Server stores in Redis (revocation possible), short TTL prevents indefinite access if leaked
- Token binding: Optionally include IP, device fingerprint to prevent token theft
- Cookie vs header: httpOnly cookie safer (XSS not readable), but CORS requires credentials flag

---

### Follow-Up: "Refresh Token Leaked. Attacker Impersonates User. Mitigation?"

**Expected Answer:**

- Immediate: Revoke all tokens for user (clear Redis + issue new key pair)
- Rotation: Invalidate old refresh token on each use (single-use pattern, harder to exploit)
- Monitoring: Alert on suspicious activity (multiple login attempts, unusual IP, etc)
- User notification: Email + SMS notification of token compromise
- Expiration: Tokens already time-limited (15min access, 30d refresh) so window of exposure bounded
- Post-incident: Incident response plan, customer communication, force password reset

**Talking Points:**

- Single-use refresh: Each refresh invalidates previous. If attacker tries old token, server detects (token not in Redis) and alerts.
- Sliding window: Instead of 30d expiry, refresh extends window (e.g., last refresh >7d ago → add 7d). Balances security + UX.

---

### Follow-Up: "Terraform Multi-Environment (Dev, Staging, Prod). State Management?"

**Expected Answer:**

- Workspaces: `terraform workspace select prod` → different tfstate, same code
- State backend: Remote (S3 + DynamoDB state lock) not local (prevent accidental commits)
- Secrets: AWS Secrets Manager (rotatable, audit trail) not env files
- Approval gates: Manual approval in GitHub Actions for prod apply
- State lock: DynamoDB table prevents concurrent applies (corrupted state)
- Drift detection: `terraform plan` in CI to detect manual changes (enforce IaC)

**Talking Points:**

- State lock timeout: If lock stuck (apply crashed), use `terraform force-unlock`
- Workspace naming: `dev`, `staging`, `prod` + region suffix (`dev-eu-central-1`) for multi-region
- Modules: Shared code for networking, RDS, ALB → reused across environments

---

## Real life production example — Production-Ready

### Architecture

```text
User login
  ↓
POST /api/v1/auth/login {username, password}
  ├─► Hash password, compare
  ├─► Token pair: access (JWT), refresh (random string)
  ├─► Store refresh in Redis (key: user_id, value: refresh_token_hash, expiry: 30d)
  ├─► Return: access via body, refresh via httpOnly cookie

User requests /api/v1/records with Bearer {access_token}
  ├─► Middleware validates JWT signature (no DB call)
  ├─► Proceed or 401 Unauthorized

User's access token expires
  ├─► POST /api/v1/auth/refresh with refresh token
  ├─► Check Redis: valid? Matches hash?
  ├─► Regenerate token pair (old refresh invalidated)
  ├─► Return new pair

Logout
  ├─► DELETE /api/v1/auth/logout
  ├─► Remove from Redis (instant revocation)
  ├─► Clear httpOnly cookie
```

### Implementation Checklist

- [ ] **app/auth.py** — JWT + Refresh Logic

  ```python
  from datetime import datetime, timedelta
  from jose import JWTError, jwt
  from passlib.context import CryptContext
  from pydantic import BaseModel

  SECRET_KEY = os.getenv("SECRET_KEY")  # Rotate quarterly
  ALGORITHM = "HS256"
  ACCESS_TOKEN_EXPIRE_MINUTES = 15
  REFRESH_TOKEN_EXPIRE_DAYS = 30

  pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

  def hash_password(password: str) -> str:
      return pwd_context.hash(password)

  def verify_password(plain: str, hashed: str) -> bool:
      return pwd_context.verify(plain, hashed)

  def create_access_token(user_id: int) -> str:
      payload = {
          "sub": str(user_id),
          "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
          "iat": datetime.utcnow(),
      }
      return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

  async def create_refresh_token(user_id: int, redis_client) -> str:
      refresh_token = secrets.token_urlsafe(32)  # Random 32-byte token
      token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

      # Store in Redis (key: user_id, value: token_hash, expiry: 30d)
      await redis_client.setex(
          f"refresh_token:{user_id}",
          30 * 24 * 3600,  # 30 days
          token_hash,
      )

      return refresh_token

  async def validate_refresh_token(user_id: int, token: str, redis_client) -> bool:
      """Check if refresh token valid (exists in Redis)."""
      token_hash = hashlib.sha256(token.encode()).hexdigest()
      stored_hash = await redis_client.get(f"refresh_token:{user_id}")
      return stored_hash == token_hash
  ```

- [ ] **app/routers/auth.py** — Auth Endpoints

  ```python
  from fastapi import APIRouter, HTTPException, status, Response
  from app.schemas import LoginRequest, TokenResponse

  router = APIRouter()

  @router.post("/api/v1/auth/login", response_model=TokenResponse)
  async def login(req: LoginRequest, db: DbDep, redis: RedisDep):
      """Login, return access token + refresh token."""
      user = await crud.get_user_by_username(db, req.username)
      if not user or not verify_password(req.password, user.password_hash):
          raise HTTPException(status_code=401, detail="Invalid credentials")

      access_token = create_access_token(user.id)
      refresh_token = await create_refresh_token(user.id, redis)

      return TokenResponse(
          access_token=access_token,
          refresh_token=refresh_token,  # Will be set in httpOnly cookie by response middleware
          expires_in=15 * 60,  # 15 minutes in seconds
      )

  @router.post("/api/v1/auth/refresh", response_model=TokenResponse)
  async def refresh(req: RefreshRequest, db: DbDep, redis: RedisDep, response: Response):
      """Refresh token pair (invalidates old, returns new)."""
      # Validate old refresh token
      user_id = req.user_id
      valid = await validate_refresh_token(user_id, req.refresh_token, redis)
      if not valid:
          raise HTTPException(status_code=401, detail="Invalid refresh token")

      # Invalidate old token (remove from Redis)
      await redis.delete(f"refresh_token:{user_id}")

      # Generate new pair
      new_access = create_access_token(user_id)
      new_refresh = await create_refresh_token(user_id, redis)

      # Set refresh token as httpOnly cookie
      response.set_cookie(
          key="refresh_token",
          value=new_refresh,
          max_age=30 * 24 * 3600,
          httponly=True,
          secure=True,  # HTTPS only
          samesite="Strict",
      )

      return TokenResponse(
          access_token=new_access,
          refresh_token=new_refresh,
          expires_in=15 * 60,
      )

  @router.post("/api/v1/auth/logout")
  async def logout(user: CurrentUserDep, redis: RedisDep, response: Response):
      """Logout (revoke refresh token)."""
      await redis.delete(f"refresh_token:{user.id}")
      response.delete_cookie("refresh_token")
      return {"message": "Logged out"}
  ```

- [ ] **Middleware: Parse JWT**

  ```python
  from fastapi import Depends, HTTPException, status
  from jose import JWTError, jwt

  async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
      """Extract user from JWT access token."""
      try:
          payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
          user_id = int(payload.get("sub"))
      except JWTError:
          raise HTTPException(status_code=401, detail="Invalid token")

      return User(id=user_id)

  # Use in routes
  @router.get("/api/v1/records")
  async def list_records(user: CurrentUserDep, db: DbDep):
      """Only authenticated users can list."""
      return await crud.get_records_for_user(db, user.id)
  ```

- [ ] **Rate Limiting (Refresh Endpoint)**

  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address

  limiter = Limiter(key_func=get_remote_address)

  @router.post("/api/v1/auth/refresh")
  @limiter.limit("5/hour")  # Max 5 refreshes per hour per IP
  async def refresh(req: RefreshRequest, ...):
      # Refresh logic
      pass
  ```

- [ ] **Secrets Management (AWS Secrets Manager)**

  ```python
  import boto3

  def get_secret(secret_name: str) -> dict:
      """Fetch secret from AWS Secrets Manager."""
      client = boto3.client('secretsmanager')
      response = client.get_secret_value(SecretId=secret_name)
      return json.loads(response['SecretString'])

  # In config
  SECRET_KEY = get_secret('data-pipeline/jwt-key')['key']
  OPENAI_API_KEY = get_secret('data-pipeline/openai-key')['key']
  ```

- [ ] **Terraform: Multi-Environment**

  ```hcl
  # main.tf
  terraform {
    backend "s3" {
      bucket         = "data-pipeline-tfstate"
      key            = "terraform.tfstate"
      region         = "eu-central-1"
      dynamodb_table = "terraform-lock"
      encrypt        = true
    }
  }

  provider "aws" {
    region = var.region
  }

  # modules/networking/vpc.tf
  resource "aws_vpc" "main" {
    cidr_block = var.vpc_cidr
    tags = {
      Environment = var.environment
      Name        = "${var.environment}-vpc"
    }
  }

  # modules/rds/main.tf
  resource "aws_db_instance" "postgres" {
    allocated_storage    = var.db_storage
    engine               = "postgres"
    engine_version       = "17"
    instance_class       = var.db_instance_class
    username             = "postgres"
    password             = random_password.db_password.result
    multi_az             = var.multi_az
    skip_final_snapshot  = var.environment == "dev"

    tags = {
      Environment = var.environment
    }
  }

  # terraform.tfvars (per environment)
  # dev.tfvars
  environment = "dev"
  db_instance_class = "db.t3.micro"
  multi_az = false

  # prod.tfvars
  environment = "prod"
  db_instance_class = "db.t3.large"
  multi_az = true
  ```

- [ ] **.github/workflows/terraform.yml** — Plan + Apply

  ```yaml
  name: Terraform

  on:
    push:
      branches: [main]
      paths: [terraform/**, .github/workflows/terraform.yml]

  jobs:
    plan:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: hashicorp/setup-terraform@v2
        - run: terraform plan -var-file=prod.tfvars -out=tfplan
        - uses: actions/upload-artifact@v3
          with:
            name: tfplan
            path: tfplan

    apply:
      runs-on: ubuntu-latest
      needs: plan
      if: github.ref == 'refs/heads/main'
      environment: production  # Manual approval required
      steps:
        - uses: actions/download-artifact@v3
          with:
            name: tfplan
        - uses: hashicorp/setup-terraform@v2
        - run: terraform apply tfplan
  ```

---

## Weekly Checklist

### Week 1: JWT + Refresh Tokens

- [ ] User schema: hash password (bcrypt), store securely
- [ ] Login endpoint: return access + refresh tokens
- [ ] Refresh endpoint: validate, invalidate old, return new pair
- [ ] Logout endpoint: revoke refresh token (Redis delete)
- [ ] JWT middleware: parse, validate, attach user to request
- [ ] Rate limiting: 5 refreshes/hour per user
- [ ] Interview Q: "Design secure JWT + refresh?" → Answer drafted
- [ ] Commits: 6–8 (auth endpoints, middleware, rate limiting, tests)

### Week 2: Secrets + Terraform

- [ ] AWS Secrets Manager: store JWT key, OpenAI key
- [ ] Secret rotation: quarterly for JWT key (updates app config)
- [ ] Dependency audit: `pip-audit` to scan for CVEs
- [ ] Terraform modules: VPC, RDS, ECS/Fargate, ALB
- [ ] Multi-environment: dev, staging, prod with separate vars
- [ ] State backend: S3 + DynamoDB lock for safe concurrent applies
- [ ] GitHub Actions: Terraform plan on PR, apply on main (with approval)
- [ ] Interview Q: "Token leaked. Recovery?" → Full answer
- [ ] Commits: 5–7 (terraform setup, secrets rotation, CI/CD for infra)
- [ ] Portfolio item + LinkedIn post

---

## Success Metrics

| Metric                      | Target                    | How to Measure                                                  |
| --------------------------- | ------------------------- | --------------------------------------------------------------- |
| API endpoints authenticated | 100%                      | Public endpoints only: /health, /docs. Others all gated.        |
| Token expiry                | 15min access, 30d refresh | JWT decode + check exp claim. Refresh tokens in Redis with TTL. |
| Refresh rate limit          | 5/hour                    | Test: 6 refreshes in 1 min → 6th returns 429                    |
| CVE vulnerabilities         | 0                         | `pip-audit` output → should be clean                            |
| Secrets in repo             | 0                         | `grep -r "sk_\|AKIA" .` → should find nothing                   |
| Terraform state locked      | Always                    | DynamoDB table shows lock on apply, auto-released on completion |
| Deployment approval         | Manual on prod            | GitHub environment approval required for prod apply             |
| Commit count                | 11–15                     | 1 per auth feature / terraform module                           |

---

## Gotchas + Fixes

### Gotcha 1: "Refresh Token Doesn't Persist in Redis After Deploy"

**Symptom**: Logout works locally, but production refresh fails (token disappeared).
**Cause**: Redis instance not persistent (in-memory only), or connection string wrong.
**Fix**: Use Redis with `appendonly yes` (persistence), or switch to managed service (AWS ElastiCache, Azure Cache).

### Gotcha 2: "Terraform State Locked, Can't Apply"

**Symptom**: `terraform apply` hangs or fails with "state locked".
**Cause**: Previous apply crashed or hung, lock not released.
**Fix**: `terraform force-unlock <LOCK_ID>` (find ID in DynamoDB), then retry.

### Gotcha 3: "JWT Key Rotation Breaks Existing Tokens"

**Symptom**: After key rotation, all users logged out (tokens invalid).
**Cause**: Old tokens signed with old key, new key doesn't validate.
**Fix**: Use key versioning (`kid` in JWT header), keep old key in secrets for grace period (7 days), then deprecate.

### Gotcha 4: "Refresh Token HttpOnly Cookie Not Sent"

**Symptom**: Client receives refresh token in response body but not in session.
**Cause**: Cookie not set (HTTPS required, or domain mismatch).
**Fix**: Ensure `secure=True` (HTTPS), `samesite="Strict"`, and client uses `credentials: 'include'` in fetch.

---

## Cleanup (End of Phase 7)

```bash
# Terraform cleanup (if destroying environment)
terraform destroy -var-file=prod.tfvars -auto-approve

# CVE scan final
pip-audit

# Secret rotation reminder
# Schedule: TBD (usually quarterly)
```

---

## Metrics to Monitor Ongoing

- Failed login attempts: Alert if > 10 per minute per user (brute force attempt)
- Refresh token usage: Alert if spike (potential token compromise)
- Terraform drift: Run `terraform plan` daily, alert if changes detected (manual infra changes)
- CVE vulnerabilities: Alert if any found (run `pip-audit` weekly)

---

## Next Phase (Optional)

**Phase 8: Observability at Scale**
OTEL tracing, Grafana dashboards, log aggregation, SLO/SLI metrics. Not included in core 7-phase plan but valuable for production.

**Completion**: Phase 7 marks end of core 8-phase Data Zoo Platform. Subsequent iterations focus on scale, observability, and advanced patterns.

---

Project Completion Checklist

- [ ] 7 phases complete, each with working real life production example
- [ ] 100+ commits across all phases (8–15 per phase)
- [ ] 8 LinkedIn posts (1 per phase), archived
- [ ] 8 portfolio items (1 per phase), with GitHub links
- [ ] 100% test coverage
- [ ] Zero CVEs in dependencies
- [ ] Production-ready infrastructure (Terraform multi-env, state locked)
- [ ] Interview prep: All core Q + follow-ups articulated (mid-level → senior)
- [ ] CV narrative: "Backend engineer shipping multi-service data platforms. Specialized in: event streaming, async Python, embeddings, database optimization, infrastructure automation."

---

END OF DATA ZOO PLATFORM — 8-PHASE LEARNING PATH
