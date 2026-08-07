# Cross-Functional Role Onboarding

Track: A — Product and Onboarding

This page explains how each Agile team role can approach this polyglot multi-stack project during onboarding.

## Shared First-Day Baseline

For technical roles, this baseline gives a reproducible local environment and a quick quality check.

```bash
just doctor
just dev-up
just db-migrate
just test-unit
just test-integration
```

For product and delivery roles, use the Project Overview, Architecture Overview, and Roadmap first.

## QA Engineer

### First Focus

- Validate core user and API flows in the Daily Development guide.
- Expand regression scenarios from the Commands Reference.
- Keep defect notes with clear reproduction and API payloads in `.local-dev/dumps`.

### Contribution Pattern

- Prioritize risk-based regression suites for ingestion, scheduling, and auth boundaries.
- Add integration assertions for failure paths, not only happy paths.

## AQA Engineer

### First Focus

- Stabilize automation around deterministic fixtures and CI parity.
- Use the Commands Reference as command source-of-truth.
- Build reusable test helpers per service boundary.

### Contribution Pattern

- Add smoke suites for PR gates and deep suites for nightly runs.
- Track flakiness sources and harden retries/timeouts with evidence.

## Data Engineer

### First Focus

- Map ingestion and transformation boundaries via the Architecture Overview.
- Inspect schema and migration path from the Pillar 2 Database guide.
- Validate batch and event paths through CQRS and storage targets.

### Contribution Pattern

- Optimize schema/index strategy with measurable query plans.
- Keep data contracts explicit between write-side and read-side services.

## AI/ML Engineer

### First Focus

- Review model and vector-related integration points in the Pillar 6 AI/LLM guide.
- Validate inference service contracts and payload shapes.
- Align offline experiments with production observability and rollback strategy.

### Contribution Pattern

- Treat model prompts and output schemas as versioned contracts.
- Ship features behind toggles with latency and quality guardrails.

## DBA

### First Focus

- Audit migration safety, query patterns, and retention policy.
- Use the Advanced SQL and CQRS guide and the Pillar 2 Database guide.
- Validate backup/restore procedures from operational scripts.

### Contribution Pattern

- Prefer additive zero-downtime migration strategies.
- Enforce index and partition policies against measured workloads.

## PM

### First Focus

- Build a feature map from Track A and Track C docs.
- Use the Roadmap for dependency-aware sequencing.
- Define clear outcome metrics per milestone.

### Contribution Pattern

- Keep roadmap tied to user value and operational risk reduction.
- Prioritize slices that produce testable, demoable outcomes every iteration.

## PO

### First Focus

- Translate backlog items into acceptance criteria linked to docs and APIs.
- Use the Evolution Playbook for value framing.
- Keep stakeholder language synchronized with technical constraints.

### Contribution Pattern

- Require each story to define user impact, contract changes, and rollout plan.
- Track value hypotheses and adjust backlog based on evidence.

## Security Specialist

### First Focus

- Review auth, session, RBAC, and header hardening paths.
- Validate dependency and image scanning process in the Docker Security Scanning Setup guide.
- Verify secret handling and environment separation.

### Contribution Pattern

- Shift-left threat checks into PR templates and CI gates.
- Prioritize remediation by exploitability and blast radius.

## Cloud-Native Engineer

### First Focus

- Review deployment and IaC flow in Cloud Deployment Model and Floci AWS Workflow.
- Validate local-to-cloud parity assumptions.
- Check infra drift and promotion workflow quality.

### Contribution Pattern

- Keep infrastructure modular, environment-aware, and testable.
- Treat observability and cost controls as first-class deployment requirements.

## SRE

### First Focus

- Review SLO/SLI expectations, alerting, and incident runbook paths.
- Validate instrumentation from service entrypoints to background workers.
- Check backup, restore, chaos, and rollback workflows.

### Contribution Pattern

- Drive reliability targets via measurable error budgets.
- Standardize post-incident feedback into architecture and backlog updates.

## System/Application Architect

### First Focus

- Re-evaluate service boundaries, coupling, and integration seams.
- Use adr/README.md and design/decisions.md for decision context.
- Align platform direction with product value and team capacity.

### Contribution Pattern

- Keep architecture decisions explicit, reversible where possible, and measurable.
- Balance simplicity now with extension points for future services and UI evolution.

## Role Onboarding Checklist

Day 1 / Week 1 / Month 1 milestones per role. Check off each milestone as it is complete.

| Role                             | Day 1                                                                | Week 1                                                        | Month 1                                                      |
| -------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ |
| **QA Engineer**                  | Run shared baseline; explore `/api/v1/observations` happy and error paths | Add 3+ regression scenarios for auth and ingestion boundaries | Risk-based regression suite merged and running in CI         |
| **AQA Engineer**                 | Run shared baseline; confirm CI test pass locally                    | Automate 2 smoke tests against PR gate                        | Nightly deep suite live; flakiness sources documented        |
| **Data Engineer**                | Inspect ingestion schemas and pipeline flow                          | Validate end-to-end record lifecycle with real payloads       | Data quality checks or pipeline extension merged             |
| **AI/ML Engineer**               | Understand data model and async job patterns                         | Prototype feature extraction or model hook against API        | Experiment notebook or ML pipeline integrated with ingestor  |
| **DBA**                          | Review ORM models and current Alembic migrations                     | Audit index coverage and query plans for key read paths       | Index and constraint recommendations merged; runbook updated |
| **Product Manager**              | Read `00-project-overview.md`, roadmap, and phase status             | Map user outcomes to current API surface                      | Backlog prioritized with measurable acceptance criteria      |
| **Product Owner**                | Read `00-project-overview.md` and `02-architecture/application-architecture.md`  | Define sprint goal with 3 measurable acceptance criteria      | First sprint delivered; retrospective findings logged        |
| **Security Specialist**          | Review auth flow, secrets management, and OWASP checklist            | Run dependency audit (`pip-audit`) and triage findings        | Security findings resolved or risk-accepted with ADR         |
| **Cloud-Native Engineer**        | Read the infra repository deployment guide; validate Docker Compose stack | Review Kubernetes manifests and CI pipeline                   | Infrastructure-as-code change or hardening PR merged         |
| **SRE**                          | Locate metrics, alerting config, and healthcheck endpoints           | Validate SLO targets, error budget, and incident runbook      | Post-incident review cycle established; runbook updated      |
| **System/Application Architect** | Read all ADRs and `02-architecture/{application,infrastructure}-architecture.md`  | Map service boundaries and identify coupling hotspots         | Architecture decision logged in `adr/`; backlog aligned      |

## Team-Level Working Agreement

- Use Track A for onboarding, Track B for execution, Track C for decisions, Track D for business narrative, and Track E for historical context.
- Keep one canonical source per topic and link from other docs instead of duplicating command blocks.
- Store noisy local investigation artifacts in `.local-dev/` and never in tracked docs.
