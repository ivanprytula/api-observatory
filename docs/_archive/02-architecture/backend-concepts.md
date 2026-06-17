# Backend Concepts & Mental Models

Track: C — Architecture and Platform Strategy


> **Target Audience**: Strong Middle backend engineers. Mental frameworks that unlock system design, performance optimization, and production decision-making.
>
> **How to Use**: Read one section per week. Apply to real code in your project.

---

## Core Mental Framework: The Bottleneck Hierarchy

**Everything** in backend systems eventually hits one of five bottlenecks (in order of prevalence):

```text
1. DATABASE BOTTLENECK    (70% of cases)   → Wrong query, no index, lock contention
2. I/O BOTTLENECK         (15% of cases)   → Network latency, external APIs, disk I/O
3. CPU BOTTLENECK         (10% of cases)   → Compute-bound processing, no parallelism
4. MEMORY BOTTLENECK      (3% of cases)    → Leaks, large objects, inefficient structures
5. NETWORK BOTTLENECK     (2% of cases)    → Bandwidth, serialization, distributed tracing
```

**Decision Rule**: Measure first, diagnose which bottleneck, then solve.

```text
❌ WRONG: "Let me add caching" (assumes I/O bottleneck)
✅ RIGHT: Run query analyzer → See sequential table scan → Add index
❌ WRONG: "Let me optimize CPU" (assumes compute bottleneck)
✅ RIGHT: Profile code → Find 95% time in DB calls → Fix queries
```

---

## PART 1: Database Mastery (70% of Backend Performance)

### 1.1 MVCC (Multi-Version Concurrency Control)

**Mental Model**: Every UPDATE creates a new row version, not in-place modification.

```text
Transaction 1 (writes)
├─ Old row version: "status=pending"
├─ Commits: New row version: "status=approved"
└─ Old version still exists

Transaction 2 (started before Tx1 commits)
├─ Sees old version: "status=pending"
├─ This is correct isolation (no dirty reads)
└─ MVCC allows SELECT to NOT block UPDATE
```

**Real Impact**: Long-running queries can prevent VACUUM cleanup → table bloat → slower queries

```python
# Dangerous: Long transaction prevents cleanup
async with db.begin():
    results = []
    for i in range(1000000):
        # Takes 10 minutes
        row = await db.execute(...)
        results.append(row)
    # Meanwhile, VACUUM can't clean old versions
    # Table grows 10GB while transaction runs
```

**Fix**: Batch and commit frequently

```python
async def process_in_batches():
    for batch in chunks(items, 100):
        async with db.begin():
            # Commit every 100 items
            # VACUUM can clean old versions
            await save_batch(batch)
```

### 1.2 Query Optimization: Diagnosis Framework

**EXPLAIN ANALYZE Decision Tree**:

```text
1. Slow query detected
   └─ Run: EXPLAIN ANALYZE SELECT ...
   └─ Output shows:
      ├─ Sequential Scan or Index Scan?
      ├─ Rows scanned vs returned
      ├─ Plan time vs execution time
      └─ Join order

2. Check: Scan type
   ├─ Sequential Scan on 100M rows?
   │  └─ Check: Are you selecting <5% of rows?
   │  ├─ YES → You need an index
   │  └─ NO → Sequential scan is correct
   │
   ├─ Index Scan exists?
   │  └─ Check: Does index match WHERE clause?
   │  ├─ YES → Index is working, optimize elsewhere
   │  └─ NO → Wrong index, add composite index

3. Check: Filter efficiency
   ├─ Scanning 1M rows, returning 100?
   │  └─ Selectivity = 0.01% (bad)
   │  └─ Fix: Better index or WHERE clause
   │
   └─ Scanning 100 rows, returning 90?
      └─ Selectivity = 90% (good)
      └─ Probably can't optimize further

4. Check: Join order
   ├─ Is DB joining large tables first?
   │  └─ This reduces result set too late
   │  └─ Hint: JOIN smaller table first
   │
   └─ Is DB using right join type?
      └─ Nested loop (slow), Hash join (fast), etc.
```

