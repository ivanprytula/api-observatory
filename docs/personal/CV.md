# Backend Engineer — Strong Middle / Middle+

Track: D — Business and Interview Narrative

> **5 years commercial experience** building production backend systems at scale.
> **T-shaped specialist**: Deep in async systems, databases, data pipelines; working familiarity with CI/CD, deployment workflows, and observability.
> Now building **Data Zoo** — a reference implementation of production backend patterns.

---

## Professional Summary

Backend engineer with deep technical expertise across async systems, databases, and data pipelines. Proven ability to diagnose and solve production problems, design reliable systems, and communicate complex technical concepts.

**Core Strength**: Turn vague problems ("system is slow") into measurable solutions (query optimization, connection pooling, caching strategies). Comfortable working across multiple repositories, services, and infrastructure layers. Learn quickly and independently.

**What I Deliver**:

- ✅ Security-in-mind, from code to production: secrets scanning (Gitleaks), IaC scanning (Checkov), dependency auditing (pip-audit), container scanning (Trivy), SAST (Bandit), and runtime hardening (no-new-privileges, read-only rootfs, seccomp) — applied at every stage
- ✅ 5+ years of real production experience across multiple domains (SaaS, data systems, trading platforms)
- ✅ Concrete technical results: eliminated weekly service restarts, debugged concurrent system failures, optimized data pipelines for 1000+ events/sec
- ✅ Proactive problem-solving: diagnosed issues BEFORE they became incidents; prevented cascading failures
- ✅ T-shaped skills: deep in backend/data/databases; practical familiarity with CI/CD, Kubernetes workflows, and observability tooling
- ✅ Full-stack accountability: code → testing → deployment → production monitoring
- ✅ Collaborative and adaptable: work best with clear requirements but experienced with vague ones — skilled at DoD refinement, managing out-of-scope, and constructively pushing back to keep delivery focused

**Where I'm Headed**: Middle → Middle+ roles where I can own technical decisions on complex systems, contribute to architecture alongside senior engineers, and grow leadership skills through real projects and mentoring relationships.

---

## Technical Expertise (Ranked by Depth)

### Mastered (5+ years, production-grade)

| Area                                | Depth        | Proof                                                                           |
| ----------------------------------- | ------------ | ------------------------------------------------------------------------------- |
| **Python Backend (Django/FastAPI)** | Expert       | 5+ years: Django → FastAPI migration                                            |
| **PostgreSQL + Optimization**       | Expert       | Resolved connection pool exhaustion (5+ weekly incidents)                       |
| **REST API Design**                 | Strong       | 10+ production APIs, OAuth2 integrations, webhook handlers                      |
| **Async Task Processing**           | Strong       | Celery expertise, async/await patterns, backpressure handling                   |
| **Production Troubleshooting**      | Strong       | Root cause analysis, logging/metrics interpretation                             |
| **Docker + Kubernetes**             | Intermediate | Containerized deployments, YAML configuration, day-to-day operational workflows |

### Advanced (3+ years, architecture-level decisions)

| Area                            | Depth    | Proof                                                            |
| ------------------------------- | -------- | ---------------------------------------------------------------- |
| **Database Query Optimization** | Advanced | EXPLAIN ANALYZE diagnosis, index design, query refactoring       |
| **CI/CD Pipelines**             | Advanced | GitLab CI, GitHub Actions, multi-environment deployments         |
| **Monitoring & Observability**  | Advanced | Sentry, VictoriaLogs, OpenSearch, Grafana dashboards             |
| **System Design**               | Advanced | Multi-service architecture, event streaming, resilience patterns |

### Working Familiarity (Delivery Support Level)

| Area                  | Level     | Scope                                                                                             |
| --------------------- | --------- | ------------------------------------------------------------------------------------------------- |
| **DevOps / Platform** | Practical | CI/CD configs, Docker/K8s manifests, service-level deployment/debug workflows                     |
| **Infra Networking**  | Limited   | Not claiming deep expertise in bare-metal provisioning, advanced network design, or CIDR planning |

### Data Zoo — Coverage by Phase

