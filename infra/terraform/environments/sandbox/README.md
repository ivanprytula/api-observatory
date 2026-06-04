# Terraform Sandbox Environment

Local emulator target for Terraform workflows. Works with Floci, LocalStack, or any
S3-compatible AWS emulator — controlled by `emulator_endpoint` in `terraform.tfvars`.

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
just sandbox-up          # start emulator
just tf-sandbox-init     # init backend (creates S3 bucket if absent)
just tf-sandbox-plan     # plan
just tf-sandbox-apply    # apply saved plan
just tf-sandbox-destroy  # destroy all sandbox resources
```

## Changing emulator

Set `emulator_endpoint` in `terraform.tfvars`:

```hcl
emulator_endpoint = "http://localhost:4566"   # Floci / LocalStack default
```

Update the matching `endpoints.s3` in `backend.hcl` to the same value.

## Separation from dev/

`environments/dev/` targets real AWS only — no emulator overrides, no sandbox credentials.
`environments/sandbox/` targets local emulators only — no real AWS credentials, no real backend bucket.
