# Learning Paths

Three tracks covering the full MVP stack (Commits 1-12). Start with architecture orientation:
[docs/04-architecture-overview.md](04-architecture-overview.md) for the visual flow diagram and service justifications.

---

## Backend Interview Prep

1. Run the stack: `docker compose up -d && curl http://localhost:8000/docs`
2. Walk the request flow in [services/ingestor/main.py](../services/ingestor/main.py) (lifespan, router wiring) and [services/ingestor/routers/](../services/ingestor/routers/).
3. Review async DB patterns in [services/ingestor/models.py](../services/ingestor/models.py) and [services/ingestor/repositories/](../services/ingestor/repositories/).
4. Study JWT auth + RBAC in [services/ingestor/auth.py](../services/ingestor/auth.py) and [services/ingestor/security/](../services/ingestor/security/).
5. Trace a LangGraph agent run: [services/ingestor/agent/graph.py](../services/ingestor/agent/graph.py) → [routers/agent.py](../services/ingestor/routers/agent.py).
6. Explain trade-offs from [docs/tech-map.md](tech-map.md) — interview-ready topic map.

---

## Distributed Systems Track

1. **Event broker**: Redpanda (Kafka-compatible) at `broker:29092`. See `BROKER_URL` in `.env.example`.
   - Why Redpanda vs Kafka? [docs/design/architecture.md](design/architecture.md) (ADR 001).
2. **Real-time push**: Cache pub/sub in [services/ingestor/pubsub.py](../services/ingestor/pubsub.py) → WebSocket fan-out in [routers/ws.py](../services/ingestor/routers/ws.py).
3. **Background scheduling**: APScheduler in [services/ingestor/jobs.py](../services/ingestor/jobs.py) and [jobs_registry.py](../services/ingestor/jobs_registry.py).
4. **Resilience**: circuit breaker in [libs/platform/circuit_breaker.py](../libs/platform/circuit_breaker.py), rate limiting in [services/ingestor/rate_limiting.py](../services/ingestor/rate_limiting.py).
5. **Contract drift + scoring**: [routers/contract_drift.py](../services/ingestor/routers/contract_drift.py) and [routers/scorecards.py](../services/ingestor/routers/scorecards.py).
6. **LangGraph agent**: StateGraph with 5 nodes, HITL interrupt, SSE streaming in [agent/graph.py](../services/ingestor/agent/graph.py).

---

## DevOps and Cloud Track

1. Local orchestration: [docker-compose.yml](../docker-compose.yml) — 4 services (db, cache, broker, ingestor).
2. Image hardening: [Dockerfile](../Dockerfile) (multi-stage) and [infra/database/Dockerfile](../infra/database/Dockerfile).
3. Observability: Prometheus metrics in [services/ingestor/metrics.py](../services/ingestor/metrics.py), OTEL in [main.py lifespan](../services/ingestor/main.py), `/health` and `/readyz` probes.
4. IaC: Terraform modules in [infra/terraform/](../infra/terraform/).
5. Deployment walkthrough: [docs/floci-aws-deployment-workflow.md](floci-aws-deployment-workflow.md).
6. Dashboard: `uv run streamlit run services/dashboard/streamlit_app.py` — real-time scorecards, drift events, agent panel.

---

## Agent / LLM Track

1. Start with the ADR: [docs/adr/012-langgraph-agent.md](adr/012-langgraph-agent.md) — dual-model cost design.
2. Trace state transitions in [agent/graph.py](../services/ingestor/agent/graph.py) (`build_graph()` function).
3. Review each node in [agent/nodes.py](../services/ingestor/agent/nodes.py): RAG fetch → classify → deep analyze → publish.
4. Test interactively with Bruno: `cd bruno && bru run agent --env local`.
5. See HITL approval flow in Streamlit: launch app → Agent Enrichment → HITL Review tab.
