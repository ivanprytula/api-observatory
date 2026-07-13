Contracts bump automation
=========================

This project includes an automated helper and CI workflow to keep `libs/contracts/VERSION`
and `libs/contracts/CHANGELOG.md` in sync with contract changes.

Files added:

- `scripts/bump_contracts_version.py` — validate or apply a semver bump and prepend a changelog entry.
- `.pre-commit-config.yaml` — local `pre-commit` hook to check staged contract changes.
- `.github/workflows/contracts-bump.yml` — GitHub Action that runs on PRs and will commit+push a bump using a bot PAT.

How to use locally

1. Run the check (pre-commit will call this automatically on staged contract changes):

```bash
python scripts/bump_contracts_version.py --check
```

1. To apply a bump locally (for testing):

```bash
python scripts/bump_contracts_version.py --apply --strategy patch --changelog-entry "Manual test bump"
git add libs/contracts/VERSION libs/contracts/CHANGELOG.md
git commit -m "ci: bump contracts VERSION (manual test)"
```

See `scripts/bump_contracts_version.py` for full CLI reference.

CI note

The workflow `.github/workflows/contracts-bump.yml` will attempt to push a small commit back
to the PR branch. For this to work when PRs come from forks, add a repository secret named
`BUMP_PAT` containing a bot PAT with `repo` write access. If you do not want to allow an automated
push, the workflow will still update files in the runner workspace but will skip the push step when
`BUMP_PAT` is not set.

CI automation status

At this time the team has decided to defer enabling automatic CI-side bumps (the push-back
behavior) until the project has a larger team and clearer maintenance ownership. The in-repo
pre-commit hook defined in `.pre-commit-config.yaml` provides local enforcement once contributors
run `pre-commit install`, without requiring secrets or bot tokens. When the project grows and
there's an agreed automation owner, we can revisit enabling the GitHub Action and add the
`BUMP_PAT` secret or use a GitHub App for safer automation.

Security: prefer a machine/bot account with minimal privileges and rotate the token regularly.

Local hook setup
----------------

Hooks are defined in `.pre-commit-config.yaml`. Install them with `pre-commit install`,
then checks run automatically on each commit. Run `pre-commit run --all-files` to trigger manually.

Maintenance
-----------

- Keep `.pre-commit-config.yaml` as the single source of truth for local commit checks.
- When a hook should no longer run locally, remove or disable it there instead of adding wrapper scripts.
- If you want an automated CI bump later, the repo workflow `.github/workflows/contracts-bump.yml` already exists.
