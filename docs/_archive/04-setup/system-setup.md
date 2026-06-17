# System Setup

Track: A - Product and Onboarding

This page is the onboarding preflight for host tooling.

Canonical package and tooling matrix:

- System Requirements

Use this file for the minimum sequence before first bootstrap.

## Goal

Ensure your machine has the required runtime and CLI tools so project automation can run without manual troubleshooting.

## Preflight Sequence

1. Install required packages and CLIs from the System Requirements guide.
2. Run `just doctor` to verify tools and local folder conventions.
3. Continue to the First-Time Setup guide.

## Minimum Verification

```bash
just doctor
uv --version
docker --version
docker compose version
```

If `just doctor` reports missing tools, install them from the canonical matrix and re-run.

## Docker Notes

If Docker commands fail due to permissions, follow the Linux docker-group steps from the System Requirements guide.

## Local Artifact Convention

Use `.local-dev/` for temporary local outputs and troubleshooting artifacts.
The directory is gitignored and safe to clear/recreate.

## Next Document

Proceed to the First-Time Setup guide for end-to-end local bootstrap.
