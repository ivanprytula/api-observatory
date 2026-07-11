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
| ✅ 3 | **Loki/Promtail/Mailpit undeployable** | Config files exist (`promtail.yml`, `alertmanager.yml`, Grafana `loki.yml` datasource) referencing `loki:3100` / `mailpit:1025`. Services were missing from docker-compose. | **Resolved.** All 6 services (Prometheus, Grafana, Loki, Promtail, Alertmanager, Mailpit) added to `docker-compose.yml` under `monitoring` profile. `just up-monitoring` starts the stack. Verified: all health endpoints respond, Grafana datasources auto-provisioned, Mailpit SMTP + web UI functional. Closed by: doc consolidation + commit `c963308`. | Phase 6 |
| 🟠 4 | **PostgreSQL RLS not implemented** | App-level tenant isolation (ContextVar + TenantMiddleware + repository filters) works and is correct for MVP. No database-level `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` or `CREATE POLICY` in any migration. `tests/test_rls.py` tests app-level isolation, not PG-native RLS. | **Deferred to post-MVP.** App-level isolation intentional for MVP scope. DB-level RLS + test update planned for Phase 7 hardening. | Phase 7 |
| 🟠 5 | **REPEATABLE READ isolation demo missing** | Plan Phase 3d required `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` in analytics rollup. Documented as concept in Backend Concepts and Patterns but no code. | **Deferred to post-MVP.** Analytics functionality (including rollups, materialized views, and isolation demos) is not part of the current MVP scope. | Phase 3 |
| 🟠 6 | **Auth coverage incomplete** | 29/97 routes have auth (30%). 4 routers fully covered (scorecards, source_registry, contract_drift, abuse_detection). 11 routers have zero auth (analytics, reporting, subscriptions, notifications, insights, vector_search, scraper, etl, background_processing, mongo_analytics, health). Auth infra exists (JWT, session, API-key+scope) but not applied system-wide. Notable: `api_keys.py` key management routes have zero auth. | **Deferred to post-MVP.** MVP auth infra is in place (4 core MVP routers fully covered). System-wide auth enforcement planned for post-MVP hardening. | Cross-cut |
| ✅ 7 | **No dedicated agent router tests** | Agent endpoints had zero dedicated tests (this row originally described `/enrich`, `/enrich/review`, `/resume`, `/stream` — an earlier aspirational design; see `bruno/z-agent/` for the historical shape). | **Resolved** (Phase 3 of `docs/.plans/ai-augmented-observatory-agent-mcp.md`). Actual agent is real and auto-triggered by critical/breaking drift events, not manually invoked per-observation — no `/enrich` or `/stream` endpoints exist. Real surface: `GET /api/v1/agent/runs/{id}`, `POST /api/v1/agent/runs/{id}/resume`. Tests: `services/ingestor/tests/unit/agent/` (nodes + full graph pause/resume) + `services/ingestor/tests/integration/test_agent_router.py`. Auth still not applied (that part of this gap rolls into gap 🟠6). | Cross-cut |
| ✅ 8 | **No WebSocket HTTP-level tests** | `ws.py` had no HTTP-level test coverage. | **Resolved.** 9 tests in `services/ingestor/tests/integration/observations/test_ws.py` cover: missing/invalid/expired/valid JWT auth, auth-disabled mode, cache-disabled fallback, connection lifecycle, and disconnect handling. Covered 55% of `ws.py` lines (auth logic + cache-disabled path fully covered; streaming logic requires live cache). | Cross-cut |

---

## How to Update

- When a gap is resolved, change the icon to `✅` and add a resolution note.
- Add new gaps at the bottom of the relevant section with today's date.
- Leave the `Owner` column as the original phase — add a "Closed by" note when resolved.
