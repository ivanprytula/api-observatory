# Common Gotchas & Pitfalls

Track: B — Engineering Execution


Learn from mistakes without making them yourself.

---

## Python & Async

### [gotcha] Forgetting `await` on Coroutines

```python
# ❌ Creates coroutine, never runs it, gets garbage collected
result = my_async_function()

# ✅ Actually runs
result = await my_async_function()

# ✅ Fire and forget (if you don't care about result)
asyncio.create_task(my_async_function())
```

**How to spot**: Warnings about coroutine "was never awaited"

---

### [gotcha] Blocking Sync Code in Async Context

```python
async def my_route():
    time.sleep(1)  # ❌ BLOCKS entire event loop
    return {"status": "ok"}

# Fix:
async def my_route():
    await asyncio.sleep(1)  # ✅ Yields control
    return {"status": "ok"}
```

**How to spot**: Route takes forever even though it's marked async

---

### [gotcha] Connection Pool Exhaustion

```python
# Pool size = 10, but you create 11 concurrent tasks
for i in range(11):
    asyncio.create_task(fetch_from_db(db, i))

# Result: "too many connections" error

# Fix: Use Semaphore
semaphore = asyncio.Semaphore(10)
async def bounded_fetch(i):
    async with semaphore:
        return await fetch_from_db(db, i)

for i in range(11):
    asyncio.create_task(bounded_fetch(i))
```

**How to spot**: Error "too many connections" or "pool exhausted"

---

## Database

### [gotcha] N+1 Queries

```python
# ❌ 1 + N queries (slow)
users = await db.scalars(select(User))
for user in users:
    profile = await db.scalar(select(Profile).where(...))

# ✅ Single JOIN (fast)
stmt = select(User).options(selectinload(User.profile))
users = await db.scalars(stmt)

# Spot it: Enable DB_ECHO=True, count queries in logs
```

---

### [gotcha] Table Bloat from Long-Running Transactions

```sql
-- User starts long query at 10:00
SELECT COUNT(*) FROM huge_table;

-- Other users UPDATE at 10:05, 10:10, 10:15
-- PostgreSQL piles up old versions (can't delete until first query finishes)
-- At 10:30, first query finishes, but table is now "bloated" with dead rows

-- Solution: Kill long queries
SELECT pg_terminate_backend(pid) WHERE query LIKE 'SELECT COUNT%';

-- Or configure autovacuum to be aggressive
```

**How to spot**: Queries getting slower, `pg_stat_user_tables.dead_n_tup_ratio` high

---

### [gotcha] MVCC-Related Serialization Anomalies

```python
# Two transactions see different versions of same row
# Tx1: balance = 100
# Tx2: balance = 100
# Tx1: balance -= 50 (commits)
# Tx2: balance += 20 (commits, sees old version)
# Final: balance = 120 (but should be 70!)

# Fix: SELECT FOR UPDATE
stmt = select(Account).where(...).with_for_update()
account = await db.scalar(stmt)
```

---

### [gotcha] Missing Indexes on Where Clauses

```sql
-- Slow query: full table scan
EXPLAIN ANALYZE
SELECT * FROM observations WHERE source = 'api.example.com';
-- Seq Scan on observations (cost=0.00..5000.00 rows=10000)

-- Add index
CREATE INDEX idx_observations_source ON observations(source);

-- Now fast
-- Index Scan using idx_observations_source (cost=0.01..10.00 rows=10)
```

---

### [gotcha] Alembic Migrations on Python 3.14 + SQLAlchemy Async

**Problem**: `alembic upgrade head` hangs or fails with `psycopg.OperationalError: server closed the connection unexpectedly` on Python 3.14 + sqlalchemy 2.0 + asyncpg.

**Root cause**: SQLAlchemy's sync `engine_from_config()` uses greenlet spawning internally. Python 3.14's event loop changes (asyncio rewrite in CPython) broke greenlet interop in certain contexts. Even raw `psycopg.connect()` fails because the underlying psycopg SCRAM-SHA-256 auth handshake involves thread/greenlet transitions that Python 3.14 rejects.

**Solution**: Use `async_engine_from_config()` + `run_sync()` wrapper + `asyncio.run()` at top-level:

```python
# alembic/env.py
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config

async def run_migrations_async():
    """Async engine avoids sync greenlet issues."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=None,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    """Call async via asyncio.run() at top-level.

    Top-level asyncio.run() avoids greenlet spawning issues from inside
    existing event loops (which happen if Alembic is called from within app).
    """
    asyncio.run(run_migrations_async())
```

**Why this works**:

- `async_engine_from_config()` creates an async engine (no greenlets)
- `asyncio.run()` at top-level creates fresh event loop (no existing loop conflicts)
- `run_sync()` wraps sync DDL execution, but from a "clean" async context

**Caveats**:

- `alembic upgrade head` and `alembic revision` work fine
- Do NOT call Alembic from within FastAPI's running event loop (e.g., startup hook) — Python 3.14 will refuse to spawn the new event loop
- If you must auto-create schema on app startup, use `Base.metadata.create_all()` via `run_sync()` instead (that's safe because it's inside existing async app context)

