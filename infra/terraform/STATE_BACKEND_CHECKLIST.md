# Terraform State Backend Checklist (AWS S3)

This checklist maps AWS S3 backend best practices to this repository.

## Implemented

- Remote backend uses partial config files per context.
- Local sandbox backend is isolated in `backend.hcl`.
- AWS backend template exists in `environments/dev/backend.aws.hcl.example`.
- S3 native locking is enabled through `use_lockfile = true` in backend examples.
- State key naming is environment/component scoped (`dev/platform/terraform.tfstate`).
- Lock timeout is used in team-facing AWS plan/apply recipes (`-lock-timeout=30m`).
- `.tfvars` overlays split shared config from context-specific values.

## Must Implement Next (dev env bootstrap)

S3 state bucket must be created manually before first `TF_ENV=dev just tf init`.
No DynamoDB table needed — all backends use `use_lockfile = true` (Terraform ≥ 1.9
S3-native locking via a `.tflock` object in S3).

See bootstrap commands in Cloud Security Checklist Step 1.

Required before `TF_ENV=dev just tf init`:

- S3 state bucket created with versioning, AES-256 encryption, public-access block.
- `infra/terraform/environments/dev/backend.aws.hcl` populated (copy from `.example`).
- `infra/terraform/environments/dev/terraform.aws.tfvars` populated (copy from `.example`).
- GitHub repo variable `TERRAFORM_STATE_BUCKET_DEV` set to the bucket name.

## CI/CD Practices (dev → develop branch)

- OIDC role `data-zoo-github-actions` is Terraform-managed (`modules/iam/main.tf`).
  It is created on the **first local `TF_ENV=dev just tf apply`** with admin creds.
- Trust policy restricts to `repo:<owner>/api-observatory:ref:refs/heads/develop`
  and `ref:refs/heads/main` only — no wildcard sub.
- ECS deploy IAM policy in `modules/iam/main.tf` is currently commented out.
  Uncomment `ecs_deploy` policy block before first `just deploy-ecs`, then re-apply.
- `cd-dev.yml` triggers on `develop` branch CI success; requires `dev` environment approval.
- `terraform apply` is always from a saved plan (`-out=tfplan`); never auto-plans in CI.
- Use unique backend key per environment; never reuse keys across envs.
- `terraform force-unlock` emergency workflow: not yet created (prod hardening item).

## Prod Hardening (deferred — not needed for dev)

- S3 bucket policy: deny non-TLS access.
- S3 access logging to separate audit bucket.
- S3 lifecycle policy for noncurrent version expiry.
- KMS CMK for state encryption (replace SSE-S3).
- `cd-prod.yml` OIDC block (currently TODO/commented out).
- Separate `github-actions-prod` role with narrower permissions.
- `terraform force-unlock` `workflow_dispatch` emergency workflow.

## Safe Key Convention

Use:

- `{environment}/{component}/terraform.tfstate`

Examples:

- `dev/platform/terraform.tfstate`
- `stage/platform/terraform.tfstate`
- `prod/network/terraform.tfstate`

## Migration Safety Notes

Before backend migration:

1. Back up local state file.
2. Run `terraform init -migrate-state` with backend config.
3. Verify with `terraform state list`.

## Team Day-2 Commands

- Local sandbox plan/apply:
  - `TF_ENV=sandbox just tf plan`
  - `TF_ENV=sandbox just tf apply`
- Real AWS dev plan/apply:
  - `TF_ENV=dev just tf plan`
  - `TF_ENV=dev just tf apply`
