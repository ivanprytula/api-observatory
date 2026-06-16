# MVP & MVP+ Audit Gaps

Audit date: 2026-06-16. Cross-referenced 3 planning docs against actual codebase.

---

## 🟡 MVP Minor

| # | Gap | Detail | Fix |
|---|-----|--------|-----|
| 1 | `streamlit_app.py` not at repo root | Plan said single file at root; lives at `services/dashboard/streamlit_app.py`. Docs reference correct path, so functional — design divergence only. | Accept as-is or move to root. |

---

## 🟠 Post-MVP Polish (Commit 14)

| # | Gap | Detail | Fix |
|---|-----|--------|-----|
| 2 | `docs/dev/developer-guide.md` missing | Commit 14c planned a master admin/dev guide. Never created. | Create file with: prerequisites, setup sequence, daily dev loop, test commands, debugging, endpoint recipe, Floci workflow, pre-deploy gate. |

---

## 🔴 Senior Gaps Closure (Phases 1–7)

| # | Gap | Detail | Owner Phase |
|---|-----|--------|-------------|
| 3 | **Loki/Promtail/Mailpit undeployable** | Config files exist (`promtail.yml`, `alertmanager.yml`, Grafana `loki.yml` datasource) but reference `loki:3100` / `mailpit:1025` which aren't in any docker-compose. The Phase 6 monitoring stack is configured but dead. | Phase 6 |
| 4 | **PostgreSQL RLS not implemented** | App-level tenant isolation (ContextVar + TenantMiddleware) works, but no database-level `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` or `CREATE POLICY` in any migration. `tests/test_rls.py` tests app-level isolation, not PostgreSQL-native RLS. | Phase 7 |
| 5 | **REPEATABLE READ isolation demo missing** | Plan Phase 3d required `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` in the analytics rollup. Documented as concept in Backend Concepts and Patterns but no code. | Phase 3 |
| 6 | **Auth coverage incomplete** | Only 4/21 routers have auth on every endpoint (scorecards, source_registry, contract_drift, abuse_detection). Observations CRUD, agent, analytics, reporting, insights, subscriptions, notifications, etl, scraper, background_processing, vector_search, mongo_analytics have unprotected routes. | Cross-cut |
| 7 | **No dedicated agent router tests** | Agent endpoints (`/enrich`, `/enrich/review`, `/resume`, `/stream`) have zero dedicated tests. | Cross-cut |
| 8 | **No WebSocket HTTP-level tests** | `ws.py` has no HTTP-level test coverage. | Cross-cut |
