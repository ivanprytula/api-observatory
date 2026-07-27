# Never-Regress Application Baseline

These controls are the application quality/security floor. Tool configuration, CI, code, and tests
are authoritative; this page records only durable invariants and their owners. The sibling infra
[baseline](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/architecture/baseline-checklist.md)
owns Terraform, Kubernetes, and platform SRE controls.

## Quality and Compatibility

| Invariant | Enforced or proven by |
| --- | --- |
| Formatting, lint, typing, and compile checks remain clean | [`pyproject.toml`](../../pyproject.toml), [pre-commit](../../.pre-commit-config.yaml), [CI](../../.github/workflows/ci.yml) |
| Unit and integration suites exercise affected behavior | [`tests/`](../../tests/), service-owned test trees, CI |
| Protected OpenAPI routes reject anonymous generated requests | [contract tests](../../services/ingestor/tests/contract/) |
| Shared schema changes are versioned and documented | [`libs/contracts`](../../libs/contracts/), contract version guard |
| Alembic is schema authority; rollout remains expand/contract compatible | [`alembic/`](../../alembic/), migration tests |
| Documentation links and claims remain current | [`docs_quality_check.py`](../../scripts/ci/docs_quality_check.py) |

## Security and Data

| Invariant | Enforced or proven by |
| --- | --- |
| Authentication and authorization deny by default | [security architecture](security-architecture.md), auth/contract tests |
| Tenant-scoped access cannot cross tenant boundaries | repository filters, authorization tests, opt-in PostgreSQL RLS tests |
| User-controlled outbound URLs pass scheme/DNS/IP SSRF checks | source registration/probe validation and tests |
| SQL is parameterized and queries/payloads are bounded | SQLAlchemy repositories and focused performance tests |
| Secrets are not hardcoded, logged, or committed | settings classification, redaction, Gitleaks, example-only config |
| Security events preserve bounded audit evidence without unnecessary PII | security audit models, metrics, and tests |

## Runtime and Supply Chain

| Invariant | Enforced or proven by |
| --- | --- |
| Network calls have timeouts; retries are safe and bounded | [`libs/platform`](../../libs/platform/), fault tests |
| Optional cache, broker, telemetry, and AI paths fail as documented | feature flags and dependency failure tests |
| Service images run non-root as UID 10001 and satisfy health contracts | Dockerfiles and [deployment contract](../07-deployment/app-repo-contract.md) |
| Dependencies and images receive maintained vulnerability checks | dependency/security workflows and container scans |
| Image provenance uses immutable `tree-<SHA>` candidates | application CI/release workflows |
| `libs/` never imports service internals | service-boundary check |

## Maintenance Rule

Revisit the affected row when adding a service/dependency, changing a contract/schema, or moving a
deployment boundary. Add tooling only to close a named control gap. Detailed job names, commands,
and implementation status stay in their executable source or the
[engineering evidence map](engineering-topics.md).