### 1.3 Isolation Levels (Correctness vs Performance)

| Level                    | Problem               | When                     | Cost      |
| ------------------------ | --------------------- | ------------------------ | --------- |
| READ COMMITTED (default) | Non-repeatable reads  | 99% of cases             | ✅ Lowest |
| REPEATABLE READ          | Phantom reads         | Strong consistency needs | ⚠️ Medium |
| SERIALIZABLE             | None (total ordering) | Financial transactions   | ❌ High   |

**Real Scenario**: Concurrent balance updates (lost update problem)

```python
# WITHOUT locking (bad):
balance = await db.get("SELECT balance FROM accounts WHERE id=?", user_id)
# Thread A: balance=100
# Thread B: balance=100
await db.execute("UPDATE accounts SET balance=?", balance - 50)  # A: 50
await db.execute("UPDATE accounts SET balance=?", balance + 30)  # B: 130
# Result: Thread A's update lost! (should be 80)

# WITH SELECT FOR UPDATE (good):
async with db.begin():
    balance = await db.execute(
        "SELECT balance FROM accounts WHERE id=? FOR UPDATE",
        user_id
    )
    # Row is locked for other transactions
    new_balance = balance - 50
    await db.execute("UPDATE accounts SET balance=?", new_balance)
    # Lock released on commit
```

**Pattern**: Use SELECT FOR UPDATE instead of raising isolation level. More efficient.

---

## PART 2: Async I/O (15% of Backend Performance)

### 2.1 The Event Loop Model

**Mental Model**: One thread, many tasks, pausing & resuming based on I/O readiness.

```text
Event Loop Timeline:
├─ Task A (await db.query)     → Yields, waits for DB
├─ Task B (await api.get)      → Yields, waits for network
├─ Task C (await cache.get)    → Yields, waits for cache
│
├─ Meanwhile: OS handles all three I/O calls in parallel
│
├─ DB responds → Resume Task A (0.1 sec)
├─ Cache responds → Resume Task C (0.05 sec)
├─ API responds → Resume Task B (0.5 sec)
│
└─ Total time: ~0.5 sec (max of three), not 0.65 sec (sum)
```

**The Rule**:

- **I/O-bound** (network, disk, DB)? Use async → 10–100x improvement
- **CPU-bound** (compute, parsing)? Async is useless

```python
# ❌ WRONG: Async doesn't help CPU work
async def sum_million_numbers():
    total = 0
    for i in range(1_000_000):  # Pure compute
        total += i
    return total

# ✅ RIGHT: Async helps I/O work
async def fetch_user_and_posts(user_id):
    user = await db.query(f"SELECT * FROM users WHERE id={user_id}")
    posts = await db.query(f"SELECT * FROM posts WHERE user_id={user_id}")
    return {"user": user, "posts": posts}
    # Both DB calls run in parallel (concurrently)
```

### 2.2 The GIL (Global Interpreter Lock)

**Truth**: Only ONE thread can execute Python bytecode at a time.

```text
Two threads computing (no I/O):
├─ Thread 1: Running bytecode [====]
├─ Thread 2: Waiting (GIL held by Thread 1)
├─ Thread 1: Done, releases GIL [====]
├─ Thread 2: Running bytecode [====]
├─ Thread 1: Waiting
└─ Result: Sequential execution, NO speedup

BUT with async (one thread, many tasks):
├─ Task A: Running until first await [====]
├─ Task B: Running until first await [====]
├─ Task C: Running until first await [====]
└─ Result: Interleaved, 100x+ speedup on I/O
```

**Implication**: Threads for I/O (async is better). Processes for CPU.

---

## PART 3: Data Pipeline Patterns

### 3.1 Idempotency (The Foundation of Reliability)

**Definition**: Processing the same message twice produces same result as once.

