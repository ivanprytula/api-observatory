# Testing System Context

Decomposed reference for a new session. Focus: how tests are selected, what runtime
context each lane/profile requires, and where the wiring lives.

## 1. Taxonomy

### Lanes (just/testing.just → scripts/test/run-lane.sh)
| Lane | Just recipe | Runner | Runtime needs |
|------|-------------|--------|---------------|
| unit | `test-unit` | `run-lane.sh unit` | None (uv extras only) |
| integration | `test-integration` | `run-lane.sh integration` | Docker (testcontainers) |
| e2e | `test-e2e` | `run-lane.sh e2e` | Docker when fixtures need PG |
| live | `test-live-external` | `run-lane.sh live` | Public network only |
| smoke | `test-smoke` | `scripts/smoke-test.sh` | Running local stack |
| smoke-auth | `test-smoke-auth` | `scripts/smoke-test.sh` | Running local stack + JWT |
| api | `test-api` | `bru run` | Running local stack |

### Profiles (just/testing.just → scripts/test/run-profile.sh)
| Profile | Just recipe | Runner | Env flags set |
|---------|-------------|--------|---------------|
| core | `test-core` | `run-profile.sh core` | All optional caps OFF |
| rls | `test-capability-rls` | `run-profile.sh rls` | `RLS_ENABLED=true` |
| broker | `test-capability-broker` | `run-profile.sh broker` | `BROKER_ENABLED=true`, `NOTIFICATIONS_ENABLED=true`, `NOTIFICATION_DELIVERY_MODE=broker` |
| ai | `test-capability-ai` | `run-profile.sh ai` | `ANTHROPIC_ENABLED=false` |
| full-optional | `test-full-optional` | `run-full-optional.sh` | `RLS_ENABLED=true`, `BROKER_ENABLED=true`, `NOTIFICATIONS_ENABLED=true`, `NOTIFICATION_DELIVERY_MODE=broker`, `ANTHROPIC_ENABLED=false` |

## 2. Pytest Markers (pyproject.toml)
```
unit, integration, core, capability_rls, capability_broker, capability_ai,
full_optional, demo, contract, e2e, chaos, browser, live, mongo, ws_lab
```

Default `addopts` in pyproject.toml:
```
--cov=services/ingestor --cov-report=term-missing --cov-report=html -q -m 'not e2e and not demo'
```

## 3. System-Context Env Flags
These toggle capability slices in the ingestor and tests:

| Flag | Default | Meaning |
|------|---------|---------|
| `CACHE_ENABLED` | `false` | Redis cache |
| `BROKER_ENABLED` | `false` | Redpanda/Kafka broker |
| `NOTIFICATIONS_ENABLED` | `false` | Notification subsystem |
| `NOTIFICATION_DELIVERY_MODE` | `direct` | `direct` or `broker` |
| `RLS_ENABLED` | `false` | PostgreSQL row-level security |
| `OPENAI_ENABLED` | `false` | OpenAI LLM provider |
| `ANTHROPIC_ENABLED` | `false` | Anthropic LLM provider |
| `OTEL_ENABLED` | `false` | OpenTelemetry tracing |
| `BACKGROUND_WORKERS_ENABLED` | `false` | Background job workers |
| `RETENTION_ENABLED` | `false` | Data retention policies |
| `AUTH_DEMO_ROUTES_ENABLED` | `false` | Demo auth routes |

## 4. Docker Compose Topology
File: `docker-compose.yml`

Always-on:
- `ingestor-db` (PostgreSQL, port 5432)
- `ingestor` (FastAPI, port 8000, depends on ingestor-db)
- `dashboard` (Streamlit, port 8501, depends on ingestor)

Optional profiles:
| Profile | Services |
|---------|----------|
| `cache` | `cache` (Redis, port 6379) |
| `broker` | `broker` (Redpanda, ports 9092/8082), `notification-consumer` |
| `inference` | `inference-db` (PostgreSQL, port 5433), `inference` (port 8001) |
| `monitoring` | `prometheus`, `grafana`, `loki`, `promtail`, `tempo`, `alertmanager`, `mailpit` |
| `ingress` | `edge` (nginx, ports 80/443) |
| `security` | `trivy`, `checkov`, `gitleaks`, `hadolint` |
| `aws` | `floci-aws` (LocalStack, port 4566) |
| `test-harness` | `test-harness` (defined in `docker-compose.test.yml`) |

Network: single `api-obs` bridge.

## 5. CI Matrix (.github/workflows/ci.yml)
| Job | Trigger | Services | Env |
|-----|---------|----------|-----|
| `unit` | Always when app/delivery changes | None | `DATABASE_URL_TEST=sqlite+aiosqlite:///:memory:` |
| `integration` | After unit+code-quality | postgres:pgvector | All caps OFF except DATABASE_URL_TEST=postgres |
| `capability` (matrix) | After unit+code-quality | postgres:pgvector | Matrix-driven caps |
| `image-smoke` | After integration | None | Builds images, health-checks |
| `dashboard-tests` | After code-quality | None | Runs `services/dashboard/tests` |

Capability matrix:
| Profile | Marker | RLS | Broker | Notifications | Anthropic |
|---------|--------|-----|--------|---------------|-----------|
| rls | `capability_rls` | true | false | false | false |
| broker | `capability_broker` | false | true | true | false |
| ai | `capability_ai` | false | false | false | false |
| full-optional | `full_optional` | true | true | true | true |

## 6. Key Entrypoints
- `Justfile` — core recipes (doctor, dev-up, db-migrate, etc.)
- `just/testing.just` — all test recipes
- `scripts/test/run-lane.sh` — unit/integration/e2e/live dispatch
- `scripts/test/run-profile.sh` — core/rls/broker/ai dispatch
- `scripts/test/run-full-optional.sh` — composed RLS+broker+AI harness
- `conftest.py` — root pytest ignores (deferred post-MVP slices)
- `pyproject.toml` — pytest markers, coverage, ruff, ty config

## 7. Deferred / Post-MVP (conftest.py collect_ignore_glob)
- `services/ingestor/tests/integration/scrapers/test_*.py`
- `tests/e2e/scrapers/test_*.py`
- `services/ingestor/tests/unit/storage/test_mongo_operations.py`
- `services/ingestor/tests/integration/observations/test_materialized_views_and_partitioning.py`
- `services/ingestor/tests/integration/observations/test_cte_window_functions.py`
- `services/ingestor/tests/integration/test_background_processing_api.py`
- `services/ingestor/tests/integration/test_pubsub.py`
- `tests/integration/schema/test_schema_integrity.py`
