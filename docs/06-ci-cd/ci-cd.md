# Application CI/CD

The delivery path is intentionally small enough for one maintainer to run and explain end to end.
Workflow YAML under [`.github/workflows/`](../../.github/workflows/) is the executable source of
truth.

## Branch and Review Flow

Short-lived feature branches merge into `develop` through a pull request. A release-ready
`develop` merges into `main` through another pull request. Pushes and pull requests targeting
either protected branch run the same four CI jobs:

1. `Quality` validates boundaries, formatting, docs, focused types, action pins, and secrets.
2. `Unit and contract tests` provides the fast behavior and OpenAPI contract gate.
3. `PostgreSQL integration and migrations` validates both schemas and database-backed behavior.
4. `Deployable image smoke` builds all three Stage 0 images, runs them as non-root, and checks
   readiness without publishing them.

Branch protection should require these four checks. CI does not authenticate to AWS or publish
registry artifacts.

## Manual Assurance

[`assurance.yml`](../../.github/workflows/assurance.yml) is explicit `workflow_dispatch` evidence.
It runs dependency audit, CodeQL, advisory Trivy scans, the authenticated k6 baseline, and the
offline agent evaluation. These exercises are intentionally manual while their results and failure
modes are being learned; they are not routine merge gates.

## Manual Stage 0 Deployment

[`cd-dev.yml`](../../.github/workflows/cd-dev.yml) accepts only a selected `develop` or `main` ref.
It verifies that the exact commit passed all four CI jobs, requires the protected `aws-dev`
environment, authenticates with GitHub OIDC, builds and publishes `tree-<full-tree-SHA>` images,
resolves their ECR digests, and deploys the immutable references to EC2 through Systems Manager.
The workflow remains safely skipped unless `AWS_CD_ENABLED` is exactly `true` and all AWS variables
are configured.

Tag-based release promotion is suspended until a live Stage 0 deploy, rollback, and teardown have
been completed and recorded. No `latest` image is published.

## Evidence Boundary and Evolution

Workflow configuration and local validation are **Decision** evidence. A deployment claim requires
a completed, approved run with image identity, migrations, readiness, smoke, rollback, and teardown
evidence. Local Compose remains canonical. Fargate or Kubernetes becomes relevant only after the VM
path is understood and a measured availability, scaling, or ownership trigger justifies the next
operational layer.

Use the [OIDC setup](github-secrets-setup.md) for identity and variable requirements and the
[deployment contract](../07-deployment/app-repo-contract.md) for service interfaces.