| Area                       | Focus                              | Status              |
| -------------------------- | ---------------------------------- | ------------------- |
| **Event Streaming**        | Kafka/Redpanda, async consumers    | ✅ Phase 1 complete |
| **Vector Search**          | AI/embeddings, semantic indexing   | ✅ Phase 3 complete |
| **Resilience Patterns**    | Circuit breaker, DLQ, backpressure | ✅ Phase 4 complete |
| **Infrastructure-as-Code** | Terraform AWS EC2 MVP configuration | Decision; no live deployment claimed |
| **Observability Stack**    | Prometheus, Grafana, OTel, tracing | Local/configuration evidence |
| **Chaos / Load Testing**   | Bounded k6 and database recovery exercises | Local lab evidence |
| **Ansible Automation**     | Common, Docker, and AWS MVP host bootstrap | Statically validated |

---

## Key Achievements (Impact-Focused)

### Critical Problem Diagnosis → Prevention

**Trading Bot Failure Prevention** (LumenGlobal)

- **Situation**: Binance API changes could break trading bot order execution without warning
- **Action**: Established API changelog monitoring system, analyzed impact on codebase
- **Impact**: Identified and communicated breaking changes to product team BEFORE going to production
- **Outcome**: Proactive code adjustments prevented potential order execution failures; zero production bot failures
- **Technical Depth**: Analyzed 15+ bot repositories, coordinated cross-team rollout, implemented monitoring alerts

**System Reliability Recovery** (LumenGlobal)

- **Situation**: 5–7 service restarts per week due to database connection pool exhaustion
- **Root Cause**: SQLAlchemy pool configuration too small; health checks not detecting stale connections
- **Solution**: Tuned pool size, implemented connection health checks, added monitoring alerts
- **Metrics**:
  - Before: 5+ weekly restarts, 10–15 min downtime per incident
  - After: Zero restarts in 8+ weeks, system stable across QA/prod
- **Learning**: Documented connection pooling patterns for team reference

### Complex Feature Delivery (Architecture + Implementation)

**Trade Force-Exit Workflow Redesign** (LumenGlobal)

- **Problem**: Inconsistent state during force-exit, leading to UI sync failures and trading confusion
- **Redesign**:
  - Atomic database transactions for state transitions
  - Idempotent message processing (prevent double-processing)
  - Clear state machine (pending → executing → completed/failed)
- **Result**: Eliminated edge cases, improved test coverage, enabled QA to verify complex scenarios
- **Technical Pattern**: Applied idempotency and state machine patterns (now documented in Data Zoo)

**REST API for Multi-Tenant Access Control** (BIT Studios)

- **Scope**: Role-based APIs serving 100+ business accounts
- **Complexity**: Admin dashboard + customer-facing API with different permission models
- **Solution**: Designed permission hierarchy (global → org → team → resource), implemented via middleware
- **Result**: Enabled new product lines (admin, customer portals, API clients)
- **Integration**: Connected external services (Zoom, Microsoft Graph) via OAuth2 flows

### Production Reliability Improvements

**Database Query Optimization** (BIT Studios + ELEKS)

- **Problem**: API endpoints returning in 5–10 seconds due to inefficient ORM queries
- **Diagnosis**: Used Django Debug Toolbar, SQL profiling to identify N+1 queries and missing indexes
- **Solutions Implemented**:
  - Converted ORM queries to raw SQL where needed
  - Added composite indexes on frequently-joined columns
  - Implemented query result caching (1-hour TTL)
- **Metrics**: Average response time 5s → 200ms (25x improvement)
- **Learned**: Documented optimization workflow (now teaching in Data Zoo Phase 5)

**Async Task Processing System** (BIT Studios + ELEKS)

- **Scope**: Extended Celery for email notifications, scheduled reports, PDF generation
- **Challenges**: Ensuring reliable execution, handling retries, monitoring failures
- **Solution**:
  - Implemented exponential backoff retry logic
  - Set up task result caching (Celery result backend)
  - Created monitoring dashboard (failed tasks, queue depth)
- **Result**: 99.5%+ successful task execution; emails reliably delivered

