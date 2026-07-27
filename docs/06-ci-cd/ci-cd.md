# Application CI/CD

Workflow YAML under [`.github/workflows/`](../../.github/workflows/) is the executable source of
truth. This page explains ownership, gate intent, and the app/infra boundary without copying job
steps or commands.

## Pull Request and Push Gates

The main CI workflow detects affected paths, runs lint/type/compile checks, unit and contract tests,
and conditionally runs database, service, image, and documentation work. Slow integration/E2E work
is explicitly gated rather than silently presented as part of every fast path.

Required evidence depends on the change:

- application behavior: focused tests plus affected integration/contract coverage;
- schema: migration compatibility and PostgreSQL proof;
- shared contract: version/changelog guard plus producer/consumer coverage;
- service image: build and vulnerability scan;
- documentation: quality/link/status checks;
- security boundary: dedicated security workflow and blocking Gitleaks scan.

The workflow files and branch protection settings—not this prose—decide which jobs block a merge.

## Workflow Ownership

| Workflow | Responsibility |
| --- | --- |
| [`ci.yml`](../../.github/workflows/ci.yml) | Main quality gates, tests, contract checks, and conditional candidate images |
| [`security.yml`](../../.github/workflows/security.yml) | Security analysis and image/dependency evidence |
| [`security-secrets-lite.yml`](../../.github/workflows/security-secrets-lite.yml) | Blocking secrets scan |
| [`pip-audit.yml`](../../.github/workflows/pip-audit.yml) | Scheduled/manual dependency audit |
| [`performance-smoke.yml`](../../.github/workflows/performance-smoke.yml) | Weekly/manual authenticated k6 baseline |
| [`release.yml`](../../.github/workflows/release.yml) | Promote existing immutable candidates to a semantic version |
| [`cd-dev.yml`](../../.github/workflows/cd-dev.yml) | Approved AWS Stage 0 deployment through Systems Manager |

## Artifact and Identity Contract

CI builds ingestor, inference, and dashboard candidates tagged `tree-<SHA>`. Release promotion
reuses those candidates rather than rebuilding or publishing `latest`. AWS jobs use GitHub OIDC and
remain safely skipped until the required repository variables and protected environment exist.

The app-owned [OIDC setup](github-secrets-setup.md) defines variable/role expectations. The infra
repository must supply ECR, EC2/RDS, IAM trust/policies, runtime secret delivery, and deployment
targets. The [deployment contract](../07-deployment/app-repo-contract.md) protects image names,
ports, health behavior, and environment interfaces.

## Delivery Status

Local image and contract validation is evidence. Workflow YAML and Terraform configuration are
**Decision** evidence. A completed deployment claim requires an approved live run with redacted
image, health, migration, smoke, rollback, and teardown evidence.

Use the infra
[deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md)
for preparation, verification, rollback, and teardown boundaries.
