# GitHub Variables & OIDC Setup — AWS

AWS is the primary deployment path. GitHub Actions uses OIDC and does not store
long-lived AWS access keys or ECR passwords. This is configuration guidance only;
it does not provision an AWS account or enable the workflows by itself.

## Repository Variables

Set these under **Settings → Secrets and variables → Actions → Variables** after
the infra repository has created the matching AWS resources and IAM roles.

| Variable | Used by | Example shape |
| --- | --- | --- |
| `AWS_ECR_REGISTRY` | CI, release, CD | `123456789012.dkr.ecr.eu-central-1.amazonaws.com` |
| `AWS_REGION` | CI, release, CD | `eu-central-1` |
| `AWS_ROLE_ARN_CI` | Candidate-image publishing | `arn:aws:iam::123456789012:role/api-observatory-ci` |
| `AWS_ROLE_ARN_DEV` | Approved EC2 deployment | `arn:aws:iam::123456789012:role/api-observatory-dev-deploy` |
| `AWS_ROLE_ARN_RELEASE` | Semver-tag promotion | `arn:aws:iam::123456789012:role/api-observatory-release` |
| `AWS_EC2_INSTANCE_ID_DEV` | Stage-0 CD target | `i-0123456789abcdef0` |

Create an `aws-dev` GitHub environment with a required reviewer. Until all CI
variables and the environment are present, candidate publishing and deployment jobs
are skipped safely.

## OIDC Requirements

The AWS trust policy must permit GitHub's OIDC issuer,
`https://token.actions.githubusercontent.com`, with audience `sts.amazonaws.com`.
Restrict each role to the relevant repository, branch, or GitHub environment.

- CI role: write only the three candidate ECR repositories.
- Release role: read candidate tags and write semver tags in those repositories.
- Dev role: invoke the approved EC2 Systems Manager command only.
- EC2 instance role: pull its three ECR images and accept Systems Manager commands.

No AWS access keys, ECR passwords, SSH private keys, or service-principal JSON
belong in GitHub secrets for this AWS path.

## Azure Reference

Azure/ACR credentials remain outside the primary path and are retained only in the
infra repository's secondary/reference material.
