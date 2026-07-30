# GitHub Actions AWS OIDC Setup

The application image-publication workflow uses short-lived AWS credentials through GitHub OIDC. It does
not require an IAM user access key or secret key in GitHub. The executable contract is
[`publish-images.yml`](../../.github/workflows/publish-images.yml); this page records the AWS and GitHub settings it
expects.

## AWS Identity Configuration

Create or reuse the GitHub OIDC provider for
`https://token.actions.githubusercontent.com` with audience `sts.amazonaws.com`. Create a
dedicated image-publisher role, such as `github-actions-api-observatory-image-publish`, with a trust
policy restricted to this repository and the `aws-image-publish` environment:

- audience: `sts.amazonaws.com`;
- subject: `repo:ivanprytula/api-observatory:environment:aws-image-publish`;
- action: `sts:AssumeRoleWithWebIdentity`.

Attach only the permissions required by the workflow: push and inspect the three application ECR
repositories. The infrastructure repository owns the separate SSM deployment role, while the EC2
instance role separately needs permission to pull images. Do not attach `PowerUserAccess` to the
GitHub publisher role.

The application repository owns the role ARN and variable names; infrastructure owns the IAM
provider, role policy, ECR, EC2, and runtime delivery. See the
[infra deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md)
for the platform boundary.

## GitHub Actions Variables

Set these as repository or `aws-image-publish` environment variables, not secrets:

| Variable | Meaning |
| --- | --- |
| `AWS_IMAGE_PUBLISH_ENABLED` | Explicit image-publication gate; keep `false` or unset until AWS is ready |
| `AWS_ECR_PUBLISH_ROLE_ARN` | ARN of the dedicated ECR-publisher OIDC role |
| `AWS_REGION` | AWS region containing the Stage 0 resources |
| `AWS_ECR_REGISTRY` | ECR registry hostname used in immutable image references |

Create the `aws-image-publish` environment and configure a required reviewer before enabling publication.
The workflow skips image publication unless `AWS_IMAGE_PUBLISH_ENABLED` is exactly `true`; an absent or
`false` value is the safe default while AWS is being prepared. The workflow already requests
`id-token: write` and uses `aws-actions/configure-aws-credentials` with `role-to-assume`.

Trigger the workflow manually from a CI-green `develop` or `main` ref. Feature-branch publication
is rejected. Routine CI never receives AWS credentials and never publishes images.

## Local CLI Credentials

An IAM user profile such as `dev-cli` may be used for local AWS CLI administration or inspection.
Keep its access key and secret key in the local credential store or environment, never in GitHub,
workflow files, repository variables, or committed documentation. Prefer short-lived federation
for human access when the account supports it.

## Verification Boundary

A successful role assumption and SSM command prove credential wiring and command delivery only.
Deployment evidence additionally requires the selected immutable image tag, health/readiness
results, migration result, smoke proof, rollback path, and retained redacted evidence.