```text
❌ NOT idempotent:
def increment_counter(user_id):
    count = db.get(f"SELECT count FROM users WHERE id={user_id}")
    db.execute(f"UPDATE users SET count={count+1} WHERE id={user_id}")
    # If called twice: count becomes +2 (not idempotent)

✅ Idempotent:
def set_counter_to_5(user_id):
    db.execute(f"UPDATE users SET count=5 WHERE id={user_id}")
    # If called twice: count is still 5 (idempotent)

✅ Idempotent with tracking:
def increment_counter(user_id, event_id):
    # Check: Have we processed this event before?
    if db.query("SELECT * FROM processed_events WHERE event_id=?", event_id):
        return  # Already processed, skip

    count = db.get(f"SELECT count FROM users WHERE id={user_id}")
    db.execute(f"UPDATE users SET count={count+1} WHERE id={user_id}")
    db.execute("INSERT INTO processed_events (event_id) VALUES (?)", event_id)
    # Even if called twice, count only increments once
```

**Pattern**: Track processed event IDs → Reprocess safely.

### 3.2 Dead Letter Queue (Resilience)

**Concept**: When processing fails, move message to DLQ for later investigation.

```text
Normal flow:
Event → Process → Success → Delete from queue

Error flow:
Event → Process → ERROR → Move to DLQ

DLQ contains:
{
  "event_id": "abc-123",
  "original_payload": {...},
  "error": "Database connection timeout",
  "retry_count": 3,
  "created_at": "2024-04-22T12:00:00"
}

Operator action:
1. Investigate error
2. Fix underlying issue
3. Move DLQ message back to main queue
4. Retry processing
```

### 3.3 Backpressure (Preventing Queues from Growing)

**Problem**: Producer sends 1000 messages/sec, consumer processes 100/sec

```text
Without backpressure:
├─ Queue grows: 0 → 100 → 200 → 500 → 1000 (unbounded)
├─ Memory exhausted → Application crashes
└─ Data loss

With backpressure:
├─ Producer asks: "Can I send?" → Consumer: "Busy, send later"
├─ Producer backs off (waits 100ms)
├─ Queue stays bounded (only newest messages kept)
└─ Application stays stable
```

**Implementation**:

```python
queue = asyncio.Queue(maxsize=100)  # Bounded queue

async def producer():
    for event in events:
        try:
            queue.put_nowait(event)  # Raise if queue full
        except asyncio.QueueFull:
            logger.warning("Queue full, dropping event")
            # Or wait: await queue.put(event)  # Blocks until space available
```

---

## PART 4: System Design Patterns

### 4.1 Circuit Breaker (Cascading Failure Prevention)

**Problem**: Service A calls Service B. Service B is down. Service A waits for timeout (30 sec) × 1000 requests = 30,000 seconds blocked.

**Solution**: Circuit breaker stops calling B after first few failures.

```text
State machine:

CLOSED (normal)
  ├─ All requests go through
  ├─ Monitor error rate
  └─ If errors > threshold → OPEN

OPEN (failing)
  ├─ Requests immediately fail (don't wait for timeout)
  ├─ Don't call downstream service
  └─ After timeout → HALF_OPEN

HALF_OPEN (testing)
  ├─ Allow one test request
  ├─ If succeeds → CLOSED
  ├─ If fails → OPEN (try again later)
  └─ Prevents thundering herd on recovery
```

### 4.2 Caching Strategy: Cache-Aside vs Write-Through

**Cache-Aside** (most common):

```python
async def get_user(user_id: int):
    # 1. Check cache
    cached = await cache.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)  # Hit

    # 2. Cache miss: fetch from DB
    user = await db.query("SELECT * FROM users WHERE id=?", user_id)

    # 3. Write to cache
    await cache.set(f"user:{user_id}", json.dumps(user), ex=3600)
    return user
```

**Trade-off**: Cache may be stale (OK for most use cases)

**Write-Through**:

```python
async def update_user(user_id: int, data: dict):
    # 1. Update DB
    user = await db.execute("UPDATE users SET ... WHERE id=?", data)

    # 2. Update cache immediately
    await cache.set(f"user:{user_id}", json.dumps(user))
    return user
```

