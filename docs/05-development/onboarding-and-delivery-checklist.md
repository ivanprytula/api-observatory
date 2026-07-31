# Canonical onboarding and delivery checklist

This document is the single source of truth for first-time setup, day-to-day task flow, PR readiness,
and the app-to-infra release handoff. When a contributor workflow changes, update this document first
and then link to it from the README, contributing guide, and deployment docs rather than copying the
same instructions into multiple places.

## 1. Canonical onboarding path

Use this path for first-time setup or when returning to the repository after a long gap:

1. Review the app [README](../../README.md) and the [setup guide](../04-setup/setup-guide.md).
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
