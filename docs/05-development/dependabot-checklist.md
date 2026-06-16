# Dependabot Verification Checklist

Track: B — Engineering Execution

Use this after editing `.github/dependabot.yml`.## Quick Checks

1. Confirm the config exists on the repository default branch.
2. Confirm each update block has `target-branch: develop`.
3. Confirm `package-ecosystem` coverage matches your stack (`pip`, `uv`, `docker`, `github-actions`).
4. Confirm schedule values are explicit (`interval`, `day`, `time`, `timezone`).
5. Confirm labels and reviewers are present for triage.
6. Confirm `open-pull-requests-limit` is set to control noise.

## Behavior Checks

1. Trigger a manual Dependabot run from repository settings.
2. Verify new version-update PRs target `develop`, not `main`.
3. Verify PR titles/labels match expected policy.
4. Verify grouped updates behave as expected (minor/patch batching).

## If a PR Still Targets Main

1. Check whether `.github/dependabot.yml` on the default branch is stale.
2. Check whether the PR was created before the config change.
3. Check whether it is a security update (security updates can follow separate repo security settings).
4. Rebase/recreate Dependabot PRs after config sync if needed.

## Dependency Cooldown Policy

This repository applies a conservative cooldown to reduce noise from short-lived releases:

- **Reduced cadence:** Python package updates (`pip` and `uv`) run monthly.
- **Early-release labeling:** PRs for newly published releases get labeled `early-dependency` by the age-guard. The label means the release is within the 7-day maturation window.
- **Local validation:** Local `uv` config uses `exclude-newer = "7 days"` so you can install and test a candidate release manually before CI adopts it.
- **Non-blocking:** Early releases are labeled, not closed; merge when ready or wait for the window to pass.

## One-Time Repo Sanity

```bash
# Verify current default branch and remote state
 git remote show origin | sed -n '/HEAD branch/s/.*: //p'

# Optional: verify config currently checked out
 sed -n '1,220p' .github/dependabot.yml
```

## Expected Outcome

- Routine dependency update PRs open against `develop`.
- Merge and release promotion happen through your normal `develop -> main` flow.
- Security updates are reviewed with explicit branch policy awareness.
