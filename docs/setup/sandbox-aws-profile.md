# Sandbox AWS Profile Setup

One-time workstation setup required before running `just tf-plan-local`, `just sandbox-up`, or
any recipe that sources `scripts/aws-env.sh`.

## Why a named profile?

The Terraform AWS provider rejects a mix of a named `profile` and access-key environment
variables (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`). Using a dedicated `[sandbox]` profile
keeps emulator credentials fully isolated from real AWS profiles and avoids that conflict.

The profile name `sandbox` is emulator-agnostic — it works with Floci, LocalStack, or any
AWS-compatible local emulator that listens on `http://localhost:4566`.

## One-time setup

Add the following to `~/.aws/credentials`:

```ini
[sandbox]
aws_access_key_id     = test
aws_secret_access_key = test
```

Add the following to `~/.aws/config`:

```ini
[profile sandbox]
region = eu-central-1
```

## How it is used

`scripts/aws-env.sh` exports:

| Variable            | Value                      | Purpose                                      |
|---------------------|----------------------------|----------------------------------------------|
| `AWS_PROFILE`       | `sandbox`                  | Selects the profile for CLI and Terraform     |
| `AWS_ENDPOINT_URL`  | `http://localhost:4566`    | Redirects all AWS API calls to the emulator  |
| `AWS_DEFAULT_REGION`| `eu-central-1`             | Default region for CLI commands              |

Any stale `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars are unset by the script to
prevent the named-profile conflict.

`infra/terraform/environments/dev/terraform.tfvars` should set `aws_profile = "sandbox"` for local runs, overriding the `aws_profile = "default"` fallback.

## Verify the setup

```bash
source scripts/aws-env.sh
aws sts get-caller-identity   # returns mock JSON from the emulator
```

Expected output (emulator responds with dummy account):

```json
{
    "UserId": "AKIAIOSFODNN7EXAMPLE",
    "Account": "000000000000",
    "Arn": "arn:aws:iam::000000000000:root"
}
```

## Switching emulators

To switch emulators (e.g. from Floci to LocalStack):

1. Update the container image / service name in `docker-compose.yml`.
2. Verify the health endpoint and update `sandbox-up` in the Justfile if it differs.
3. No credential or profile changes are needed — `[sandbox]` credentials are the same for all
   AWS-compatible emulators.

## Related files

- [`scripts/aws-env.sh`](../../scripts/aws-env.sh) — exports sandbox env vars
- [`infra/terraform/environments/dev/terraform.tfvars`](../../infra/terraform/environments/dev/terraform.tfvars) — Terraform variable overrides for local runs
- [`infra/terraform/environments/dev/main.tf`](../../infra/terraform/environments/dev/main.tf) — AWS provider definition
- [`Justfile`](../../Justfile) — `sandbox-up`, `tf-plan`, and related recipes