### Cross-Team Enablement (Mentoring + Documentation)

**QA Team Infrastructure Training** (LumenGlobal)

- **Situation**: QA team struggled to debug complex trading scenarios, felt "blocked" by infrastructure
- **Action**:
  - Conducted training on Kubernetes logging, port-forwarding, log aggregation
  - Created runbooks for common debugging tasks (find specific trade, inspect state transitions)
  - Provided off-hours support for edge-case testing
- **Result**: QA became self-sufficient, could verify complex scenarios independently
- **Impact**: Reduced developer interruptions; improved feature quality

**Technical Documentation** (ELEKS + LumenGlobal)

- Created comprehensive guides for backtesting calculations (referenced by new devs and BA team)
- Documented API response formats and error codes (reduced support questions)
- Built internal dashboards for production monitoring (accessible to non-engineers)

---

## Professional Experience

### Python Developer — LumenGlobal (Jan 2025 – Mar 2026, 14 months)

**High-Throughput Event Processing System** | Real-time order processing, 15+ concurrent services | FastAPI/PostgreSQL/Kubernetes

**Key Responsibilities**:

- Core backend engineer for event-driven microservices platform (multi-service, multi-repository)
- Designed and maintained async data pipelines handling 1000+ events/sec
- Deployed features via GitLab CI/CD to QA and production Kubernetes clusters
- Ownership of system reliability and incident response

**Technical Accomplishments**:

- **Event Processing at Scale**: Built async consumer pipeline processing 1000+ events/sec with idempotent message handling and dead letter queue for failed events
- **System Stability**: Resolved critical connection pool exhaustion (5+ weekly restarts) through SQLAlchemy tuning, connection health checks, and Prometheus monitoring
- **Data Consistency**: Redesigned state machine workflow, eliminating race conditions and ensuring atomic state transitions across distributed services
- **Observability**: Implemented distributed tracing (VictoriaLogs, OpenSearch, Sentry), enabling rapid incident diagnosis and root cause analysis
- **Cross-Team Support**: Mentored QA team on Kubernetes debugging, log aggregation, and infrastructure navigation
- **Infrastructure Automation**: Automated internal workflows and monitoring via GitLab CI and JIRA APIs

**Tech**: FastAPI, PostgreSQL (async), SQLAlchemy 2.0, Celery (async tasks), Docker, Kubernetes, AWS (EC2/S3), GitLab CI, Prometheus, VictoriaLogs, OpenSearch, distributed tracing

---

### Middle Backend Engineer — BIT Studios (Dec 2023 – Sep 2024, 9 months)

**SaaS Admin Dashboard & Customer Portals** | 100+ business accounts | Django/Celery/PostgreSQL

**Key Responsibilities**:

- Designed and implemented role-based REST APIs for multi-tenant access control
- Extended Celery background task system for reliability and scalability
- Collaborated with frontend on API contracts and error handling

**Technical Accomplishments**:

- **API Design**: Built permission hierarchy (global → org → team → resource) supporting admin and customer portals
- **External Integrations**: Implemented OAuth2 flows for Zoom, Microsoft Graph with webhook event handling and error recovery
- **Query Optimization**: Analyzed slow endpoints via Django Debug Toolbar; refactored ORM queries, added indexes (5s → 200ms response time)
- **Async Processing**: Extended Celery for email notifications, reports, PDF generation; implemented retry logic and monitoring
- **Documentation**: Created technical guides for API clients and new developers

**Tech**: Django, Django REST Framework, PostgreSQL, Celery, Docker, Sentry, OAuth2, pytest

---

### Middle Backend Engineer — ELEKS (Jul 2022 – Jun 2023, 12 months)

**Renewable Energy Management Platform** | 300+ business accounts | Django/PostgreSQL/Celery

**Key Responsibilities**:

- Backend services for time-series energy consumption data (PV-Wind systems)
- CSV/XLSX data import pipelines for meter readings
- Database performance optimization

**Technical Accomplishments**:

