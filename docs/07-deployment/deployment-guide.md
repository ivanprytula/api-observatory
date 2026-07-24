# Deployment Guide — AWS Stage 0

## Primary Target

AWS is the primary portfolio deployment direction. Stage 0 uses Docker Compose on
EC2, RDS PostgreSQL, and ECR images. This repository is not deployed yet: the
workflow templates remain inactive until the AWS variables, OIDC roles, and the
approved `aws-dev` environment exist.

Azure and ACR material remains secondary/reference documentation. ECS/Fargate is a
Stage 2 option, not part of this deployment slice.

## Deployable Services

The Stage-0 contract defines three HTTP services:

| Service | Image repository | Port | Health | Readiness |
| --- | --- | ---: | --- | --- |
| ingestor | `api-observatory/ingestor` | 8000 | `/health` | `/readyz` |
| inference | `api-observatory/inference` | 8001 | `/health` | `/readyz` |
| dashboard | `api-observatory/dashboard` | 8501 | `/_stcore/health` | `/_stcore/health` |

Images use `${AWS_ECR_REGISTRY}/api-observatory/<service>:tree-<SHA>`. MCP is a
locally spawned stdio integration and is intentionally not deployed to EC2.

## Prerequisites for a Later AWS Deployment

The infra repository owns real-cloud provisioning. Before enabling CI/CD, create
the ECR repositories and the existing `aws-dev` EC2/RDS environment there, then
configure these GitHub repository variables:

- `AWS_ECR_REGISTRY`
- `AWS_REGION`
- `AWS_ROLE_ARN_CI`
- `AWS_ROLE_ARN_DEV`
- `AWS_ROLE_ARN_RELEASE`
- `AWS_EC2_INSTANCE_ID_DEV`

The AWS roles use GitHub Actions OIDC; do not create long-lived AWS access-key
secrets. The EC2 instance needs an instance role that can pull the three ECR images
and Systems Manager access for the controlled deployment command.

## Workflow Behavior

- CI publishes and scans immutable images only when `AWS_ECR_REGISTRY`,
  `AWS_ROLE_ARN_CI`, and `AWS_REGION` are configured.
- The AWS CD workflow also requires explicit `aws-dev` environment approval and
  `AWS_EC2_INSTANCE_ID_DEV`; otherwise every deployment job is skipped.
- Release promotion copies all three `tree-<SHA>` candidates to a semver tag. It
  never publishes `latest` to ECR.

## Local Image Verification

```bash
docker build -t api-observatory/ingestor:verify .
docker build -t api-observatory/inference:verify -f services/inference/Dockerfile .
docker build -t api-observatory/dashboard:verify -f services/dashboard/Dockerfile .
```

After testing, remove only the explicitly created `:verify` images if they are no
longer needed.

## Secondary Azure Reference

The sibling infra repository retains Azure Terraform and VM guidance for comparison
and learning. Do not treat its ACR or Azure-credential instructions as the primary
deployment path.
