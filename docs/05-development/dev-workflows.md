# Development Workflows

The [`Justfile`](../../Justfile) is the command catalogue. This guide owns intent, proof selection,
and stable development rules so command syntax is not duplicated in Markdown.

## Development Loop

1. Run `just doctor`, then choose direct HTTP hot reload (`just dev`) or HTTPS ingress parity
   (`just up`).
2. Apply migrations before exercising changed persistence behavior.
3. Run the smallest focused unit/integration test while iterating.
4. Run the affected service boundary, contract, security, and documentation checks.
5. Review the diff, migration compatibility, telemetry, and rollback path.
6. Run the applicable pre-commit and CI-equivalent gates before considering the change complete.

Use [setup](../04-setup/setup-guide.md) for runtime modes. The
[CI/CD reference](../06-ci-cd/ci-cd.md) explains automated gates.

## Proof Selection

| Change | Minimum focused proof |
| --- | --- |
| Pure domain/helper | Unit test for success and failure behavior |
| API/auth/tenant behavior | ASGI integration test including unauthorized/cross-tenant regression |
| Model/schema | Alembic upgrade/downgrade plus PostgreSQL integration test |
| Cross-service contract | Contract version check and both producer/consumer tests |
| Cache/broker/provider boundary | Dependency failure/recovery and fail-open/fail-closed assertion |
| Query/performance | Captured workload and query plan in the performance worksheet |
| Deployment interface | Machine-readable app/infra contract validator and image health checks |
| Documentation only | Docs quality, links, stale-claim search, and diff check |

The maintained test recipes and flags live in the [`Justfile`](../../Justfile); CI definitions live
under [`.github/workflows/`](../../.github/workflows/).

## Test Architecture

| Suite | Dependency boundary | Purpose |
| --- | --- | --- |
| Unit | In-memory/mocked boundary | Deterministic behavior and failure rules |
| Integration | PostgreSQL/Redis/service container as applicable | Persistence, migrations, auth, concurrency, and service contracts |
| Contract | In-process OpenAPI/shared schemas | Backward compatibility and protected-route behavior |
| End-to-end/smoke | Running local stack | Critical user and deployment path |
| Performance/fault | Explicit opt-in workload | Measurement, degradation, recovery, and remaining uncertainty |

Shared fixtures live in [`tests/fixtures_shared.py`](../../tests/fixtures_shared.py). Root and
ingestor `conftest.py` files re-export them; fixture logic should not be copied between trees.
Inference and MCP keep service-owned suites because their dependency boundaries differ.

## Durable Engineering Rules

- Preserve backward compatibility unless a breaking change is explicitly approved.
- Keep routes thin and persistence tenant-scoped; use parameterized database access.
- Treat Alembic as schema authority and use expand/contract sequencing for rollout compatibility.
- Bound every network call, retry only safe work, and document fail-open/fail-closed behavior.
- Do not add a service, datastore, framework, or dependency without a current evidence gap.
- Keep `libs/` independent from `services/`; validate shared contracts at process boundaries.
- Never hardcode or print secrets. Use placeholder/example configuration only.
- Update durable architecture, contract, or recovery documentation in the same change; omit
  transient progress notes.

## Review Focus

Check authorization, data ownership, bounded queries/payloads, migration compatibility, timeout and
retry behavior, useful telemetry, and rollback. New code should follow the project-specific
instructions in [`.github/copilot-instructions.md`](../../.github/copilot-instructions.md); generic
language/tool rules do not need to be repeated here.

## Specialized Evidence

- API collections live under [`bruno/`](../../bruno/) and are exercised by the maintained recipe.
- Authenticated k6 smoke ownership lives in
  [`performance-smoke.yml`](../../.github/workflows/performance-smoke.yml) and its script.
- Contract versioning is owned by [`libs/contracts`](../../libs/contracts/) and
  [`scripts/bump_contracts_version.py`](../../scripts/bump_contracts_version.py).
- Performance and recovery records use the
  [performance/failure worksheet](performance-and-failure-lab.md).
- Cloud provisioning and rollback belong to the infra
  [deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md).
