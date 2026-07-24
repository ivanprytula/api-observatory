# CI/CD Reference

Track: C — Architecture and Platform Strategy

---

## CI Workflow Structure

**Trigger model:** PR and push run Waves 0-3 + 5-6 (fast path). `workflow_dispatch` adds Wave 4 (slow checks).

### Wave Breakdown

| Wave | Jobs | Type |
|------|------|------|
| **0** | `change-impact` — detect changed paths | Fast |
| **1** | Infrastructure/gate: prebuilt image, service version, service matrix, docs-impact-gate, contracts-versioning-gate | Fast |
| **2** | Prechecks: Ruff lint+format, `ty` type check, `compileall` | Fast |
| **3** | Unit tests, outbox-inbox schema guard | Medium |
| **4** (gated) | Migrations, integration, e2e, compose smoke | Slow |
| **5** | Dependency audit + image build (Trivy scan + GHCR push) | Medium |
| **6** | Build summary comment | Fast |

### Common CI Failures

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Ruff fails | Lint/format issue | `uv run ruff check --fix . && uv run ruff format .` |
| `ty` fails | Type error | `uv run mypy .` to see exact error |
| `ScopeMismatch` | Async fixture scope issue | Check `conftest.py` fixture scopes |
| Docs-impact-gate | Service changed without docs update | Update relevant docs or mark exception |
| Contracts-versioning-gate | Schema changed without version bump | `python scripts/bump_contracts_version.py` |

### Branch Model

- `main` — stable, release tags (`v*`)
- `develop` — default branch
- `feature/*`, `fix/*` — work branches

---

## CI/CD + IaC Strategy

### Architecture

```text
Developer push/PR
  → GitHub Actions CI (lint, test, security, image build + SBOM + signing)
  → Artifact Registry (immutable SHA tags)
  → IaC pipeline (Terraform plan/apply via OIDC)
  → EC2 + Docker Compose (AWS Stage 0) → ECS Fargate (Stage 2) → EKS + Argo CD (future)
```

### Supply Chain Security

- CodeQL analysis
- Trivy container scan (SARIF → GitHub Code Scanning)
- Syft SBOM generation
- Cosign keyless signing (GH OIDC)
- Verification gate before deploy

### Secrets vs Variables Model

- **OIDC only** — no long-lived AWS access keys in GitHub Secrets
- GitHub Actions assumes IAM role via OIDC per workflow run
- Environment-scoped variables: `AWS_ROLE_ARN_DEV`, `DEV_ECR_REGISTRY`, `TERRAFORM_STATE_BUCKET_DEV`

### Required Accounts

GitHub, AWS (with OIDC), ECR, ACM, Route53 (optional), Terraform Cloud (optional), Sentry, Grafana Cloud (optional), PagerDuty (optional), Slack (optional).

---

## Prebuilt CI Image

A prebuilt Docker image at `ghcr.io/${{ github.repository_owner }}/data-pipeline-ci` ensures Python 3.14 consistency, preinstalled `uv`, and cached wheels across all CI jobs.

```bash
docker buildx build -f infra/ci/ci-base-image/Dockerfile -t ghcr.io/...:latest .
```

**Pinning:** Pin workflows to the image digest (`container.image: ghcr.io/...@sha256:<digest>`) for immutability. Rollback by changing digest to previous known-good.

---

## Workflow Reference

See `.github/workflows/ci.yml` for the canonical workflow definition. Key workflows:

| File | Purpose |
|------|---------|
| `ci.yml` | Full CI: lint, test, security, build, and an advisory deterministic agent-quality report |
| `performance-smoke.yml` | Weekly/manual k6 authentication and protected-read smoke; uploads a JSON baseline |
| `ci.yml` | Candidate builds/scans for ingestor, inference, and dashboard when AWS OIDC is configured |
| `release.yml` | Promote all three immutable ECR candidates to a semver tag |
| `cd-dev.yml` | Approved Stage-0 EC2 deployment through AWS Systems Manager |

---

## Related Documents

- [Deployment Guide](../07-deployment/deployment-guide.md) — deploy runbook and cloud security checklist
- [Dev Workflows](../05-development/dev-workflows.md) — local testing commands
- [Policies](../05-development/policies.md) — merge/release gates
