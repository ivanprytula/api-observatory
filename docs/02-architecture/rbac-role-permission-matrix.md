# RBAC Policy & Role-Permission Matrix

Source of truth for authorization in the ingestor service. Enforced by Casbin
(`security/casbin_model.conf` + `security/casbin_policy.csv`) and the
route-level guards in `routers/`.

## Roles & scope

| Role | Scope | Who it is | Mechanism |
|---|---|---|---|
| `root` | **Global** (all tenants) | Platform/SRE break-glass identity (`config.superadmin_subject`, default `"root"`) | Matcher short-circuit `is_superuser(r.sub)` + `TenantMiddleware` RLS bypass (`user_role="admin"`). No g-rules needed. |
| `admin` | Per-tenant | Tenant owner | Casbin `g(root? no) g(sub, "admin", <tenant>)`; bypasses tenant RLS via `app.user_role="admin"`. |
| `manager` | Per-tenant | Tenant power-user | Inherits `user` via `g(admin, manager, *)` / `g(manager, user, *)`; reaches manager/admin-gated routes. |
| `user` | Per-tenant | Basic member | `g(sub, "user", <tenant>)`; does **not** inherit `manager`/`admin`. |

## Permission matrix

`✓` = allowed · `✗` = denied · blank = not applicable / not exposed.

| Capability | `root` | `admin` | `manager` | `user` |
|---|---|---|---|---|
| Observations: read (list/get) | ✓ all | ✓ tenant | ✓ tenant | ✓ tenant |
| Observations: create | ✓ | ✓ | ✓ | ✓ |
| Observations: update / archive (patch) | ✓ | ✓ | ✓ | ✓ |
| Observations: hard-delete | ✓ | ✓ | ✓ | ✗ |
| Sources: read (list/get/health) | ✓ | ✓ | ✓ | ✓ |
| Sources: create | ✓ | ✓ | ✓ | ✗ |
| Sources: update (patch) | ✓ | ✓ | ✓ | ✗ |
| Sources: delete (deactivate) | ✓ | ✓ | ✓ | ✗ |
| Agent runs: get / resume | ✓ | ✓ | ✓ | ✓ |
| Incidents: acknowledge / resolve | ✓ | ✓ | ✓ | ✓ |
| Contract drift: read / accept baseline | ✓ | ✓ | ✓ | ✓ |
| Abuse detection: read / mark | ✓ | ✓ | ✓ | ✓ |
| Reporting: read | ✓ | ✓ | ✓ | ✓ |
| Analytics: stats / timeseries / tenant-status | ✓ | ✓ | ✓* | ✓* |
| Analytics: refresh materialized view | ✓ | ✓ | ✗ | ✗ |
| Analytics: materialized-view stats | ✓ | ✓ | ✗ | ✗ |
| Vector search (semantic / ingest) | ✓ | ✓ | ✗ | ✗ |
| Scorecards: create / list | ✓ | ✓ | ✗ | ✗ |
| Subscriptions | ✓ | ✓ | ✗ | ✗ |
| User management: create / delete / update / list / promote | ✓ | ✓ | ✗ | ✗ |

`*` analytics read routes accept any authenticated tenant user; the **refresh**
and **materialized-view stats** mutations are admin-only.

## Enforcement map (route guards)

| Guard | Roles reach it | Example routes |
|---|---|---|
| `casbin_guard("admin")` | `root` (bypass) · `admin` | User CRUD (`/api/v1/admin/users`), analytics refresh/stats, vector search, scorecards, subscriptions, source-admin mutations |
| `casbin_guard("manager","admin")` | `root` (bypass) · `manager` · `admin` | Observation hard-delete `DELETE /api/v1/observations/{id}`; source create/patch/delete |
| `casbin_guard("user","admin")` | `root` (bypass) · `manager` · `admin` · `user` | Observation create/update/archive; agent runs; incidents ack/resolve; contract drift; abuse detection; reporting; source read |
| `is_superuser(sub)` (matcher) | `root` only | Global bypass applied in `casbin_model.conf` matcher + `TenantMiddleware` RLS `app.user_role="admin"` |

Notes:

- `casbin_guard` is an **OR over required roles** — `casbin_guard("user","admin")`
  passes if the subject has *either* role (so `user`, `manager`, `admin` all pass).
- The `g` hierarchy is `admin → manager → user` (declared in
  `security/casbin_policy.csv`). Therefore a `manager` satisfies every
  `("user","admin")` guard transitively, and `admin` satisfies
  `("manager","admin")` transitively — but `user` does **not** satisfy
  `("manager","admin")`. This is what makes `manager` a real tier: it can reach
  the `manager/admin` routes (observation hard-delete, source CRUD) that a plain
  `user` cannot.
- Roles are **tenant-scoped**: `assign_user_role(db, username, role, tenant_id=...)`
  writes the g-rule in `domain = str(tenant_id)`. A `manager` in tenant 10
  cannot act as manager in tenant 11 unless assigned there.

## How to extend (keep it flexible)

- **New route tier**: `Depends(casbin_guard("manager","admin"))` — reuse the
  existing hierarchy; no model change.
- **New role**: add to `security/casbin_policy.csv`:

  ```csv
  p, analyst, *, *, access
  g, manager, analyst, *     # manager inherits analyst
  ```

  then gate the route `casbin_guard("analyst","manager","admin")`.
- **Assign a role to a user** in a tenant:

  ```python
  from services.ingestor.auth import assign_user_role

  await assign_user_role(db, username="alice", role="manager", tenant_id=10)
  ```

- **Root credential**: set `SUPERADMIN_PASSWORD` (argon2-hashed at first startup
  by `core/bootstrap.py:ensure_superadmin`); the reserved subject is
  `SUPERADMIN_SUBJECT` (default `root`). Root authenticates like any user via
  `/auth/token` — no separate store.

## Audit

`casbin_guard` emits an `authz.sudo` audit event (via `libs.platform.auth`)
for every request authorized through the `is_superuser` short-circuit, so
root bypasses are attributable in the security log.
