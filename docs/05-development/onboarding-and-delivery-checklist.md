# Canonical onboarding and delivery checklist

This document is the single source of truth for first-time setup, day-to-day task flow, PR readiness,
and the app-to-infra release handoff. When a contributor workflow changes, update this document first
and then link to it from the README, contributing guide, and deployment docs rather than copying the
same instructions into multiple places.

## 0. Prerequisites

The supported developer workstation is Linux (Ubuntu) or macOS with Docker Engine/Desktop and
Compose v2, a running Docker daemon, the Python version selected by [`.python-version`](../../.python-version),
`uv`, `just`, Git, and `curl`. Run `just doctor` before creating `.env`; it checks core tools and
reports optional tooling as warnings.

Terraform, Ansible, cloud CLIs, Kubernetes tools, and database client utilities are not application
onboarding requirements. Install them only for a task that owns that boundary, following the sibling
infrastructure repository's
[README](https://github.com/ivanprytula/api-observatory-infra/blob/main/README.md).

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
5. Wait for readiness with `just dev-wait-ready` and run `just db-migrate`.
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
2. Publish immutable application images; the workflow also downloads the release metadata artifact.
3. Promote the published release into the infrastructure repository:
   - Automated: when the `INFRA_PROMOTION_TOKEN` secret and the `AWS_IMAGE_PUBLISH_ENABLED`
     variables are configured in the application repository, the publish workflow dispatches an
     `app-release-published` event to the infrastructure repository. Its Stage 0 workflow then
     validates the release and, when the infra-side CD variables are enabled, promotes the
     `images.lock.json` commit itself.
   - Manual fallback: create a separate task branch in the infrastructure repository and run
     `just promote-images <artifact-path>`, then open an infra PR.
4. Review the resulting `images.lock.json` change and open an infra PR.
5. Only after the infra PR is reviewed and green should deployment be approved and executed manually.

## 5. Current deployment model

The current AWS Stage 0 deployment model is a single-host in-place recreate flow with manual approval
and best-effort rollback. It is not rolling, blue/green, or canary. The deployment guide in
[api-observatory-infra](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md)
documents the current model and the approval gate.
