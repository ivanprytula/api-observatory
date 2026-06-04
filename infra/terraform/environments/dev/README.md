# Terraform Dev Environment (AWS)

Real AWS deployment target. No emulator files live here.

> Local sandbox (Floci / LocalStack) → see [`../sandbox/`](../sandbox/README.md)

## File map

| File | Purpose |
|------|---------|
| `terraform.tfvars.example` | Copy to `terraform.tfvars` — shared AWS defaults |
| `terraform.aws.tfvars.example` | Copy to `terraform.aws.tfvars` — AWS-specific overrides |
| `backend.aws.hcl.example` | Copy to `backend.aws.hcl` (gitignored) — real S3 state config |

## First-time setup

```bash
cp infra/terraform/environments/dev/backend.aws.hcl.example \
   infra/terraform/environments/dev/backend.aws.hcl

cp infra/terraform/environments/dev/terraform.tfvars.example \
   infra/terraform/environments/dev/terraform.tfvars

cp infra/terraform/environments/dev/terraform.aws.tfvars.example \
   infra/terraform/environments/dev/terraform.aws.tfvars
```

## Commands

```bash
just tf-plan-dev    # init + validate + plan (saves tfplan.aws)
just tf-apply-dev   # apply saved plan
```

## Rule of thumb

Only `backend.aws.hcl` is valid here. Do not create `backend.local.hcl` or any
emulator-targeted files in this directory — those belong in `../sandbox/`.
