# Project Evolution and Growth Playbook

Track: C — Architecture and Platform Strategy


This playbook defines how to evolve API Observatory without losing technical focus or
operational clarity.

## Purpose

Use this when planning or implementing:

- New functionality in existing services
- New services or bounded contexts
- Dependency additions/removals
- UI framework changes (for example HTMX to React/Next.js)
- Third-party integrations (auth, billing, notifications, analytics)
- Lightweight user-value reframing for the solo-founder scenario

## Decision Flow

1. Define product value change: what user pain is solved and for whom.
2. Choose architectural placement: existing service vs new service.
3. Define contract surface: APIs, events, schemas, ownership.
4. Choose dependency strategy: add, replace, or remove libraries.
5. Define operational impact: CI/CD, observability, rollback, security.
6. Define practical impact using the four-question business layer below.
7. Implement in small slices with measurable acceptance criteria.

### Vertical-Slice Estimation

When scoping a task or ticket, answer it as one cohesive vertical slice and give an honest range —
not a single optimistic number. Trace the work end to end before estimating:

- Does it need a database migration (forward-only, run before rollout)?
- Does it bump a cross-service contract (`libs/contracts/VERSION` + changelog)?
- Does it add or change tests (the three-test set per endpoint, integration coverage)?
- Does it need a rollout step (feature flag, expand-contract, ordered deploy)?

A ticket that looks small at the API layer can be a five-minute change or a five-hour change once
the migration, contract bump, tests, and rollout are counted. Surface that hidden cost up front so
the range is honest. This complements ACROSS — which already covers Python-first and
YAGNI/anti-overengineering (see [CLAUDE.md](../../CLAUDE.md)) — and is not a new priority system; it
is a habit applied while working the Decision Flow above.

## Change Types

### 1. Existing Service Feature Expansion

Use when feature fits current service bounded context.

Checklist:

- Update service-level README and endpoint contract.
- Add integration tests first for critical path.
- Add migration if schema changes.
- Add metrics/log fields for new flow.
- Update docs Track B and Track C only once (canonical location).

### 2. New Service Introduction

Use when domain ownership or scaling profile is different.

Checklist:

- Define ownership boundary and interfaces.
- Add compose profile and health checks.
- Add CI test stage and smoke check.
- Add observability baseline (logs, metrics, traces).
- Add ADR entry for service boundary decision.

### 3. Dependency Lifecycle (Add/Remove)

Checklist:

- Justify dependency with an explicit problem statement.
- Record blast radius (security, transitive deps, maintenance risk).
- Prefer one dependency per capability.
- Add/remove from pyproject and lockfile in same PR.
- Add migration/fallback plan when replacing dependencies.

## UI Framework Evolution

Use this matrix when adding a dedicated frontend framework.

| Option | Best for | Risks | Rule |
| ----- | -------- | ----- | ---- |
| Keep HTMX/Jinja2 | Low-complexity internal admin UI | Limited client state patterns | Default for ops/admin workflows |
| React/Vite SPA | Rich client interaction, frequent UX changes | Build complexity, API contract drift | Adopt when UX complexity is dominant |
| Next.js | SEO/public product pages + app shell | SSR/build/runtime complexity | Adopt when product-facing UX needs SEO + scale |

Implementation rule:

- Keep backend APIs framework-agnostic.
- Keep auth/session boundary in backend.
- Add frontend as a separate track in docs once adopted.

## Third-Party Integrations

For each integration, document:

- Purpose and fallback mode
- Data contracts (input/output/error)
- Timeout/retry/circuit-breaker behavior
- Secret and key management model
- Cost and rate-limit model
- Removal strategy (exit plan)

## Lightweight Business Layer

For each major feature, answer only these questions:

1. Who experiences the problem?
2. What failure or cost does it create?
3. How does this implementation reduce that risk?
4. At what scale would the current approach stop being appropriate?

The standing example is a solo SaaS developer monitoring third-party dependencies. Customer
acquisition, billing, permanent hosting, and ongoing product operations are non-goals.

## Governance Rules

- One canonical doc per topic. Other docs link, not duplicate.
- Every major architecture shift must have an ADR.
- Every positioning shift must remain consistent with the lightweight business layer.
- Historical snapshots stay in Track E and are labeled as dated.

## Execution Cadence

- Weekly: feature progress + dependency review + docs sync.
- Monthly: roadmap, priorities, evidence status, and interview readiness review.
- Quarterly: architecture triggers and deferred decisions review.
