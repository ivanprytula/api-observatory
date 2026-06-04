#!/usr/bin/env bash
# AWS environment for local sandbox (Floci / LocalStack / any emulator).
# Credentials come from the [sandbox] named profile in ~/.aws/credentials.
# See docs/setup/sandbox-aws-profile.md for one-time setup.
# Keep AWS_ENDPOINT_URL in sync with environments/sandbox/terraform.tfvars emulator_endpoint.
export AWS_PROFILE=sandbox
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=eu-central-1
# Unset any stale credential env vars — a named profile and access key env vars conflict.
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
