# Application CI/CD

The application repository owns CI and AWS MVP workload delivery. Workflow YAML under
[`.github/workflows/`](../../.github/workflows/) is the executable source of truth; the sibling
infrastructure repository provides the secure platform contract rather than a second deployment
control plane.

## Branch and Review Flow

Short-lived task branches merge into `main` through a pull request. The core CI checks
(`CI / Quality`, `CI / Unit and contract tests`) protect `main`. Additional job graphs
(integration, capability, image-smoke) run conditionally; publish and deploy enforce their own
gating via workflow `if:` conditions. Protect the app `main` branch with required PRs and the core
checks before enabling AWS gates.

Application CI has no AWS credentials. Only the post-gate image publisher receives the separate
`aws-image-publish` OIDC identity. The deployment workflow receives the different `aws-dev` OIDC
identity only after reviewed desired state reaches `main`.

## Image Publication and Promotion

[`publish-images.yml`](../../.github/workflows/publish-images.yml) runs after a deployable `main`
change passes CI. It verifies the exact current commit, builds immutable `tree-<full-tree-SHA>` ECR
images, and emits the source commit, tree, and resolved digests. It remains skipped unless
`AWS_IMAGE_PUBLISH_ENABLED` is exactly `true`.

The publisher then validates that release metadata and maintains one same-repository
`automation/promote-aws-dev` PR. It preserves `enabled_profiles` from app `main` and changes only
`environments/aws-dev/images.lock.json`. The `APP_PROMOTION_TOKEN` is limited to this repository's
Contents and Pull requests write access, allowing the bot PR to use normal branch protection without
an additional GitHub Actions approval path.

## Deployment

[`deploy-aws-mvp.yml`](../../.github/workflows/deploy-aws-mvp.yml) has no image or target inputs.
After a green lock merge, app CI invokes it exactly once for the committed `aws-dev` lock. It checks
the lock source commit/tree, resolves that exact source checkout, verifies ECR digests, requires MVP
platform contract `1`, and sends the application workload to the pre-bootstrapped host through SSM.
It does not write Git and it never consumes event-supplied image digests. A manual dispatch replays
only the desired state already committed on app `main`.

Keep `AWS_IMAGE_PUBLISH_ENABLED` and `AWS_CD_ENABLED` separate and disabled until the one-time
platform/bootstrap and GitHub environment setup is complete. Reverting the lock in a reviewed PR
uses the same deployment path for an application-image rollback.

## Evidence Boundary and Evolution

Workflow configuration and local validation are **Decision** evidence. A deployment claim requires
a completed, approved run with image identity, migrations, readiness, smoke, rollback, and teardown
evidence. Local Compose remains canonical. The AWS learning sequence is an exercised EC2 deployment,
then ECS on Fargate, then EKS. Moving the product runtime beyond EC2 still requires a measured
availability, scaling, ownership, or delivery-friction trigger.

## Local CI with `act`

[`act`](https://nektosact.com/) runs GitHub Actions workflows locally in Docker containers,
catching workflow syntax, composite-action, and migration-validation errors before pushing.

### Installation

```bash
# macOS/Linux
brew install act
```

### Just Recipes

```bash
# Prime the act image cache (run once or after dependency changes)
just ci-prime

# Fast lane: unit, MCP, and contract tests (no Postgres service)
just ci-unit

# Run unit tests only
just ci

# Before push: unit tests + pre-commit hooks
just pre-push
```

> **Note:** `act` does not support GitHub Actions service containers, so the `integration` and `capability` jobs (which rely on Postgres service containers) must run on real GitHub Actions or via local `docker compose`. The `ci-unit` recipe catches workflow syntax, composite-action, and migration-path errors locally.
