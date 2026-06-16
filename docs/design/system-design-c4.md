# System Design C4

Track: C - Architecture and Platform Strategy

This document complements the flow-oriented architecture guide in [docs/04-architecture-overview.md](../04-architecture-overview.md) with a C4 viewpoint:

- Level 1: system context
- Level 2: containers
- Level 3: components inside the ingestor service

## Scope

Current focus is the MVP runtime centered on the ingestor service and its core data and messaging dependencies.
Future services are shown as planned extensions, not active dependencies.

## Level 1: Context

```mermaid
flowchart LR
    User["API Consumer\n(Bruno, curl, Streamlit)"]
    Team["Developer / Operator"]

    subgraph Platform["Data Pipeline Platform"]
      Ingestor["Ingestor API\nFastAPI service"]
    end

    ExtAPI["External HTTP APIs\nsource providers"]
    OpenAI["OpenAI API\nagent enrichment"]
    AWS["AWS runtime\n(ECS, RDS, ElastiCache)"]

    User -->|REST, WebSocket| Ingestor
    Team -->|deploy, observe, maintain| Ingestor
    Ingestor -->|probe and ingest| ExtAPI
    Ingestor -->|LLM calls| OpenAI
    Team -->|deploy target| AWS
```

## Level 2: Containers

```mermaid
flowchart TB
    Client["Client\nHTTP + WS"]
    Streamlit["Streamlit dashboard\nlocal UI"]

    subgraph App["Application Boundary"]
      Ingestor["Ingestor\nFastAPI + APScheduler"]
    end

    Postgres[("PostgreSQL\nsource profiles, observations, drift, scorecards")]
    Cache[("Cache\ncache, sessions, pub/sub, rate-limit state")]
    Redpanda[("Redpanda\nKafka-compatible event bus")]
    Trivy["Trivy scans\nsecurity checks"]

    Client --> Ingestor
    Streamlit --> Ingestor
    Ingestor --> Postgres
    Ingestor --> Cache
    Ingestor --> Redpanda
    Trivy -. image scan .-> Ingestor

    Inference["Inference service\nplanned"]
    Dashboard["Dashboard service\nplanned"]
    Analytics["Analytics service\nplanned"]
    Webhook["Webhook service\nplanned"]
    Timeseries["Timeseries service\nplanned"]
    Search["Search service\nplanned"]

    Inference -. future .-> Ingestor
    Dashboard -. future .-> Ingestor
    Analytics -. future .-> Ingestor
    Webhook -. future .-> Ingestor
    Timeseries -. future .-> Ingestor
    Search -. future .-> Ingestor
```

## Level 3: Components (Ingestor)

```mermaid
flowchart TB
    Router["API routers\nservices/ingestor/routers/"]
    Security["Security and auth\nservices/ingestor/security/\nauth.py"]
    Jobs["Schedulers and jobs\nservices/ingestor/jobs.py\njobs_registry.py"]
    Repos["Repositories\nservices/ingestor/repositories/"]
    Obs["Observability\nmetrics + tracing + logging"]
    Agent["Agent workflow\nservices/ingestor/agent/"]

    Router --> Security
    Router --> Repos
    Router --> Agent
    Jobs --> Repos
    Jobs --> Security
    Security --> Repos

    Repos --> DB[("PostgreSQL")]
    Router --> Cache[("Cache cache/pubsub")]
    Jobs --> Bus[("Redpanda topics")]
    Router --> Obs
    Jobs --> Obs
    Security --> Obs
```

## Design Notes

- The architecture document in [docs/04-architecture-overview.md](../04-architecture-overview.md) remains the request-flow deep dive.
- This C4 document is the structural map for onboarding, planning, and cross-team communication.
- Future services are intentionally shown as planned edges to keep MVP boundaries explicit.

## Related Documents

- [docs/04-architecture-overview.md](../04-architecture-overview.md)
- [docs/monorepo-structure.md](../monorepo-structure.md)
- [docs/observability.md](../observability.md)
