# Application Image Contract

The application repository owns developer-local Compose, service behavior, Dockerfiles, image
build contexts, ports, health/readiness endpoints, migrations, and image smoke tests. It does not
own an AWS runtime topology, deployment host, runtime secrets, or rollout mechanism.

[`release/services.json`](../../release/services.json) is the portable release manifest. It defines
the three deployable HTTP images and the immutable `tree-<full-tree-SHA>` tag convention. The
manual image-publication workflow verifies the existing application CI checks before pushing those
images to ECR; it does not deploy them.

The infrastructure repository owns the selected environment image digests, Compose profile shape,
runtime values, migration ordering, deployment/rollback, monitoring, backup, and cloud IAM. See
its [deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md).

Local Compose files remain application-owned so a developer can run and test the complete stack
without cloning infrastructure code.