- **Data Processing**: Designed validation and transformation logic for time-series energy data; handled format standardization and error reporting
- **Bulk Import Pipeline**: Implemented CSV/XLSX upload with data sanitization, validation, and error reporting for large datasets
- **Performance Profiling**: Used cProfile to identify bottlenecks; proposed optimization strategies to team
- **API Design**: Collaborated with frontend on response formats and error handling for consistent data consumption
- **Testing**: Contributed comprehensive unit and integration tests (pytest)

**Tech**: Django, Django REST Framework, PostgreSQL, Celery, Docker, pytest, REST APIs

---

### Junior Python Developer — Inoxoft, SoftServe (2019 – 2022, 3 years)

**Data-Driven Mining & SaaS Platforms** | Django/GraphQL | Multiple projects

- REST and GraphQL API development
- Supported Python 2.7 → 3.x migration
- Database schema design and migrations
- Django admin customization
- Code review participation
- Bug fixes and feature delivery

---

## api-observatory: Job-Ready Learning Project

### [GitHub: api-observatory](https://github.com/ivanprytula/api-observatory)

A production-grade learning project demonstrating **8 phases** of backend system design.

### Why I Built This

To consolidate 5 years of production experience into a **reference implementation** showing:

- ✅ How strong middle engineers think about system design
- ✅ Real patterns from production services (event streaming, resilience, observability)
- ✅ How to communicate technical decisions (ADRs, architecture docs)
- ✅ Production-ready code quality (type hints, testing, logging)

### Project Status (8 Phases)

| Phase | Focus                   | Status     | Key Takeaway                                            |
| ----- | ----------------------- | ---------- | ------------------------------------------------------- |
| **1** | Event Streaming (Kafka) | ✅ Complete | Async producers/consumers, idempotency, DLQ patterns    |
| **2** | Data Scraping           | ✅ Complete | Backpressure, error handling, rate limiting             |
| **3** | AI + Vectors            | ✅ Complete | Multi-service architecture, embeddings, semantic search |
| **4** | Resilience              | ✅ Complete | Circuit breaker, retries, graceful degradation          |
| **5** | CQRS + Analytics        | 🚀 Active   | Background workers, async tasks, Prometheus metrics     |
| **6** | Dashboard               | ⏹️ Queued   | Server-side rendering, real-time SSE                    |
| **7** | Cloud IaC               | ✅ Complete | Terraform, AWS multi-env, secrets management            |
| **8** | Production Hardening    | ✅ Complete | Prometheus/Grafana stack, k6 load tests, chaos.sh gauntlet, Ansible automation |

### Technical Highlights

- **Async-first architecture**: FastAPI + SQLAlchemy 2.0 async, asyncpg driver
- **Production observability**: Prometheus metrics, OpenTelemetry tracing, structured JSON logging
- **Resilience patterns**: Circuit breaker, dead letter queue, backpressure, idempotent processing
- **Testing pyramid**: Unit tests (in-memory SQLite), integration tests (PostgreSQL), e2e tests
- **CI/CD**: GitHub Actions split into unit/integration workflows
- **Infrastructure support**: Docker Compose (local), Terraform basics, deployment workflow automation
- **Documentation**: Numbered learning path, architectural decisions recorded (ADRs)

### What This Demonstrates for Hiring

1. **T-Shaped Technical Depth**:
   - Deep: Async systems, databases, data pipelines

- Support-level: CI/CD, deployment workflows, observability tooling
- Breadth: Can solve problems across the stack, not just write endpoints

1. **Production Thinking**: Built with real patterns from production systems (event streaming, CQRS, idempotent processing, monitoring)
2. **Communication**: Documentation, ADRs, runbooks demonstrate ability to explain complex systems clearly
3. **Best Practices**: Type hints, comprehensive testing, structured logging, CI/CD integration, infrastructure-as-code
4. **Continuous Learning**: Proactively building patterns, documenting trade-offs, staying current with ecosystem

---

## Skills Summary

### Languages & Frameworks

- **Python 3.x** (10+ years): Django, Django REST Framework, FastAPI, Celery
- **SQL/PostgreSQL**: Query optimization, indexing, MVCC, transaction management
- **JavaScript**: Basic (frontend debugging, API client testing)

