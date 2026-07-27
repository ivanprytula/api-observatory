# Interview Prep: Strong Middle Backend Engineer

Track: D — Business and Interview Narrative

> Practical Q&A for middle/middle+ backend roles. Answer these aloud before interviews to internalize.
>
> **Structure**: Real questions from production interviews + your proven experience + Data Zoo examples

---

## Quick Prep: 5 Most Common Questions

### Q1: "Describe a production issue you diagnosed and fixed."

**Your Story** (2 min, practice aloud):

"At LumenGlobal, we had 5–7 service restarts per week, each lasting 10–15 minutes. It seemed random. I checked logs and saw 'connection pool exhausted' errors.

The problem: SQLAlchemy connection pool was too small for peak load. Connections weren't being closed properly. Over time, all connections were held by requests, new requests couldn't get one, and the service crashed.

I diagnosed it with:

1. Checking pool configuration (size was 20, should be 50+ for concurrent requests)
2. Adding health checks to detect stale connections
3. Implementing connection timeouts
4. Adding Prometheus metrics to track pool usage

Result: Zero restarts after fix. The team learned the connection pooling pattern."

**Why It Works**:

- ✅ Concrete problem (not vague)
- ✅ Systematic diagnosis (didn't guess)
- ✅ Measurable outcome (5+ → 0 restarts)
- ✅ Learning shared (team got knowledge)

---

### Q2: "Walk me through your approach to optimizing a slow API endpoint."

**Your Answer** (3 min):

"First, I'd measure. Get the actual response time distribution (P50, P95, P99), not just average. Is it consistent or spiky?

Then I'd diagnose:

1. Run EXPLAIN ANALYZE on the main query
2. Check: sequential scan or index scan?
3. If sequential scan on large table and <5% of rows returned, I need an index
4. If index exists but slow, check the join order — is it scanning large table first?
5. Check row selectivity — if I'm returning 90% of scanned rows, there's no good index

From there:

- Missing index? Add it matching the WHERE clause
- Index exists? Maybe the WHERE clause can be tightened
- Maybe it's not the query — network latency, serialization, connection wait time?

I'd also check if caching helps. If same query runs 100 times/sec, cache the result for 1 hour.

Real example at BIT Studios: Customer report endpoint was 8 seconds. EXPLAIN ANALYZE showed sequential scan of 2M records. Added index on (customer_id, created_at). Response time dropped to 200ms."

Why It Works:

- ✅ Systematic approach (diagnose before fixing)
- ✅ Shows you use tools (EXPLAIN ANALYZE, metrics)
- ✅ Mentions caching as a pattern (senior thinking)
- ✅ Concrete example with metrics

---

### Q3: "Tell me about a time you worked with a team on a complex feature. What was your role?"

**Your Story** (2.5 min):

"At LumenGlobal, we redesigned the trade force-exit workflow. The problem: when a trader force-exits a position, sometimes the UI and database got out of sync. Orders would show as 'executing' in the UI but already executed in the backend, or vice versa.

My role: Backend architect for the state machine.

I designed:

1. Clear state transitions: pending → executing → completed/failed (no shortcuts)
2. Idempotent message processing: even if a request arrived twice, the second would be no-op
3. Atomic database transaction: state update and order update happen together, or not at all

Then I worked with QA to verify edge cases — what if network breaks mid-request? What if two exit requests arrive at the same time?

Result: QA could confidently test complex scenarios. Zero state-sync issues in production."

Why It Works:

- ✅ Shows architectural thinking (state machines, idempotency)
- ✅ Cross-team collaboration (QA, trading team)
- ✅ Measurable outcome (zero issues)
- ✅ Deep understanding of the problem

---

### Q4: "How do you ensure reliability when your service depends on an external API?"

**Your Answer** (2 min):

"I'd implement layered defense:

1. **Circuit breaker**: If the external API fails 5 times in a row, stop calling it for 60 seconds. Then retry one test request. If it works, close the circuit. If not, wait another 60 seconds.

2. **Timeout**: Don't wait forever. Set a 5-second timeout per request.

3. **Retry with backoff**: Try 3 times with delays (1 sec, 2 sec, 4 sec). Exponential backoff prevents thundering herd.

4. **Cache**: If I've called the API, store the response for 1 hour. Next requests get cached result (stale but available).

5. **Fallback**: If all else fails, return stale data or a default.

Example at BIT Studios: Integrated Microsoft Graph API for org data. If Microsoft went down, we'd serve cached org data for up to 1 hour. Most users got data anyway. After 1 hour, we'd show a 'data may be stale' banner.

The key: Graceful degradation. Service degrades, not fails."

Why It Works:

- ✅ Comprehensive approach (multiple layers)
- ✅ Specific patterns (circuit breaker, backoff)
- ✅ Acknowledges trade-offs (stale data vs down)
- ✅ Production mindset

---

### Q5: "What's your approach to testing? How do you decide what to test?"

**Your Answer** (2.5 min):

"Testing pyramid: 70% unit tests, 20% integration tests, 10% e2e tests. That means fast feedback in CI.

**Unit tests**: Pure functions, no I/O. One function, one test.

- Example: parse_csv_line() function. Test valid input, missing fields, malformed data.
- Fast: 100 tests in <1 second
- Deterministic: Run 100 times, same result

**Integration tests**: Database + application logic together.

- Example: Create user → verify it's in DB → update user → verify update
- Slower: Use real PostgreSQL
- Catch bugs unit tests miss (ORM mistakes, transaction issues)

**E2E tests**: Full API request → database → response

- Example: POST /users with valid data → verify 201 response + DB record created
- Slowest: Real databases, async context
- Only critical paths (sign up, payment, etc.)

At LumenGlobal, I'd test:

- Normal path (happy case)
- Error cases (invalid input, API failure)
- Edge cases (concurrent requests, state transitions)
- Never test library code (trust pytest, SQLAlchemy, etc.)

The rule: Test behavior, not implementation. If I refactor code but behavior stays the same, tests should still pass."

Why It Works:

- ✅ Clear testing strategy (pyramid)
- ✅ Understands trade-offs (speed vs coverage)
- ✅ Knows what to test (behavior, not implementation)
- ✅ Production mindset (edge cases, concurrency)

---

## Deep Dive Questions (Senior/Architect Level)

### Q: "Describe a system you designed. What trade-offs did you make?"

**Your Answer** (4 min):

"At BIT Studios, we redesigned the role-based access control system for multi-tenant SaaS.

**Problem**: 100+ business accounts, each with own teams and permissions. Admin dashboard needed different permissions from customer portal.

**Original approach**: Stored permissions in a single users table. Complex logic scattered across views.

**My redesign**: Permission hierarchy

```text
Organization
  └─ Team
      └─ Role (Admin, Viewer, Editor)
          └─ Permissions (read_users, edit_users, etc.)
```

Trade-offs I considered:

1. **Granularity vs Complexity**
   - More granular = more powerful (customer can set fine-grained permissions)
   - More complex = harder to maintain
   - Decision: Stopped at team+role level. Didn't add resource-level permissions (could add later if needed)

2. **Database normalization vs Query speed**
   - Normalized: Separate tables (roles, permissions, role_permissions) = cleaner, slower joins
   - Denormalized: Flatten permissions into user record = faster queries, stale data
   - Decision: Normalized + caching. Cache permission check for 5 minutes. Cache hit rate 95%+

3. **Centralized permission check vs Distributed**
   - Centralized: Single permission service, other services call it
   - Distributed: Each service knows how to check permissions
   - Decision: Middleware checks on every request. One place to reason about security

Result

- Enabled new product lines (admin dashboard, customer portal, API clients)
- Zero security incidents related to permissions
- Performance: Permission check <5ms due to caching

**What I'd do differently**: Should have set up feature flags for gradual rollout. We did big-bang migration which caused integration issues."

Why It Works

- ✅ Clear problem statement
- ✅ Multiple alternatives considered
- ✅ Rationale for each decision
- ✅ Honest about what could be better
- ✅ Measurable outcomes

---

### Q: "You're proposing to move from Django to FastAPI. Make the case."

**Your Answer** (3 min):

"**Context**: Legacy Django monolith, API responses slow during peak traffic.

**Problem we're solving**: Traffic increased 10x, response times degraded. Some endpoints take 5+ seconds.

**Why FastAPI**:

1. **Async-first**: FastAPI is built for async. Django's async support is bolted-on. With FastAPI, I can handle 1000 concurrent requests on one server. Django would need 10 servers.

2. **Performance**: Uvicorn (FastAPI server) faster than gunicorn (Django). ~2–3x faster for I/O-bound workloads.

3. **Validation**: Pydantic auto-validates requests. Django REST Framework requires more boilerplate.

**Trade-offs**:

- **Smaller ecosystem**: Django has more packages. FastAPI growing fast but newer.
- **Learning curve**: Team knows Django. FastAPI different mental model.
- **Maturity**: Django battle-tested for 15+ years. FastAPI ~5 years.

**Mitigation**:

- Start with one new service in FastAPI (not rewrite monolith)
- Keep Django for existing endpoints
- Gradually migrate high-traffic endpoints
- Team training: 2-week FastAPI workshop

**Measure success**:

- Response time P95 <500ms (vs 5s today)
- Server count 10 → 3
- Developer productivity (fewer bugs, faster feature delivery)

**If we're wrong**:

- FastAPI ecosystem matures fast. If not, rewrite is painful but possible
- Django monolith still works, just slower"

**Why It Works**:

- ✅ Clear problem (not technology for technology's sake)
- ✅ Concrete metrics for success
- ✅ Acknowledges trade-offs
- ✅ Risk mitigation (gradual migration)
- ✅ Decision reversible if wrong

---

### Q: "Design a real-time notification system that handles 100K+ users. Walk through your approach."

**Your Answer** (4 min):

"**Requirements**:

- 100K+ concurrent users
- Notifications should arrive within 1 second
- 99.9% reliability (2–3 notifications can be lost, not service down)
- Scalable to 1M+ users

**Architecture**:

```text
Event Source (order placed, user mentioned, etc.)
    ↓ (Publish to Kafka)
Event Stream (Kafka topic)
    ↓ (Consume)
Notification Service (FastAPI + async workers)
    ├─ Check user preferences (cached)
    ├─ Render notification (template)
    ├─ Send via WebSocket OR push notification
    └─ Log to notification_history table

User receives notification <1s
```

**Key decisions**:

1. **Kafka vs direct API call**
   - Kafka: Decouples producer (order service) from consumer (notification service)
   - If notification service goes down, events queue up, no data loss
   - If I called API directly, order service would wait → cascading failures

2. **WebSocket for real-time**
   - Server pushes notification to user (not user polling)
   - Sub-100ms latency
   - Requires connection management (users disconnect, reconnect)

3. **Idempotency**
   - If notification service crashes after sending but before marking as sent, don't send twice
   - Use idempotency key: event_id + user_id
   - Check: "Did I already send this?" before sending

4. **Scaling**
   - Kafka handles 1M+ events/sec (partition by user_id)
   - Multiple notification workers (horizontal scale)
   - Each worker gets subset of partitions
   - PostgreSQL log grows unbounded → archive old notifications to S3

**Metrics to monitor**:

- Event lag (how far behind are we processing?)
- Notification latency (P50, P95, P99)
- Error rate (failed sends)
- WebSocket connection count

**If this becomes bottleneck**:

- Cache user preferences (5-min TTL)
- Batch sends (send 100 at a time instead of 1)
- Use CDN for push notifications (Firebase Cloud Messaging, Apple Push)"

Why It Works

- ✅ Scalable architecture (Kafka, horizontal workers)
- ✅ Reliability (idempotency, DLQ)
- ✅ Specific technology choices with rationale
- ✅ Monitoring strategy
- ✅ Degradation plan if bottleneck appears

---

## Behavioral Questions

### Q: "Tell me about a time you made a mistake. How did you handle it?"

**Story** (2 min):

"Early in my career at [company], I deleted a production database backup thinking it was a test environment. Very scary moment.

How I handled it:

1. Immediately told my manager (transparency)
2. We restored from another backup (fortunately existed)
3. I set up monitoring to prevent it again
4. Documented the incident and lessons learned

What I learned:

- Labels matter. Always explicit about prod vs test
- Automate what can go wrong
- Incident response is not blaming, it's fixing + learning

Now I double-check environment before any destructive operations. And I advocate for infrastructure that prevents accidental deletes (immutable backups, multi-region copies)."

**Why It Works**:

- ✅ Honest about mistake
- ✅ Shows ownership (didn't blame others)
- ✅ Took action to prevent recurrence
- ✅ Learned something

---

### Q: "Describe a time you had to communicate something complex to a non-technical person."

**Story** (2 min):

"At LumenGlobal, trading bot performance was degrading. The CEO wanted to know: Is it a problem? When will it be fixed?

Technical reality: Database connection pool exhaustion causing cascading timeouts. Needed 2–3 days to diagnose and fix.

How I explained it to CEO:

- Analogy: 'Think of connections as checkout lanes at a grocery store. We had 20 lanes, but during busy hours, 100 customers need checkout. They back up, frustrate customers, sometimes they leave.'
- Impact: '5–7 service restarts per week means 15 min downtime. For automated traders, that's missed opportunities.'
- Solution: 'We'll add more lanes and a system to detect when we're overwhelmed.'
- Timeline: '2–3 days to diagnose and implement. Then zero restarts.'

CEO understood, approved the work, managed expectations.

Result: We fixed it, zero restarts after. CEO was happy we communicated clearly."

**Why It Works**:

- ✅ Used analogy (CEO understood)
- ✅ Focused on business impact (revenue, not technology)
- ✅ Clear timeline
- ✅ Result-oriented

---

## Wrap-Up: Before Every Interview

**Do this the night before**:

1. ✅ Write down 3–5 stories from your experience
   - 1 production issue you diagnosed
   - 1 complex feature you designed
   - 1 time you learned from mistake
   - 1 time you helped someone else

2. ✅ Practice answering aloud (2–3 min each)

3. ✅ Prepare questions for interviewer:
   - "What does success look like in this role?"
   - "What's the biggest technical challenge your team is facing?"
   - "How do you measure engineer impact here?"

4. ✅ Have Data Zoo project ready to reference
    - "I built a project demonstrating these patterns..."
    - Link to GitHub: [api-observatory](https://github.com/ivanprytula/api-observatory) (formerly data-pipeline-async)

---

## Talking Points by Interview Round

### Phone Screening (30 min)

- **Goal**: Quick check if you're real / experienced
- **Your stories**: Production issue diagnosis + one achievement
- **Time**: 10 min = story, 10 min = technical questions, 10 min = logistics

### Technical Round (90 min)

- **Goal**: Can you solve real problems?
- **Prepare**: Your 3 biggest stories in detail, system design question
- **Code**: May be minimal (architect role) or detailed (if pure backend)

### System Design Round (90 min)

- **Goal**: Can you think at scale?
- **Prepare**: "Design notification system for 100K users" — answer above
- **Framework**: Problem → Solution → Trade-offs → Scaling

### Final Round (Manager/Director)

- **Goal**: Culture fit, growth mindset
- **Your story**: "Why I built Data Zoo" = continuous learning, teaching others
- **Questions**: "What does success look like?" "How do you grow engineers?"
