# Terraform State Backend Checklist (AWS S3)

This checklist maps AWS S3 backend best practices to this repository.

## Implemented

- Remote backend uses partial config files per context.
- Local sandbox backend is isolated in `backend.local.hcl`.
- AWS backend template exists in `environments/dev/backend.aws.hcl.example`.
- S3 native locking is enabled through `use_lockfile = true` in backend examples.
- State key naming is environment/component scoped (`dev/platform/terraform.tfstate`).
- Lock timeout is used in team-facing AWS plan/apply recipes (`-lock-timeout=30m`).
- `.tfvars` overlays split shared config from context-specific values.

## Must Implement Next

- Create dedicated backend bootstrap stack (or one-time bootstrap run) that provisions:
  - S3 state bucket
  - S3 versioning enabled
  - S3 default encryption enabled
  - S3 public access block enabled
- Add S3 bucket policy for least privilege and deny non-TLS access.
- Add optional KMS CMK for state encryption in shared/prod accounts.
- Enable S3 access logging (or CloudTrail data events) for state bucket audit trail.
- Add lifecycle policy for noncurrent object versions.

## CI/CD Practices

- Use OIDC role assumption for Terraform jobs.
- Use unique backend key per environment/component; never reuse keys across envs.
- Keep `terraform apply` gated by protected branch + environment approval.
- Add manual `terraform force-unlock` workflow (workflow_dispatch only).

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
  - `just tf-plan-local`
  - `just tf-apply-local`
- Real AWS dev plan/apply:
  - `just tf-plan-dev`
  - `just tf-apply-dev`
