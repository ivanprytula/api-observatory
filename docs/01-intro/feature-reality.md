# Feature Reality Map

Maps every major feature to its evidence status, runnable path, and test
coverage. Use this to answer "what did you build?" without listing
technologies.

---

| Feature | Status | Default run path | Test coverage |
| --- | --- | --- | --- |
| Observation CRUD | **Core** | `just dev-up` → `POST /api/v1/observations` | Integration + unit |
| Source registry + health probing | **Core** | APScheduler starts on app launch | Integration + unit |
| Scorecards + availability | **Core** | Scheduled job, no extra infra | Integration |
| Dependency incidents | **Core** | Auto-created on threshold breach | Integration |
| Tenant RLS | **Core** | `RLS_ENABLED=true` (opt-in) | Integration (cross-tenant leak tests) |
| Auth (JWT + roles) | **Core** | `just generate-secrets` then start | Unit + integration |
| Redis pub/sub (WebSocket) | **Core** | `just dev-up-cache` | Integration |
| Notifications (direct) | **Core** | Inline HTTP dispatch, fail-open | Unit |
| Contract drift detection | **Core** | Scheduled snapshot job | Integration |
| LangGraph incident agent | **Lab** | `ANTHROPIC_ENABLED=true` + API key | Unit + evals |
| Kafka broker / outbox | **Lab** | `just dev-up-broker` + `--profile broker` | Integration (isolated) |
| Inference service (embeddings) | **Lab** | `just dev-up-inference` | Unit + integration |
| Vector search | **Lab** | Requires inference service | Unit |
| Background worker pool | **Lab** | `BACKGROUND_WORKERS_ENABLED=true` | Unit |
| Gateway / load balancer | **Lab** | `labs/gateway_load_balancing/` | Manual |
| Partitioning / sharding | **Deferred** | `labs/partitioning_sharding/` | None (trigger: measured single-node limit) |
| mTLS between services | **Deferred** | Planned, not implemented | None |
| AWS deployment | **Decision** | Gated behind repo variables; infra in sibling repo | CI pipeline only |
| Streamlit dashboard | **Core** | Part of `just dev-up` default stack | Manual |

---

## Primary vs. Secondary Paths

### Event delivery

- **Primary**: Synchronous PostgreSQL write. This is the only path that runs
  with `just dev-up`. It is authoritative, transactional, and observable.
- **Secondary**: Redis pub/sub for real-time WebSocket fan-out. Optional,
  fail-open, requires `just dev-up-cache`.
- **Tertiary**: Kafka for async notification dispatch. Feature-gated behind
  `BROKER_ENABLED=true` and `notification_delivery_mode=broker`. The
  `notification-consumer` container is a separate process and is **not** part
  of `just dev-up`.

### Scheduling

- APScheduler runs in-process. It is the only scheduler and owns all probe,
  snapshot, retention, and scorecard jobs.
- Single-replica only. Running 2 ingestor replicas causes duplicate outbound
  API calls. The roadmap explicitly defers multi-replica extraction.

### Inference

- The inference service is a separately deployed FastAPI app with its own
  database, migrations, and Dockerfile.
- It is **not** included in `just dev-up`. Use `just dev-up-inference` or
  `just dev-up-extended`.
- The ingestor calls it over HTTP for embeddings. If the service is down,
  vector-search endpoints return 503 but core CRUD is unaffected.

---

## Configuration Hygiene

Removed dead configuration in this cleanup:

- `broker_strangler_adapter_enabled` — declared but never read; `events.py`
  has one publish path.
