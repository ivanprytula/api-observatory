# Application Image Contract

The application repository owns developer-local Compose, service behavior, Dockerfiles, image
build contexts, ports, health/readiness endpoints, migrations, and image smoke tests. It does not
own an AWS runtime topology, deployment host, runtime secrets, or rollout mechanism.

[`release/services.json`](../../release/services.json) is the portable release manifest. It defines
the three deployable HTTP images and the immutable `tree-<full-tree-SHA>` tag convention. The
reusable image-publication workflow runs after a deployable `main` change passes application CI and
verifies the exact commit again before pushing those images to ECR. Its release metadata binds the
Git commit to the tree identity and three resolved digests so infrastructure can validate the exact
source contract; it does not deploy them. Manual dispatch remains an initial-release and retry
fallback for a CI-green `main` commit.

The infrastructure repository owns the selected environment image digests, Compose profile shape,
runtime values, migration ordering, deployment/rollback, monitoring, backup, and cloud IAM. It
uses a simple promotion model of `dev`, `stage`, and `prod-like` lanes, with `aws-dev` as the only
active concrete target today. See its [deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md)
and [promotion model](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/promotion-model.md).
The publisher can update only a bot-owned infra lock PR through the infra-owned promotion script;
merging that reviewed lock is the approval for infra CI to deploy it. Automated image promotion
preserves optional profiles already selected on infra `main`.

`SERVICE_VERSION=tree-<SHA>` is coordinated release provenance, not the semantic application
version. `APP_VERSION` remains an independently managed API/OpenAPI version, while
`libs/contracts/VERSION` records shared-contract compatibility.

Local Compose files remain application-owned so a developer can run and test the complete stack
without cloning infrastructure code.
