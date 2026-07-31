# Contributing

This repository uses short-lived task branches into `main`. The sibling infrastructure repository
uses the same branch model. Keep application and infrastructure changes in separate commits and pull
requests even when they implement one cross-repository contract change.

## Start a Task

Begin from an up-to-date `main` branch and create a focused branch:

```bash
git switch main
git pull --ff-only
git switch -c <type>/<short-task-name>
```

Use `feat/`, `fix/`, `docs/`, `test/`, `refactor/`, `ci/`, or `chore/` as the branch prefix. Do not
develop directly on `main`.

For first-time local setup, follow the [setup guide](docs/04-setup/setup-guide.md). During normal
development, use the smallest runtime and proof listed by
[development workflows](docs/05-development/dev-workflows.md). For the current contributor workflow,
the [canonical onboarding and delivery checklist](docs/05-development/onboarding-and-delivery-checklist.md)
is the single source of truth for onboarding, task flow, PR readiness, and the app-to-infra release
handoff.

## Prepare a Commit

Review the complete change before staging:

```bash
git status --short
git diff
git diff --check
```

Stage only the files or exact hunks owned by the task. Do not use `git add .` or `git add -A` in a
shared or dirty worktree.

```bash
git add <explicit-paths>
git diff --cached --check
git diff --cached
git commit -m "<type>: <imperative summary>"
```

Use conventional commit prefixes: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, or `chore`.
Pre-commit hooks are part of the commit gate; do not bypass them without explicit review.

## Push and Open a Pull Request

```bash
git push -u origin HEAD
gh pr create --base main --fill
```

The maintainer policy is to merge only after `CI / Merge gate` succeeds and review conversations are
resolved. GitHub does not currently enforce required checks or approvals, so verify that evidence
manually before merging. Manual assurance and image publication are not routine merge requirements.

## Cross-Repository Delivery

The app-to-infra release handoff is documented in the canonical checklist and the deployment
contract, so this file intentionally avoids maintaining a second copy of those steps. Keep the app
PR and infra PR separate, but follow the canonical checklist for the current promotion flow.

Never describe a workflow, image, Terraform plan, or committed lock as a completed deployment.