**Testing** (migrations don't run):

- Tests use in-memory SQLite (`aiosqlite`), not PostgreSQL
- So test suite passes even if Alembic would fail
- To test Alembic on Python 3.14, run manually: `uv run alembic upgrade head`

**Expected in Python 3.14.1+**: This is likely fixed in later Python 3.14 releases or upstream in asyncpg/psycopg3.

---

### [gotcha] PostgreSQL Authentication: Dev vs Prod (Localhost vs Network)

**Problem**: Want fast, password-free connections for localhost dev/migrations but secure password auth for remote connections (DBeaver, pgAdmin, prod servers).

**Solution**: Use `pg_hba.conf` with role-based auth rules:

```ini
# pg_hba.conf
# IPv4 local connections : trust (no password)
host    all             all             127.0.0.1/32            trust
# IPv4 remote connections: password required
host    all             all             0.0.0.0/0               scram-sha-256
# Unix socket (local psql, Alembic): trust
local   all             all                                     trust
```

**Result**:

- `psql -h localhost -U postgres` (dev/Alembic) → no password prompt
- `psql -h remote-host -U postgres` (DBeaver, pgAdmin, prod) → password required
- `docker compose exec db psql -U postgres` (socket) → no password

**Docker setup**:

```yaml
# docker-compose.yml
services:
  db:
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - ./infra/database/pg_hba.conf:/etc/postgresql/pg_hba.conf:ro
    command:
      - postgres
      - -c
      - hba_file=/etc/postgresql/pg_hba.conf
```

**Caveats**:

- `trust` auth only secure for localhost (can't reach from outside)
- Production: use VPC/network security, SSL certs, strong passwords
- Alembic URL in alembic.ini can be bare (no password) → works with `trust` auth

---

## FastAPI & APIs

### [gotcha] Query Params Without Defaults Are Optional

```python
# ❌ This doesn't work as expected
@app.get("/observations/{id}")
async def get_observation(id: int, limit: int):  # <-- limit is optional!
    pass

# Call: /observations/123 (no limit param)
# FastAPI returns 422 because limit is missing

# Fix: Add default
@app.get("/observations/{id}")
async def get_observation(id: int, limit: int = 10):
    pass
```

---

### [gotcha] Form Data vs Body

```python
# These are different!

# ❌ Expects form data (application/x-www-form-urlencoded)
@app.post("/login")
async def login(username: str, password: str):
    pass

# ✅ Expects JSON body
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login")
async def login(request: LoginRequest):
    pass
```

---

### [gotcha] HTTPException Status Code Defaults to 500

```python
# ❌ Returns 500 (server error)
raise HTTPException(detail="User not found")

# ✅ Returns 404 (client error)
raise HTTPException(status_code=404, detail="User not found")
```

---

## Docker & Deployment

### [gotcha] Layers Built But Not cached

```dockerfile
# ❌ Rebuilds deps every time code changes
FROM python:3.14-slim
COPY . /app          # <-- changes often
RUN pip install -r requirements.txt

# ✅ Layers cached properly
FROM python:3.14-slim
COPY requirements.txt .
RUN pip install -r requirements.txt  # Cached unless requirements.txt changes
COPY . /app          # Changes often, but deps already cached
```

---

### [gotcha] Running as Root in Container

```dockerfile
# ❌ Runs as root (security risk)
FROM python:3.14-slim
CMD ["python", "app.py"]

# ✅ Runs as non-root
FROM python:3.14-slim
RUN useradd -m appuser
USER appuser
CMD ["python", "app.py"]
```

---

## Testing

### [gotcha] Test DB Not Isolated Between Tests

```python
# ❌ Tests interfere with each other
@pytest.fixture
def db():
    engine = create_async_engine("sqlite:///:memory:")
    yield engine  # Shared across tests!

# ✅ Fresh DB per test
@pytest.fixture
async def db():
    engine = create_async_engine("sqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()  # Clean up
```

---

## Security

### [gotcha] Storing Secrets in Environment Variables

```python
# ❌ Secrets in code or .env checked into git
DATABASE_URL = "postgresql://user:password@host/db"  # Exposed!

# ✅ Load from environment
import os
DATABASE_URL = os.environ["DATABASE_URL"]

# Or better: use Secrets Manager (AWS, GCP, HashiCorp Vault)
```

---

### [gotcha] Hardcoding API Keys

```python
# ❌ Key exposed in source code
response = openai.ChatCompletion.create(
    api_key="sk-abc123xyz",  # LEAKED!
    ...
)

# ✅ Use environment variable
openai.api_key = os.environ["OPENAI_API_KEY"]
```

---

### [gotcha] Trusting User Input

```python
# ❌ Direct concatenation (SQL injection)
query = f"SELECT * FROM users WHERE id = {user_input}"

# ✅ Parameterized query (ORM)
stmt = select(User).where(User.id == user_input)
```

---

## Observability

### [gotcha] Logging Sensitive Data

```python
# ❌ Logs contain PII
logger.info(f"User login: {username}, email: {email}, password: {password}")

# ✅ Log only IDs
logger.info("user_login", extra={"user_id": user.id, "email_hash": hash(email)})
```

---

### [gotcha] No Request ID in Logs

```python
# ❌ Can't correlate request lifecycle
logger.info("Starting request")
logger.info("Querying DB")
logger.info("Returning response")

# ✅ Inject correlation ID
logger.info("Starting request", extra={"cid": request_id})
logger.info("Querying DB", extra={"cid": request_id})
logger.info("Returning response", extra={"cid": request_id})
```

---

## How to Avoid Gotchas

1. **Enable linting**: `ruff check` catches many issues
2. **Write tests**: Gotchas appear as test failures
3. **Use `DB_ECHO=True` in dev**: Spot N+1 queries
4. **Profile in production**: Use `prometheus-fastapi-instrumentator` to find slow endpoints
5. **Read error messages carefully**: They usually tell you exactly what's wrong
6. **Ask LLM to explain errors**: "Why am I getting 'too many connections'?"
