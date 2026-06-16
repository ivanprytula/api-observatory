# Project Evolution and Growth Playbook

Track: C — Architecture and Platform Strategy


This playbook defines how to evolve Data Zoo without losing product clarity or delivery speed.

## Purpose

Use this when planning or implementing:

- New functionality in existing services
- New services or bounded contexts
- Dependency additions/removals
- UI framework changes (for example HTMX to React/Next.js)
- Third-party integrations (auth, billing, notifications, analytics)
- Product value reframing, monetization options, or GitHub Sponsors positioning

## Decision Flow

1. Define product value change: what user pain is solved and for whom.
2. Choose architectural placement: existing service vs new service.
3. Define contract surface: APIs, events, schemas, ownership.
4. Choose dependency strategy: add, replace, or remove libraries.
5. Define operational impact: CI/CD, observability, rollback, security.
6. Define business impact: pricing story, sponsorship narrative, GTM signal.
7. Implement in small slices with measurable acceptance criteria.

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

## Product Value Reframing

Use this template before changing project positioning:

1. Core user segment: who benefits first.
2. Core pain solved: what becomes faster/cheaper/safer.
3. Evidence: measurable outcomes already in repo.
4. Storyline: one-sentence value proposition.
5. Monetization hypothesis: what someone would pay for.

## Monetization and Sponsorship Paths

### Path A: Open Core + Paid Enablement

- Open source core pipeline and reference architecture.
- Paid offerings: implementation support, architecture reviews, migration playbooks.

### Path B: Managed Templates and Accelerators

- Paid setup templates: cloud-ready terraform stacks, hardened CI packs, observability starter kits.
- Subscription for updates and support.

### Path C: GitHub Sponsors Strategy

- Public roadmap with sponsor-priority labels.
- Sponsor tiers tied to outcomes:
  - Tier 1: early access docs/templates
  - Tier 2: monthly architecture office hours
  - Tier 3: implementation review and migration guidance
- Publish monthly changelog with sponsor acknowledgments.

## Governance Rules

- One canonical doc per topic. Other docs link, not duplicate.
- Every major architecture shift must have an ADR.
- Every product-positioning shift must update Track D docs.
- Historical snapshots stay in Track E and are labeled as dated.

## Execution Cadence

- Weekly: feature progress + dependency review + docs sync.
- Monthly: roadmap/priorities and sponsorship narrative refresh.
- Quarterly: architecture and monetization hypothesis review.
