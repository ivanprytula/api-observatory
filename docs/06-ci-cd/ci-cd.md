# Application CI/CD

The delivery path is intentionally small enough for one maintainer to run and explain end to end.
Workflow YAML under [`.github/workflows/`](../../.github/workflows/) is the executable source of
truth.

## Branch and Review Flow

Short-lived task branches merge into `main` through a pull request. The executable workflow owns its
internal quality, test, migration, contract, and image-smoke jobs. The stable `CI / Merge gate` fails
unless every internal requirement succeeds. Repository settings intentionally do not enforce checks
or approvals yet, so waiting for that gate is a maintainer policy rather than a GitHub restriction.
The stable gate lets the internal job graph evolve without updating release documentation.

CI does not authenticate to AWS or publish registry artifacts. Follow the exact branch, commit,
push, and pull-request lifecycle in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Manual Assurance

[`assurance.yml`](../../.github/workflows/assurance.yml) is explicit `workflow_dispatch` evidence.
It runs dependency audit, CodeQL, advisory Trivy scans, the authenticated k6 baseline, and the
offline agent evaluation. These exercises are intentionally manual while their results and failure
modes are being learned; they are not routine merge gates.

## Manual Image Publication

[`publish-images.yml`](../../.github/workflows/publish-images.yml) accepts only a selected `main`
ref. It verifies that the exact commit passed the merge gate, requires the protected
`aws-image-publish` environment, authenticates with GitHub OIDC, and publishes immutable
`tree-<full-tree-SHA>` ECR images with their resolved digests. It uploads machine-readable release
metadata containing the source commit, source tree, and three image digests. It does not deploy to EC2.
Publication remains safely skipped unless `AWS_IMAGE_PUBLISH_ENABLED` is exactly `true` and all AWS
variables are configured.

Promotion is an infra-repository PR that changes the environment image lock; no `latest` image is
published.

## Cross-Repository Contract Change

When a change affects published images, the runtime service contract, or deployment topology:

1. Merge the application PR into `main` and wait for the internal `CI / Merge gate` to succeed.
2. Publish immutable `tree-<SHA>` images with `publish-images.yml`.
3. Download the resulting `release-metadata-<commit-SHA>` artifact.
4. In `api-observatory-infra`, create a separate task branch from `main`, run
   `just promote-images <artifact-path>`, review the generated `images.lock.json`, and open an
   infra PR.
5. After infra CI passes, manually dispatch the approved Stage 0 deployment workflow in the infra
   repo.

Do not describe a lock-file change, Terraform plan, or published image as a completed deployment.

## Evidence Boundary and Evolution

Workflow configuration and local validation are **Decision** evidence. A deployment claim requires
a completed, approved run with image identity, migrations, readiness, smoke, rollback, and teardown
evidence. Local Compose remains canonical. Fargate or Kubernetes becomes relevant only after the VM
path is understood and a measured availability, scaling, or ownership trigger justifies the next
operational layer.

Use the [OIDC setup](github-secrets-setup.md) for identity and variable requirements and the
[deployment contract](../07-deployment/app-repo-contract.md) for service interfaces.
