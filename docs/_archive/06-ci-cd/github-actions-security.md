# GitHub Actions Security Hardening

Track: C — Architecture and Platform Strategy


This document explains how to secure GitHub Actions workflows by pinning action references to immutable commit SHAs and maintaining them over time.

Note: this repository also uses a curated, prebuilt CI image for Python-based jobs: `ghcr.io/${{ github.repository_owner }}/data-pipeline-ci`. The image guarantees Python 3.14 parity, preinstalled `uv` and cached wheels. See Prebuilt CI Image for build, pinning, and rollback instructions.

## The Problem: Mutable Action References

Default GitHub Actions workflows pin to **mutable tags** like `@v4` or `@latest`:

```yaml
# ❌ VULNERABLE — Mutable tag can be redirected to malicious commit
uses: actions/checkout@v4
uses: actions/setup-python@latest
```

If a malicious actor gains write access to an action's repository, they can silently move the tag (e.g., `@v4`) to a compromised commit. This is a **supply chain attack** that executes arbitrary code in your CI/CD pipeline.

## The Solution: Full Commit SHA Pinning

Pin all actions to **immutable full commit SHAs** with a human-readable version comment:

```yaml
# ✅ SECURE — Immutable SHA cannot be redirected
uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v4.3.1
uses: actions/setup-python@3235b876344d2a9aa001b8d1453c930bba69e610 # v3.9.1
```

**Why this matters**:

- SHAs are immutable — cannot be moved or changed once committed
- The version comment (e.g., `# v4.3.1`) is for human readability in logs
- Combining both gives you security + maintainability

## Finding Action SHAs

### Method 1: GitHub CLI (Fastest)

```bash
# Find the latest SHA for a specific action version

gh api repos/aws-actions/configure-aws-credentials/commits/v6.2.0 --jq '.sha'

# Result: SHA like de0fac2e4500dabe0009e67214ff5f5447ce83dd
```

### Method 2: GitHub Web UI

1. Navigate to the action's repository: `https://github.com/actions/checkout`
2. Go to **Releases** tab
3. Click on the version (e.g., "v4.3.1")
4. Find the commit SHA in the release page (or view the tag)

### Method 3: Git Command (If Action is a Local Repo)

```bash
cd /tmp && git clone https://github.com/actions/checkout.git
cd checkout && git rev-list -n 1 v4.3.1
```

### Method 4: GitHub API

```bash
curl -s https://api.github.com/repos/actions/checkout/releases/tags/v4.3.1 \
  | jq '.target_commitish'
```

## Automated Maintenance with Dependabot

Dependabot can **automatically create pull requests** to update action SHAs when new versions are released.

### Step 1: Create `.github/dependabot.yml`

```yaml
version: 2
updates:
  # Update GitHub Actions to latest versions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "03:00"
    labels:
      - "dependencies"
      - "github-actions"
    commit-message:
      prefix: "chore(actions): update"
    pull-request-branch-name:
      separator: "/"
    open-pull-requests-limit: 5
    reviewers:
      - "ivanp"
```

### Step 2: Enable Dependabot in Repository Settings

1. Go to **Settings** → **Code security and analysis**
2. Ensure **Dependabot version updates** is enabled
3. Ensure **Dependabot alerts** is enabled

### Step 3: Configure PR Merging (Optional)

Create `.github/workflows/auto-merge-dependabot.yml` to auto-merge Dependabot PRs for GitHub Actions:

```yaml
name: Auto-Merge Dependabot PRs

on:
  pull_request:
    types:
      - opened
      - synchronize
      - reopened

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]' && contains(github.event.pull_request.title, 'github-actions')

    permissions:
      contents: write
      pull-requests: write

    steps:
      - name: Enable auto-merge for Dependabot PR
        run: |
          gh pr merge "${{ github.event.pull_request.number }}" \
            --auto \
            --squash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Manual Workflow Hardening Checklist

For each workflow file in `.github/workflows/`:

1. **Find all `uses:` statements**:

   ```bash
   grep -n "uses:" .github/workflows/*.yml
   ```

2. **Replace mutable references with SHAs**:

   ```yaml
   # Before:
   uses: actions/checkout@v4

   # After:
   uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v4.3.1
   ```

3. **Add explicit permissions blocks** (principle of least privilege):

   ```yaml
   name: My Workflow
   on: [push, pull_request]

   permissions:
     contents: read        # Allow repo read
     pull-requests: write  # Allow PR updates (if needed)
     # Deny all others implicitly (id-token, deployments, etc.)

   jobs:
     my-job:
       runs-on: ubuntu-latest
       # Can override at job level if needed:
       permissions:
         id-token: write   # For OIDC to AWS
         contents: read
   ```

## Common Action SHAs (As of 2025-02-15)

| Action                                  | Latest Version | SHA (40-char)                               |
| --------------------------------------- | -------------- | ------------------------------------------- |
| `actions/checkout`                      | v4.3.1         | `de0fac2e4500dabe0009e67214ff5f5447ce83dd`  |
| `actions/setup-python`                  | v5.4.0         | `8ffe231b26690ac58f30d6956d38fbe87c938ec11` |
| `actions/upload-artifact`               | v4.5.0         | `bbbca2ddaa5d8feaa63e36b76fdaad77386f024f`  |
| `actions/download-artifact`             | v4.1.5         | `5175b73c45da0e1d79c9b61a4e2ca1c31d7e2302`  |
| `actions/cache`                         | v4.1.5         | `668228422ae6a00e4ad889ee87cd7109ec5666a7`  |
| `aws-actions/configure-aws-credentials` | v4.0.2         | `5f0e8e11c7ad15b18e5f5fa5b80487b85c6cc2bc`  |
| `docker/build-push-action`              | v6.9.0         | `3b5e8027fcad23fda98b2e3ac259d8d67585f671`  |

**To always find the latest**, use one of the methods above rather than this table.

## Verification

After hardening workflows, verify all action references use SHAs:

```bash
# Should find NO results (only comments):
grep -E 'uses: .+@(latest|v[0-9])' .github/workflows/*.yml

# Should find results (all actions pinned):
grep -E 'uses: .+@[a-f0-9]{40}' .github/workflows/*.yml
```

## GitHub Actions Supply Chain Security Best Practices

1. **Always pin to commit SHAs**, never tags or branches
2. **Keep actions updated** — use Dependabot or set calendar reminders quarterly
3. **Audit third-party actions** before use — review source code on GitHub
4. **Use `GITHUB_TOKEN` with least privilege** — default to `contents: read`, add specific write permissions only when needed
5. **Enable branch protection rules** to require workflow checks before merge
6. **Monitor for alerts** — GitHub notifies of vulnerable actions

## Maintenance Schedule

- **Monthly**: Check Dependabot for open update PRs
- **Quarterly**: Manually audit important action versions
- **Annually**: Review entire `.dependabot.yml` configuration and workflow permissions

## References

- [GitHub Actions Security Hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [GitHub Actions Best Practices](https://docs.github.com/en/actions/guides/actions-security-guides)
- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [OWASP — Supply Chain Security](https://owasp.org/www-community/attacks/Supply_chain_attack)