### Backend Patterns

- Async/await, event streaming, resilience (circuit breaker, DLQ, backpressure)
- REST API design, OAuth2, webhook handling
- Database query optimization, connection pooling, caching strategies

### Infrastructure & DevOps

- **Docker**: Containerization, multi-stage builds, image optimization, Compose stacks
- **Kubernetes**: Disposable app-owned k3d lab with deployments, services, ingress, and Kustomize; no EKS operation claimed
- **AWS (portfolio IaC)**: Statically validated VPC/ECR/EC2/EBS/S3/SSM Terraform and OIDC delivery contracts; live deployment not yet claimed
- **Ansible**: Idempotent common, Docker, and AWS MVP host-bootstrap roles using SSM inventory inputs; statically validated only
- **CI/CD**: GitHub Actions with multi-lane matrix (lint, unit, integration, docker-build, security scan), branch protection, digest-based promotion, GitHub Environments with OIDC
- **Monitoring**: App-owned local Prometheus/Grafana/Alertmanager profiles, OpenTelemetry tracing, and structured JSON logging
- **Chaos / Load testing**: Bounded k6 observations workload and opt-in local PostgreSQL stop/recovery proof

### Observability & Monitoring

- Structured logging, JSON formatters, log aggregation (VictoriaLogs, OpenSearch, Loki/Promtail)
- Prometheus metrics and app-owned local Grafana dashboards
- APM (Sentry error tracking, distributed tracing with OpenTelemetry)
- Load/chaos engineering: k6 thresholds (p95<500ms, error rate<5%), container kill-recovery drills, readiness-based health assertions

### Development Practices

- Testing: pytest, fixtures, mocking, unit/integration/e2e coverage
- Code review: Pull requests, merge strategies, documentation
- Agile: Estimation, refinement, sprint ceremonies, cross-functional collaboration
- Documentation: Technical guides, API contracts, runbooks, ADRs

---

## What I'm Looking For

**Middle → Middle+ roles** where I can:

- ✅ Own technical decisions on complex systems (not just implement specs)
- ✅ Contribute to architecture discussions alongside senior engineers (learn how decisions are made)
- ✅ Solve hard problems: database optimization, async complexity, system reliability
- ✅ Work with engineers I can learn from (mentor relationships, not management roles)
- ✅ Grow through real projects: take on progressively harder technical problems
- ✅ Work on data-intensive or scalability-focused systems (where my expertise adds value)

**What I'm NOT looking for yet**: Management roles, team lead positions (need more project/team experience first).

**Industries**: **Any** where I can solve interesting technical problems — SaaS, data platforms, fintech (non-crypto), distributed systems, developer tools, startups. Domain-agnostic; technology and problem-solving focused.

---

## Contact & Projects

- **GitHub**: [github.com/ivanpytula](https://github.com/ivanpytula)
- **api-observatory (Learning Project)**: [github.com/ivanpytula/api-observatory](https://github.com/ivanpytula/api-observatory)
- **Email**: [Available on request]

---

## Interview Talking Points

### "Tell me about a time you diagnosed a production issue."

→ "Discovered connection pool exhaustion causing weekly service restarts. Root cause: SQLAlchemy pool size too small + stale connections not detected. Fixed through pool tuning and health checks. Zero restarts after. Taught team the pattern."

### "What's your approach to slow queries?"

→ "Run EXPLAIN ANALYZE. Check: sequential vs index scan, row selectivity, join order. Diagnose whether it's missing index or inefficient query logic. Add indexes only after confirming selectivity. Document the pattern for team."

### "How do you ensure system reliability?"

→ "Combination: circuit breaker for external calls, DLQ for failed processing, backpressure to prevent queue overflow, async for I/O efficiency. Instrument everything (metrics, traces, logs). Alert on anomalies. Test failure scenarios before production."

### "Describe your experience with Kubernetes."

→ "Deployed FastAPI services to Kubernetes via GitLab CI/CD. Configured resource requests/limits, health checks, scaling policies. Debugged pod issues using kubectl logs, port-forward. Familiar with cluster operations but not cluster setup/management."
