# Terraform Dev Environment Files

This folder has one base config plus one overlay per execution context.

## File map

- `terraform.tfvars.example` -> copy to `terraform.tfvars`
  - Shared dev defaults used by both LocalStack and real AWS.
- `terraform.floci.tfvars.example` -> copy to `terraform.floci.tfvars`
  - LocalStack/Floci-only overrides.
- `terraform.aws.tfvars.example` -> copy to `terraform.aws.tfvars`
  - Real AWS-only overrides.
- `backend.local.hcl.example` -> copy to `backend.local.hcl`
  - Backend config for LocalStack S3 state + lockfile locking.
- `backend.aws.hcl.example` -> copy to `backend.aws.hcl`
  - Backend config for real AWS S3 state + lockfile locking.

## Which files are used by which commands

### LocalStack/Floci path

- `just tf-plan-local`
  - reads: `backend.local.hcl`
  - reads: `terraform.tfvars`
  - reads: `terraform.floci.tfvars`

### Real AWS path

- `just tf-plan-dev`
  - reads: `backend.aws.hcl`
  - reads: `terraform.tfvars`
  - reads: `terraform.aws.tfvars`

## First-time setup

1. Copy shared base:

```bash
cp infra/terraform/environments/dev/terraform.tfvars.example \
   infra/terraform/environments/dev/terraform.tfvars
```

1. Choose one path:

LocalStack:

```bash
cp infra/terraform/environments/dev/backend.local.hcl.example \
   infra/terraform/environments/dev/backend.local.hcl
cp infra/terraform/environments/dev/terraform.floci.tfvars.example \
   infra/terraform/environments/dev/terraform.floci.tfvars
```

Real AWS:

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example \
   infra/terraform/environments/dev/backend.aws.hcl
cp infra/terraform/environments/dev/terraform.aws.tfvars.example \
   infra/terraform/environments/dev/terraform.aws.tfvars
```

1. Run the matching command:

- LocalStack: `just tf-plan-local`
- AWS: `just tf-plan-dev`

## Rule of thumb

Only one backend file is active per context:

- local context: `backend.local.hcl`
- aws context: `backend.aws.hcl`

Do not create or use a generic `backend.hcl` file in this folder.
