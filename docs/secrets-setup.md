# GitHub Secrets Setup — DHI Docker Hub Access

## Repos that need secrets

Only **`api-observatory`** pulls `dhi.io` images directly in CI.
Sibling repos (`api-observatory-infra`, `agent-forge`) do **not** reference DHI images — no secrets needed there.

---

## Required secrets (2 per repo)

| Secret name | Value | Where to get it |
|-------------|-------|-----------------|
| `DOCKERHUB_USERNAME` | Your Docker Hub username | Docker Hub account |
| `DOCKERHUB_TOKEN` | Docker Hub access token (read-only) | Docker Hub → Security → New Access Token |

### How to create the token

1. Log in to [hub.docker.com](https://hub.docker.com)
2. Account Settings → Security → Access Tokens
3. Create token with **Read Only** permission
4. Copy the token value (you won't see it again)

---

## Where to add the secrets

### Option A: Repository-level (recommended)

```bash
# Using GitHub CLI
gh secret set DOCKERHUB_USERNAME --repo ivan-pi/api-observatory
gh secret set DOCKERHUB_TOKEN --repo ivan-pi/api-observatory
```

Or via web UI:
`https://github.com/ivan-pi/api-observatory/settings/secrets/actions`

### Option B: Organization-level (if all repos share the same Docker Hub account)

```bash
gh secret set DOCKERHUB_USERNAME --org your-org
gh secret set DOCKERHUB_TOKEN --org your-org
```

Then grant the secrets to the `api-observatory` repo via org secret permissions.

---

## Verification

After adding secrets, trigger a workflow run:

```bash
gh workflow run ci.yml --repo ivan-pi/api-observatory
```

Watch for the "Log in to Docker Hub" step to succeed in:

- `.github/workflows/ci.yml` → `integration` and `capability` jobs
- `.github/workflows/assurance.yml` → `performance-smoke` job

If the step fails with `401 Unauthorized`, double-check:

1. Token has **Read Only** scope
2. Secret names match exactly (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`)
3. Token was created under the same Docker Hub account as `DOCKERHUB_USERNAME`
