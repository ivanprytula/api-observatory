# Canonical onboarding and delivery checklist

This document is the single source of truth for first-time setup, day-to-day task flow, PR readiness,
and the application release handoff. When a contributor workflow changes, update this document first
and then link to it from the README, contributing guide, and deployment docs rather than copying the
same instructions into multiple places.

## 0. Prerequisites

The supported developer workstation is Linux (Ubuntu) or macOS with Docker Engine/Desktop and
Compose v2, a running Docker daemon, the Python version selected by [`.python-version`](../../.python-version),
`uv`, `just`, Git, and `curl`. Run `just doctor` before creating `.env`; it checks only these core
tools and the Docker daemon/Compose path.

Terraform, Ansible, cloud CLIs, Kubernetes tools, and database client utilities are not application
onboarding requirements. Install them only for a task that owns that boundary, following the sibling
infrastructure repository's
README.

Never read or commit a local `.env`. Copy the public, non-secret
[`.env.example`](../../.env.example), then generate local credentials privately.

### Runtime and dependency maintenance

`.python-version` specifies the supported Python minor series (`3.14`), allowing `uv` to use the
latest compatible patch release without a repository edit. Dependabot opens weekly `uv` and GitHub
Actions update PRs; review the compatible group and each major upgrade while the change is small.

When a new Python minor is adopted, change `.python-version` in this repository and the sibling
infrastructure repository in the same maintenance slice, then run `uv lock --upgrade` and the
relevant CI suites. The `requires-python` lower bounds describe compatibility, so do not raise them
without deciding to drop an older supported runtime. App CI also requires every Python Docker base
image to match `.python-version`.

## 1. Canonical onboarding path

Use this path for first-time setup or when returning to the repository after a long gap:

1. Review the app [README](../../README.md).
2. Run `just doctor`.
3. Copy `.env.example` to `.env` and generate local secrets with `just generate-secrets`.
4. Start the default stack with `just dev-up`.
5. `dev-up` returns only after Compose reports the core services healthy; run `just db-migrate`.
6. Run the smallest proof that matches the task: `just test-unit` for isolated work or `just test-smoke` when the running stack is involved.

## 2. Canonical task workflow

Use this path for a normal change:

1. Create a short-lived branch from `main` using the conventions in [CONTRIBUTING](../../CONTRIBUTING.md).
2. Pick the smallest runtime shape that exercises the change.
3. Run the minimum focused proof before opening a PR.
4. Review the diff for docs, migrations, and contract changes.
5. Open a PR after the relevant checks are green.

## 3. PR readiness checklist

Before requesting review:

- [ ] The change is scoped to the task and does not mix unrelated work.
- [ ] The relevant tests were run and the result is recorded.
- [ ] Documentation and migration impact were considered.
- [ ] The PR description clearly states the change, proof, and rollout risk.

## 4. Canonical release checklist

Use this checklist when a change affects published images, the service contract, or deployment topology:

1. Merge the application PR first and confirm the app CI gate is green.
2. For a deployable application change, the green `main` CI run calls the reusable image-publish
   workflow. It publishes immutable images only when `AWS_IMAGE_PUBLISH_ENABLED` is explicitly
   enabled; manual dispatch remains the first-release and recovery fallback.
3. The publisher validates release metadata against current app `main` and opens or updates the
   single `automation/promote-aws-dev` application pull request.
4. Review that PR's source commit, tree, exact image digests, and app CI result. Merge the PR to
   approve the selected `images.lock.json` desired state.
5. A green app `main` CI run deploys that exact merged lock when `AWS_CD_ENABLED` is enabled.
   Manual deployment only replays the state already committed on app `main`.

Optional-profile changes use a separate application PR. Automated image promotion preserves the
profiles already reviewed and merged into app `main`.

## 5. Current deployment model

The application release handoff is a single-host in-place recreate flow with promotion-PR approval and best-effort application-image rollback; it is not rolling, blue/green, or canary. See the [application deployment contract](../07-deployment/app-repo-contract.md) for the workload flow and the sibling infra guide for platform bootstrap, backup, and host recovery.
