# Terraform Sandbox Environment

Local emulator target for Terraform workflows. Uses Floci (rootfull Docker) with
real containers: ECR registry, RDS Postgres, ElastiCache Redis, ECS Fargate tasks.

## Prerequisites

- Docker running rootfull (not rootless) — sibling container creation required
- Floci running: `docker compose --profile aws up -d floci` or `just floci-up`
- ECR registry sidecar (pre-create once):

  ```bash
  docker run -d --name floci-ecr-registry \
    --network api-observatory_api-obs -p 5100:5000 registry:2
  ```

## File map

| File | Purpose |
|------|---------|
| `terraform.tfvars.example` | Copy to `terraform.tfvars` (gitignored) |
| `backend.hcl.example` | Copy to `backend.hcl` (gitignored) |

## First-time setup

```bash
cp infra/terraform/environments/sandbox/backend.hcl.example \
   infra/terraform/environments/sandbox/backend.hcl
cp infra/terraform/environments/sandbox/terraform.tfvars.example \
   infra/terraform/environments/sandbox/terraform.tfvars
```

## Commands

```bash
just floci-up                         # start Floci emulator (real containers)
just tf init                          # init Terraform backend in sandbox
TF_ENV=sandbox just tf plan           # plan IaC against Floci
TF_ENV=sandbox just tf apply          # apply VPC/ALB/ECS/RDS/ElastiCache/ECR
just floci-deploy                     # build + push images to Floci ECR, deploy to ECS
TF_ENV=sandbox just tf destroy        # destroy all sandbox resources
```

## What Floci creates

Floci runs real containers for data-plane services:

- **ECR**: OCI registry on `127.0.0.1:5100-5199` — real `docker push`/`pull`
- **RDS**: Postgres on proxy ports `7001-7099`
- **ElastiCache**: Redis on proxy ports `6379-6399`
- **ECS**: Real Fargate tasks via mounted Docker socket

Port conflicts are avoided: Floci uses private proxy port ranges, not host bindings.

## Changing emulator

Set `emulator_endpoint` in `terraform.tfvars`:

```hcl
emulator_endpoint = "http://127.0.0.1:4566"
```

Update the matching `endpoints.s3` in `backend.hcl` to the same value.

## Separation from dev/

`environments/dev/` targets real AWS only — no emulator overrides, no sandbox credentials.
`environments/sandbox/` targets local Floci only — no real AWS credentials, no real backend bucket.
