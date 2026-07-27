# GitHub Actions AWS OIDC Setup

The application delivery workflow uses short-lived AWS credentials through GitHub OIDC. It does
not require an IAM user access key or secret key in GitHub. The executable contract is
[`cd-dev.yml`](../../.github/workflows/cd-dev.yml); this page records the AWS and GitHub settings it
expects.

## AWS Identity Configuration

Create or reuse the GitHub OIDC provider for
`https://token.actions.githubusercontent.com` with audience `sts.amazonaws.com`. Create a
dedicated deployment role, such as `github-actions-api-observatory-dev`, with a trust policy
restricted to this repository and the `aws-dev` environment:

- audience: `sts.amazonaws.com`;
- subject: `repo:ivanprytula/api-observatory:environment:aws-dev`;
- action: `sts:AssumeRoleWithWebIdentity`.

Attach only the permissions required by the workflow: SSM command delivery and command-result
inspection for the approved EC2 target. The EC2 instance role separately needs permission to pull
the three application images from ECR. Do not attach `PowerUserAccess` to the GitHub deployment
role.

The application repository owns the role ARN and variable names; infrastructure owns the IAM
provider, role policy, ECR, EC2, and runtime delivery. See the
[infra deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md)
for the platform boundary.

## GitHub Actions Variables

Set these as repository or `aws-dev` environment variables, not secrets:

| Variable | Meaning |
| --- | --- |
| `AWS_CD_ENABLED` | Explicit deployment gate; keep `false` or unset until AWS is ready |
| `AWS_ROLE_ARN_DEV` | ARN of the dedicated GitHub OIDC deployment role |
| `AWS_REGION` | AWS region containing the Stage 0 resources |
| `AWS_ECR_REGISTRY` | ECR registry hostname used in immutable image references |
| `AWS_EC2_INSTANCE_ID_DEV` | Approved EC2 deployment target |

Create the `aws-dev` environment and configure a required reviewer before enabling deployment.
The workflow skips its deployment jobs unless `AWS_CD_ENABLED` is exactly `true`; an absent or
`false` value is the safe default while AWS is being prepared.
The workflow already requests `id-token: write` and uses
`aws-actions/configure-aws-credentials` with `role-to-assume`.

## Local CLI Credentials

An IAM user profile such as `dev-cli` may be used for local AWS CLI administration or inspection.
Keep its access key and secret key in the local credential store or environment, never in GitHub,
workflow files, repository variables, or committed documentation. Prefer short-lived federation
for human access when the account supports it.

## Verification Boundary

A successful role assumption and SSM command prove credential wiring and command delivery only.
Deployment evidence additionally requires the selected immutable image tag, health/readiness
results, migration result, smoke proof, rollback path, and retained redacted evidence.
