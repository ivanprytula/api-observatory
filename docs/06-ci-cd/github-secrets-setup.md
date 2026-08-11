# GitHub Actions AWS OIDC Setup

The application repository uses two separate short-lived GitHub OIDC identities. No IAM user access
key or secret key belongs in GitHub. Terraform in the infrastructure repository creates the roles;
this page records the app-side GitHub configuration they consume.

## AWS Identities

The image-publisher role is restricted to
`repo:ivanprytula/api-observatory:environment:aws-image-publish` and can push/inspect only the
three ECR repositories. The application deployment role is restricted to
`repo:ivanprytula/api-observatory:environment:aws-dev` and can inspect those ECR images and send or
inspect SSM commands for the selected EC2 host. The EC2 instance role separately pulls images and
reads Parameter Store runtime values. Do not attach broad account permissions to either GitHub role.

## GitHub Environments and Variables

Create `aws-image-publish` and `aws-dev`, each restricted to `main`. The reviewed `aws-dev` lock PR
merge is the normal deployment approval, so routine environment-review prompts add a duplicate
approval step. Keep branch protection on `main` with required PRs and the core CI checks
(`CI / Quality`, `CI / Unit and contract tests`).

Set variables, not secrets, as follows:

| Environment | Variable | Meaning |
| --- | --- | --- |
| `aws-image-publish` | `AWS_IMAGE_PUBLISH_ENABLED` | Explicit image-publication gate; leave false or unset initially |
| `aws-image-publish` | `AWS_ECR_PUBLISH_ROLE_ARN` | Dedicated ECR publisher role ARN |
| `aws-image-publish` | `AWS_REGION` | AWS region hosting the MVP platform |
| `aws-image-publish` | `AWS_ECR_REGISTRY` | ECR registry hostname for immutable references |
| `aws-dev` | `AWS_CD_ENABLED` | Explicit deployment gate; leave false or unset initially |
| `aws-dev` | `AWS_APP_DEPLOY_ROLE_ARN` | Application workload-deployer role ARN |
| `aws-dev` | `AWS_REGION` | AWS region hosting `aws-dev` |
| `aws-dev` | `AWS_ECR_REGISTRY` | ECR registry hostname for digest verification |
| `aws-dev` | `AWS_EC2_INSTANCE_ID_DEV` | EC2 host receiving SSM commands |

Store `APP_PROMOTION_TOKEN` only in `aws-image-publish`. It is a fine-grained PAT restricted to this
application repository with Contents and Pull requests write access. It maintains one fixed
promotion PR; set an expiry, rotate it, and never place its value in a command, variable, or
documentation.

Manual workflow dispatch is a recovery/replay mechanism for a CI-green app `main` commit and its
already committed lock; it is not a way to supply a new image or deployment target.

## Verification Boundary

A successful role assumption or SSM command proves credential wiring and command delivery only.
Deployment evidence additionally requires the selected immutable image identities, migrations,
readiness, smoke proof, rollback path, and retained redacted evidence.
