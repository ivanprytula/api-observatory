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
[development workflows](docs/05-development/dev-workflows.md).

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

When an app/infra contract changes:

1. Merge the application PR first and let `main` CI succeed.
2. Manually publish immutable application images only when the protected AWS gate is enabled.
3. Download the resulting `release-metadata-<commit-SHA>` artifact.
4. In `api-observatory-infra`, create a separate task branch from `main`, run
   `just promote-images <artifact-path>`, review `images.lock.json`, and open an infra PR.
5. After the infra merge gate succeeds, deployment remains a separately approved manual action.

If the change affects published runtime images, the service contract, or deployment topology, do not
proceed without a reviewed app `main` CI success, a published image metadata artifact, and a separate
infra PR that updates `images.lock.json`.

Never describe a workflow, image, Terraform plan, or committed lock as a completed deployment.