**Trade-off**: Cache always fresh, but more operations (slower writes)

---

## Interview Q&A: Explain These Concepts Aloud

### Q1: "A query is slow. Walk me through how you'd debug it."

**Your Answer** (2 min):

"First, I'd run EXPLAIN ANALYZE to understand the plan. I'm looking for:

1. Is it a sequential scan on a large table?
2. If yes, check if I can add an index matching the WHERE clause
3. If it's an index scan but slow, check the join order
4. Look at the selectivity — am I returning 90% of scanned rows? Bad
5. Monitor actual vs estimated rows — big difference means outdated statistics

Then I'd check if it's a database bottleneck at all. Maybe the slow part is:

- Application-side filtering (stream too much data then filter in Python)
- Serialization (JSON encoding huge result set)
- Network latency (results sent across data center)

I'd profile with Python profiler or database slow-query log to confirm."

### Q2: "When would you use async vs threads vs processes?"

**Your Answer** (2 min):

"Depends on the bottleneck:

**Async**: I/O-bound workload (network calls, database queries, file I/O).

- Single thread, event loop, many concurrent tasks
- Example: Web server handling 1000 concurrent requests
- Can do 1000 I/O operations in parallel efficiently

**Threads**: I/O-bound with legacy synchronous libraries.

- GIL allows only one thread to execute Python bytecode at a time
- But I/O releases the GIL, so other threads can progress
- Example: Multiple database drivers that don't support async
- Risk: Race conditions if not careful with shared state

**Processes**: CPU-bound workload (computation, heavy parsing).

- GIL doesn't apply (separate Python interpreters)
- True parallelism on multi-core
- Example: Heavy ML inference, video encoding
- Cost: High overhead (separate memory, serialization)

In production, I'd use async for I/O, processes for CPU, and avoid threads unless necessary."

### Q3: "Your service is calling an external API that's slow/unreliable. How do you handle it?"

**Your Answer** (3 min):

"I'd implement:

1. **Circuit breaker**: Stop calling API after N failures, wait, retry
2. **Timeout**: Don't wait forever (e.g., 5-second timeout)
3. **Retry with exponential backoff**: Retry 3 times with delays (1s, 2s, 4s)
4. **Cache**: Store responses for 1 hour (or TTL from API)
5. **Fallback**: Return stale data if available, or default
6. **Monitoring**: Alert on failure rate

```python
@circuit_breaker(failure_threshold=5, timeout=60)
@retry(max_attempts=3, backoff=exponential)
async def call_external_api(url):
    try:
        # Check cache first
        cached = await cache.get(url)
        if cached:
            return cached

        # Call API with timeout
        response = await http_client.get(url, timeout=5)

        # Cache for 1 hour
        await cache.set(url, response, ex=3600)
        return response
    except Exception as e:
        logger.error(f"API call failed: {e}")
        raise
```

This way, even if the API goes down, my service degrades gracefully."

---

## PART 5: Data Engineering Patterns (T-Shaped: Solid Data Skills)

### 5.1 Data Quality & Validation Pipeline

**The Reality**: Raw data is broken. Missing fields, wrong types, duplicates. Your job: catch it early.

```text
Raw Data Stream
  ├─ Schema validation (expected fields, types)
  ├─ Business logic validation (age > 0, email has @)
  ├─ Deduplication (same record arrived twice?)
  ├─ Enrichment (add location from IP, etc.)
  └─ → Valid data to warehouse
  └─ → Invalid data to DLQ for manual review
```

Example: CSV upload of customer records

```python
from pydantic import BaseModel, field_validator

class CustomerRecord(BaseModel):
    id: int
    email: str
    age: int
    purchase_date: str

    @field_validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()

    @field_validator('age')
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Age out of range')
        return v

async def import_customers(file: UploadFile):
    valid_count = 0
    invalid_count = 0

    for row in parse_csv(file):
        try:
            record = CustomerRecord(**row)
            await db.execute("INSERT INTO customers VALUES ...", record)
            valid_count += 1
        except ValueError as e:
            # Send invalid record to DLQ
            await dlq.send({
                "original_row": row,
                "error": str(e),
                "created_at": now()
            })
            invalid_count += 1

    logger.info(f"Import complete: {valid_count} valid, {invalid_count} invalid")
```

