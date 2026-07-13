# Learning Paths

Three tracks covering the full MVP stack (Commits 1-12). Start with architecture orientation:
Architecture Overview for the visual flow diagram and service justifications.

---

## Backend Interview Prep

1. Run the stack: `docker compose up -d && curl http://127.0.0.1:8000/docs`
2. Walk the request flow in [services/ingestor/main.py](../../services/ingestor/main.py) (lifespan, router wiring) and [services/ingestor/routers/](../../services/ingestor/routers/).
3. Review async DB patterns in [services/ingestor/models.py](../../services/ingestor/models.py) and [services/ingestor/repositories/](../../services/ingestor/repositories/).
4. Study JWT auth + RBAC in [services/ingestor/auth.py](../../services/ingestor/auth.py) and [services/ingestor/security/](../../services/ingestor/security/).
5. Trace a LangGraph agent run: [services/ingestor/agent/graph.py](../../services/ingestor/agent/graph.py) → [routers/agent.py](../../services/ingestor/routers/agent.py).

---

## Distributed Systems Track

1. **Event broker**: Redpanda (Kafka-compatible) at `broker:29092`. See `BROKER_URL` in `.env.example`.
   - Why Redpanda vs Kafka? Architecture (ADR 001).
2. **Real-time push**: Cache pub/sub in [services/ingestor/pubsub.py](../../services/ingestor/pubsub.py) → WebSocket fan-out in [routers/ws.py](../../services/ingestor/routers/ws.py).
3. **Background scheduling**: APScheduler in [services/ingestor/jobs.py](../../services/ingestor/jobs.py) and [jobs_registry.py](../../services/ingestor/jobs_registry.py).
4. **Resilience**: circuit breaker in [libs/platform/circuit_breaker.py](../../libs/platform/circuit_breaker.py), rate limiting in [services/ingestor/rate_limiting.py](../../services/ingestor/rate_limiting.py).
5. **Contract drift + scoring**: [routers/contract_drift.py](../../services/ingestor/routers/contract_drift.py) and [routers/scorecards.py](../../services/ingestor/routers/scorecards.py).
6. **LangGraph agent**: StateGraph with 5 nodes, HITL interrupt (Postgres-checkpointed pause/resume, no SSE) in [agent/graph.py](../../services/ingestor/agent/graph.py).

---

## DevOps and Cloud Track

1. Local orchestration: [docker-compose.yml](../../docker-compose.yml) — 7 default services (db, cache, broker, ingestor, inference, inference-db, dashboard); `edge`/monitoring/security-scanning/cloud-deploy services sit behind compose profiles.
2. Image hardening: [Dockerfile](../../Dockerfile) (multi-stage) and [infra/database/Dockerfile](../../infra/database/Dockerfile).
3. Observability: Prometheus metrics in [services/ingestor/metrics.py](../../services/ingestor/metrics.py), OTEL in [main.py lifespan](../../services/ingestor/main.py), `/health` and `/readyz` probes.
4. IaC: Terraform modules in [infra/terraform/](../../infra/terraform/).
5. Deployment walkthrough: Floci AWS Deployment Workflow.
6. Dashboard: `uv run streamlit run services/dashboard/streamlit_app.py` — real-time scorecards, drift events, agent panel.

---

## Agent / LLM Track

1. Start with the ADR: ADR 012 (LangGraph Agent) — dual-model cost design.
2. Trace state transitions in [agent/graph.py](../../services/ingestor/agent/graph.py) (`build_graph()` function).
3. Review each node in [agent/nodes.py](../../services/ingestor/agent/nodes.py): `classify_severity` → `retrieve_similar_incidents` (RAG via the `inference` service) → `draft_analysis` → `human_review` (interrupt) → `notify`.
4. Test interactively with Bruno Desktop: open `bruno/` in Bruno, select `local` env, run the `agent` collection (create source → snapshot → breaking snapshot auto-triggers the agent → get run → resume).
5. See the HITL approval flow via the API directly (no dedicated Streamlit tab exists yet):
   trigger a breaking drift event, `GET /api/v1/agent/runs/{id}` until `status` is
   `awaiting_review`, then `POST /api/v1/agent/runs/{id}/resume` — see the `agent` Bruno
   collection (step 4 above) for the full worked flow.
