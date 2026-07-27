# Application CI/CD

Workflow YAML under [`.github/workflows/`](../../.github/workflows/) is the executable source of
truth. This page explains gate intent and ownership without duplicating job steps or command
syntax.

## Quality Gates

The main CI workflow runs lint, formatting, type, unit, contract, security, dependency, image, and
documentation checks according to the changed path and workflow trigger. Slow integration and
smoke work is explicitly gated. The workflow files and branch protection settings decide which
jobs block a merge.

## Workflow Ownership

| Workflow | Responsibility |
| --- | --- |
| [`ci.yml`](../../.github/workflows/ci.yml) | Main quality gates, tests, contracts, and candidate images |
| [`security.yml`](../../.github/workflows/security.yml) | Security analysis and dependency/image evidence |
| [`security-secrets-lite.yml`](../../.github/workflows/security-secrets-lite.yml) | Blocking secrets scan |
| [`pip-audit.yml`](../../.github/workflows/pip-audit.yml) | Scheduled/manual dependency audit |
| [`performance-smoke.yml`](../../.github/workflows/performance-smoke.yml) | Manual/weekly authenticated load baseline |
| [`release.yml`](../../.github/workflows/release.yml) | Immutable candidate promotion |
| [`cd-dev.yml`](../../.github/workflows/cd-dev.yml) | Approved AWS Stage 0 deployment through SSM |

## Artifact and Identity Contract

CI builds ingestor, inference, and dashboard candidates tagged `tree-<SHA>`. Release promotion
reuses those candidates rather than rebuilding or publishing `latest`. AWS workflows use GitHub
OIDC and remain skipped until `AWS_CD_ENABLED=true`, the required variables, and the protected
environment exist. The [OIDC setup](github-secrets-setup.md) owns role and variable expectations;
the [deployment contract](../07-deployment/app-repo-contract.md) owns image names, ports, health
behavior, and environment interfaces.

## Delivery Evidence

Workflow YAML and infrastructure configuration are **Decision** evidence. A completed deployment
claim requires an approved live run with retained image identity, health/readiness, migration,
smoke, rollback, and teardown evidence. Use the sibling
[infra deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md)
for platform preparation and recovery boundaries.