### 5.2 CQRS (Command-Query Responsibility Segregation)

**The Problem**: Your analytics DB is a copy of the operational DB. Every query scans 100M rows. Slow.

**The Solution**: Separate write path (operational DB) from read path (analytics DB optimized for queries).

```text
Write Path (Operational):
  User clicks → FastAPI endpoint → PostgreSQL (normalized schema)
  └─ Publishes event: "customer_created"

Read Path (Analytics):
  Event → Kafka consumer → Transform → Click-optimized table
  └─ Analytics queries hit this table (NOT operational DB)

Query: "Revenue by country last 30 days"
  ├─ Old: Scan 100M transactions in operational DB → 10 seconds
  └─ New: Query pre-aggregated table in analytics DB → 100ms
```

Implementation Example

```python
# Write path: Operational
@app.post("/orders")
async def create_order(order: OrderRequest, db: AsyncSession):
    db_order = await crud.create_order(db, order)

    # Publish event
    await event_bus.publish("order.created", {
        "order_id": db_order.id,
        "customer_id": db_order.customer_id,
        "amount": db_order.amount,
        "created_at": db_order.created_at,
    })
    return db_order

# Read path: Analytics consumer
async def consume_order_events():
    async for event in kafka_consumer("order.created"):
        # Transform for analytics: aggregate by customer_id, day
        await analytics_db.execute(
            """
            INSERT INTO order_summary (customer_id, date, count, total_amount)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (customer_id, date) DO UPDATE SET
                count = count + 1,
                total_amount = total_amount + ?
            """,
            (event['customer_id'], event['created_at'].date(), 1, event['amount'], event['amount'])
        )

# Analytics query (fast)
@app.get("/analytics/revenue-by-country")
async def revenue_by_country(db: AsyncSession):
    result = await db.execute(
        "SELECT country, SUM(total_amount) FROM order_summary GROUP BY country"
    )
    return result.fetchall()  # Sub-100ms
```

**Trade-off**: Analytics DB is stale (5 min lag). That's acceptable for most dashboards.

---

## PART 6: DevOps & Infrastructure Mental Models (T-Shaped: Solid DevOps Skills)

### 6.1 Multi-Environment Deployment Strategy

**The Pattern**: dev → production. Same code, different configs.

```text
git push main
  ├─ GitHub Actions triggers
  ├─ Test suite runs (pytest)
  ├─ Build Docker image
  ├─ Tag with git commit SHA
  │
  ├─ Deploy to dev (auto)
  │   ├─ Run migration
  │   ├─ Update image in ECS
  │   ├─ Run smoke tests
  │   └─ Wait for health checks
  │
  └─ Deploy to production (manual approval)
      ├─ Run migration
      ├─ Blue-green deployment (50% traffic → new version)
      ├─ Monitor error rate
      ├─ If errors spike → rollback to blue
      └─ Gradually increase traffic to new version (green)
```

**Key Principle**: Immutable infrastructure. Don't SSH into prod and change configs. Deploy new version instead.

### 6.2 Resource Limits & Scaling

**The Reality**: You have limited CPU/memory. Too many requests → everything crashes.

```text
Without limits:
  ├─ 1000 concurrent requests
  ├─ Each uses 100MB memory
  ├─ Total: 100GB memory (server has 4GB)
  ├─ OS kills processes → cascading failures
  └─ "Why did everything crash?"

With limits:
  ├─ Pod requests: 500m CPU, 512Mi memory
  ├─ Pod limits: 1000m CPU, 1Gi memory
  ├─ Kubernetes scheduler: "Can I fit this pod?"
  ├─ If not: wait (don't overcommit)
  ├─ If requests exceed limits: pod gets killed (but others survive)
  └─ Horizontal scaling: "Need more capacity? Add more pods"
```

