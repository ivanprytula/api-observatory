# Gaps & Audit Log

---

## Legend

| Icon | Meaning |
|------|---------|
| ✅ | Resolved/Completed |
| 🟡 | Minor / cosmetic / accept as-is |
| 🟠 | Post-MVP polish / deferred |
| 🔴 | Unresolved — needs code or infra work |

---

## Documentation Gaps (Doc Consolidation — 2026-06-17)

Gaps identified during the docs/ consolidation and filled in the same session.

| # | Gap | Resolution | Document |
|---|-----|-----------|----------|
| ✅ D1 | **MVP vs Post-MVP tech stack** — no single document mapped technology choices per phase | Added MVP vs Post-MVP table with 14 components, each with rationale | `03-planning/mvp-roadmap.md:51` |
| ✅ D2 | **Feature→Technology→Reasoning matrix** — no decision trace from capability to tech choice | Added 23-row table with feature, MVP flag, technology, alternatives, ADR ref | `03-planning/mvp-roadmap.md:72` |
| ✅ D3 | **DevOps/SRE promotion checklist** — no pre-prod→prod linear checklist | Added 44-item checklist: pre-flight, pre-deploy, deploy, smoke-test, post-deploy, rollback | `07-deployment/deployment-guide.md:7` |
| ✅ D4 | **User documentation** — no end-user guide | Merged 5 source files into one user guide with MVP/post-MVP badges; Post-MVP sections have stubs | `09-user-guides/user-guide.md` |

---

## Original Audit Gaps (Audit date: 2026-06-16)

| # | Gap | Detail | Status | Owner |
|---|-----|--------|--------|-------|
| 🟡 1 | `streamlit_app.py` not at repo root | Plan said single file at root; lives at `services/dashboard/streamlit_app.py`. Docs reference correct path — design divergence only. | Accept as-is | — |
| ✅ 2 | `docs/dev/developer-guide.md` missing | Commit 14c planned a master admin/dev guide. Never created. | **Resolved.** Contents now in `05-development/dev-workflows.md` + `05-development/policies.md`. | Doc consolidation |
| 🔴 3 | **Loki/Promtail/Mailpit undeployable** | Config files exist (`promtail.yml`, `alertmanager.yml`, Grafana `loki.yml` datasource) but reference `loki:3100` / `mailpit:1025` which aren't in any docker-compose. The Phase 6 monitoring stack is configured but dead. | Unresolved | Phase 6 |
| 🔴 4 | **PostgreSQL RLS not implemented** | App-level tenant isolation (ContextVar + TenantMiddleware) works, but no database-level `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` or `CREATE POLICY` in any migration. `tests/test_rls.py` tests app-level isolation, not PostgreSQL-native RLS. | Unresolved | Phase 7 |
| 🔴 5 | **REPEATABLE READ isolation demo missing** | Plan Phase 3d required `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` in analytics rollup. Documented as concept in Backend Concepts and Patterns but no code. | Unresolved | Phase 3 |
| 🔴 6 | **Auth coverage incomplete** | Only 4/21 routers have auth on every endpoint (scorecards, source_registry, contract_drift, abuse_detection). Observations CRUD, agent, analytics, reporting, insights, subscriptions, notifications, etl, scraper, background_processing, vector_search, mongo_analytics have unprotected routes. | Unresolved | Cross-cut |
| 🔴 7 | **No dedicated agent router tests** | Agent endpoints (`/enrich`, `/enrich/review`, `/resume`, `/stream`) have zero dedicated tests. | Unresolved | Cross-cut |
| 🔴 8 | **No WebSocket HTTP-level tests** | `ws.py` has no HTTP-level test coverage. | Unresolved | Cross-cut |

---

## How to Update

- When a gap is resolved, change the icon to `✅` and add a resolution note.
- Add new gaps at the bottom of the relevant section with today's date.
- Leave the `Owner` column as the original phase — add a "Closed by" note when resolved.
