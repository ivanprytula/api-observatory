# Local Stack Walkthroughs

These are repeatable learning exercises, not another command catalogue. Start with the smallest
runtime and move to the next level only when you can explain the evidence you observed. The
[setup guide](../04-setup/setup-guide.md) owns prerequisites and configuration; the
[development workflow](dev-workflows.md) owns test selection and day-to-day rules.

Do not paste values from `.env` into terminals, notes, or committed files. Do not run
`just db-reset --confirm DELETE` during these exercises unless the local data is disposable.

## Junior: Core Request and Data Lifecycle

Goal: prove that the smallest local system is running, then follow one write/read path into
PostgreSQL.

Complete the [Canonical Onboarding and Delivery Checklist](onboarding-and-delivery-checklist.md) first. Then trace the core stack:

1. On the core stack, observe the process, dependency, and data boundaries.

   ```bash
   curl --fail http://127.0.0.1:8000/health
   curl --fail http://127.0.0.1:8000/readyz
   docker compose ps
   just db-psql ingestor
   ```

   In `psql`, check `SELECT version_num FROM alembic_version;` and inspect the observation rows
   created by the smoke exercise. Exit with `\q`.

2. Open <http://127.0.0.1:8000/api/docs> and <http://127.0.0.1:8501>. `/health` proves the web
   process is alive; `/readyz` also verifies its required database path. The smoke test is the
   evidence that an observation can be written and read through the running API, so it deliberately
   leaves a small local row behind.

Teach-back: draw `client -> FastAPI ingestor -> PostgreSQL -> API response`, then explain why a
passing `/health` cannot prove the database is usable.

## Middle: Incident, Tenant, and Migration Lifecycle

Goal: trace the current product vertical from a health sample to an incident state transition, then
prove that tenant boundaries and schema evolution are tested.

1. On the core stack, create the disposable demo data only if you want an authenticated dashboard
   walkthrough:

   ```bash
   just db-auto-init
   ```

   Sign in to the dashboard with the documented local demo fixture, then inspect sources and
   incidents. The fixture is local-only; it is not an application credential pattern.

2. Follow the implementation in this order:

   - [`scorecards.py`](../../services/ingestor/api/routes/scorecards.py) accepts a health sample.
   - [`incident_lifecycle.py`](../../services/ingestor/incident_lifecycle.py) applies the incident
     policy.
   - [`incidents.py`](../../services/ingestor/repositories/incidents.py) persists deduplication and
     state transitions.
   - [`routers/incidents.py`](../../services/ingestor/api/routes/incidents.py) scopes list, read,
     acknowledge, and resolve actions to the caller's tenant before the database query.
   - [`bab88abe6c35_enable_dependency_incidents_rls.py`](../../alembic/versions/bab88abe6c35_enable_dependency_incidents_rls.py)
     adds the opt-in PostgreSQL policy as a second boundary.

3. Run the focused proof rather than trusting the dashboard view:

   ```bash
   ALLOW_EXPLAIN_ANALYZE=true uv run pytest \
     services/ingestor/tests/integration/test_incidents_api.py \
     services/ingestor/tests/integration/test_dependency_incidents_rls.py \
     services/ingestor/tests/integration/observations/test_query_analysis.py -q
   uv run alembic current --check-heads
   ```

The API tests prove cross-tenant requests are denied and admins can use their documented scope.
The PostgreSQL test uses a non-superuser role and proves tenant rows, global rows, no active tenant,
and write-policy behavior. RLS remains table-by-table opt-in, not a claim that every tenant-bearing
table is protected. The query-plan test uses 40 matching rows among 1,040 to show the existing
tenant/status index is eligible; it is not a latency SLO.

Teach-back: explain why both API authorization and RLS are useful, why global rows remain visible,
and how `upgrade -> downgrade -> upgrade` lowers migration rollout risk without making rollback
automatic in a deployed environment.

## Senior: Extended Dependencies and Failure Boundaries

Goal: operate the optional dependencies deliberately and explain which component owns each failure
mode without turning the extended stack into the default development path.

1. In `.env`, enable `API_OBS_CACHE_ENABLED=true` and `API_OBS_BROKER_ENABLED=true`, then start and
   verify the extended stack:

   ```bash
   just dev-up-extended
   just dev-wait-ready
   just db-migrate
   just db-inference-migrate
   just dev-inference-ready
   docker compose ps
   ```

   The ingestor remains the system of record owner. Redis supports cache/pub-sub/rate-limit paths;
   Redpanda transports optional events; inference owns its separate pgvector database. None replaces
   PostgreSQL authority for the incident lifecycle.

2. Keep notification delivery precise. Direct delivery is the default. To start the separate broker
   consumer, also set `API_OBS_NOTIFICATIONS_ENABLED=true` and
   `API_OBS_NOTIFICATION_DELIVERY_MODE=broker`, then run:

   ```bash
   docker compose --profile broker up -d notification-consumer
   docker compose ps notification-consumer
   ```

   The worker must persist the inbox and delivery result before committing a Redpanda offset. This
   provides at-least-once behavior; it is not an exactly-once claim. Review
   [`notification_delivery_worker.py`](../../services/ingestor/notification_delivery_worker.py) with
   its unit tests before changing that boundary.

3. Exercise recovery only on a disposable local stack:

   ```bash
   just test-chaos
   ```

   This stops the current PostgreSQL container, requires readiness to fail, restarts it, and waits
   for readiness recovery. It mutates running containers and is intentionally opt-in. Record the
   timing and limits in the [performance and failure worksheet](performance-and-failure-lab.md);
   local recovery is not production-operation evidence.

Teach-back: justify why the core stack stays small, identify the database transaction and broker
offset boundary, and name the measurement that would justify adding replicas, a managed broker, or
another operational layer.

## End Each Exercise Deliberately

Keep useful local data by stopping services with `docker compose stop`. Use the explicit destructive
reset only for disposable demo data. Before a PR, use the proof selection table in
[development workflows](dev-workflows.md#proof-selection) instead of running every optional stack.
