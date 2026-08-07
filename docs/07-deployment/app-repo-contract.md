# Application AWS MVP Delivery Contract

The application repository owns service behavior, Dockerfiles, images, migrations, health/readiness
endpoints, the AWS MVP Compose workload, Prometheus configuration, the reviewed `aws-dev` image
lock, and application deployment/rollback. The infrastructure repository owns the platform that
supplies those capabilities: Terraform state, networking, ECR, one private EC2 host with encrypted
EBS, IAM, Parameter Store, Docker/SSM bootstrap, retained S3 backups, host replacement, and restore
tooling. PostgreSQL runs in application-owned Compose containers on the EC2 volume; no managed
database is part of this MVP.

[`release/services.json`](../../release/services.json) remains the portable release manifest. It
defines the three deployable HTTP images and the immutable `tree-<full-tree-SHA>` tag convention.
`SERVICE_VERSION=tree-<SHA>` is release provenance, not the semantic application version.
`APP_VERSION` remains an independently managed API/OpenAPI version, while
`libs/contracts/VERSION` records shared-contract compatibility.

## Reviewed Desired State

`environments/aws-dev/images.lock.json` is application-owned desired state. The schema binds the
source commit and tree to exact ECR digests and records enabled optional profiles. The publisher
validates release metadata, resets its fixed `automation/promote-aws-dev` branch from current app
`main`, preserves already reviewed profiles, and replaces only image identities. Duplicate releases
produce no lock change; a newer source release updates the same pull request.

The routine delivery path is:

`app PR → CI → main → immutable images → aws-dev lock PR → review/merge → SSM → EC2 Compose`

Merging the green lock PR is the human release decision. A source merge can publish images but
cannot deploy them before that lock merge. Reverting a reviewed lock through a PR follows the same
deployment path and is the normal application-image rollback. Database migrations are forward-only;
rollback requires compatible migrations rather than an automated downgrade.

Optional profiles change in a separate application PR. Automated image promotion never changes
their selection, so a release can update only the services that received new immutable digests while
unchanged services retain their previous image identities.

## MVP Platform Contract 1

Before `AWS_CD_ENABLED` can be enabled, the infrastructure repository must bootstrap contract
version `1`. The host supplies Docker Compose, SSM command access,
`/opt/api-observatory-mvp`, its protected `.runtime` directory, and
`api-observatory-mvp-render-env <group>...`. The app computes the required groups from the reviewed
profiles, renders runtime values through that command, transfers its Compose/Prometheus/rollout
assets with SSM, then runs migrations, readiness checks, smoke checks, and best-effort previous-image
rollback.

`mvp` describes the current product/deployment scope. `aws-dev` is an environment name; future
`aws-qa-stage` and `aws-prod` must promote the same tested digests without rebuilding them.

## Evidence Boundary

Local Compose remains application-owned and canonical for development. The AWS MVP path is
configuration and contract evidence until a separately approved live run retains redacted image,
migration, readiness, smoke, rollback, backup/restore, and teardown evidence. A lock diff,
published image, static check, or Terraform plan alone is not a deployment claim.
