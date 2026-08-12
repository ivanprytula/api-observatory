# ADR 014: Separation of Management (Portal) and Operations (Dashboard)

Track: C — Architecture and Platform Strategy

## Status

Accepted (May 2026)

## Context

As the `api-observatory` project matured into Phase 5+, it required both a way to manage administrative metadata (DataSources, IngestionConfigs) and a way to monitor real-time operational metrics. Initially, a single "Dashboard" was considered, but the requirements for these two domains began to diverge:

1. **Management (Control Plane):** Requires complex relationships, relational integrity, form-heavy administrative interfaces, and long-term state management.
2. **Operations (Observability Plane):** Requires real-time updates, low-latency metric streams, high-concurrency read-only views, and quick operational "firefighting" tools.

## Decision

We decided to split these responsibilities into two separate services with distinct technical stacks optimized for their specific planes:

### 1. The Django Portal (Management/Control Plane)

* **Technonogy:** Django 6.x (Async support), DRF, PostgreSQL, psycopg3 (Connection Pooling).
* **Responsibility:** "Source of Truth" for system configuration. Handlers CRUD for `DataSource` and `IngestionConfig`.
* **Key Pattern:** Async-first Django using native `aget`, `acreate`, and `asave` methods to ensure non-blocking I/O even when handling administrative tasks.

### 2. The FastAPI Dashboard (Operations/Observability Plane)

* **Technology:** FastAPI, Jinja2, HTMX, Server-Sent Events (SSE).
* **Responsibility:** "Glass Surface" for the running system. Proxies metrics from Prometheus and active task states from the Ingestor.
* **Key Pattern:** SSE for live ingestion rates and status updates, HTMX for lightweight interactivity without the overhead of a full SPA.

## Rationale

* **Domain Isolation:** Administrative logic (Portal) is decoupled from operational monitoring (Dashboard). A failure in the metrics stack doesn't prevent an engineer from updating a DataSource configuration.
* **Stack Optimization:** Django's robust Admin and ORM are ideal for managing configuration metadata. FastAPI's high performance and native SSE support are ideal for the high-frequency operational updates required by the Dashboard.
* **Evolutionary Path:** This split mirrors production-scale "Control Plane / Data Plane" architectures used in cloud-native environments.

## Consequences

* **Integration:** The services must cross-link to each other (e.g., Dashboard links to Portal Edit pages).
* **Deployment:** Two services instead of one, requiring coordinated `docker-compose` profiles.
* **Consistency:** Metadata changes in the Portal must be reflected in the Dashboard's view of the world (usually via shared Database or API lookup).