**Rule of Thumb**:

- **Requests** = what you need (baseline)
- **Limits** = max you'll ever use (safety valve)
- **Ratio**: Limits should be ~2x requests (leave headroom for spikes)

```yaml
# Kubernetes Pod resource definition
apiVersion: v1
kind: Pod
metadata:
  name: api-server
spec:
  containers:
    - name: api
      image: myapp:v1.2.3
      resources:
        requests:
          cpu: 500m         # 0.5 CPU cores guaranteed
          memory: 512Mi     # 512MB guaranteed
        limits:
          cpu: 1000m        # Max 1 CPU core
          memory: 1Gi       # Max 1GB
      livenessProbe:
        httpGet:
          path: /health
          port: 8000
        initialDelaySeconds: 10
        periodSeconds: 30
```

### 6.3 Monitoring & Alerting Strategy

**The Goal**: Detect problems before users notice.

```text
Application Metrics (Prometheus):
  ├─ Request latency (P50, P95, P99)
  ├─ Error rate (errors / total requests)
  ├─ Throughput (requests / sec)
  └─ Business metrics (orders/sec, revenue/hour)

Infrastructure Metrics:
  ├─ CPU usage
  ├─ Memory usage
  ├─ Disk I/O
  ├─ Network bandwidth
  └─ Pod restarts

Alerts (PagerDuty):
  ├─ Error rate > 1% → page on-call
  ├─ P99 latency > 5s → page on-call
  ├─ Pod restarting frequently → page on-call
  ├─ Disk usage > 90% → page on-call
  └─ Database connection pool exhausted → page on-call

Dashboards (Grafana):
  ├─ Real-time service health (green/yellow/red)
  ├─ Historical trends (is performance degrading?)
  ├─ Comparison (dev vs production)
  └─ Business metrics (revenue, signups)
```

**Principle**: Alert on symptoms (error rate), not causes (CPU high). CPU high is a warning, but alert on errors it causes.

### 6.4 Disaster Recovery & Backups

**The Question**: "If the database dies, how fast can you recover?"

**RTO** (Recovery Time Objective) = How long until system is back up?

- Goal: < 1 hour
- Do: Automated failover to read replica

**RPO** (Recovery Point Objective) = How much data can you lose?

- Goal: < 5 minutes
- Do: Continuous backups + WAL archiving

```text
Production Database (Primary)
  ├─ Writes happen here
  ├─ Continuous streaming to:
  │   ├─ Read replica (standby) — switches to primary if main fails
  │   └─ S3 backups (hourly snapshots)
  │
  └─ If database dies:
      ├─ DNS points to read replica (30 sec)
      ├─ Replica becomes new primary
      ├─ Applications reconnect (automatic retry)
      └─ Users notice: ~1 min downtime, no data loss
```

---

## Wrap-Up: T-Shaped Engineer

**You Now Understand**:

- ✅ **Deep (Database, Async, Data Pipelines)**
  - MVCC + query optimization (database bottleneck diagnosis)
  - Async/await + GIL (concurrency model)
  - Idempotency + DLQ + backpressure (reliable data processing)
  - CQRS + analytics (separate read/write paths)

- ✅ **Solid (DevOps, Observability)**
  - Multi-env deployment (dev → prod)
  - Resource limits + scaling (Kubernetes)
  - Monitoring + alerting (detect problems early)
  - Backup + recovery (RTO/RPO)

- ✅ **Breadth (Can Solve Anything)**
  - Recognize bottlenecks
  - Apply appropriate patterns
  - Explain decisions to non-technical stakeholders
  - Mentor junior engineers

This is the **T-shaped backend/data engineer** — deep specialist, broad capability.

---

## Next Steps

- Apply these patterns to your project code
- When you encounter a slow query, use the EXPLAIN ANALYZE tree
- Identify which bottleneck you're actually solving before optimizing
- Review your error handling against the circuit breaker / DLQ patterns
