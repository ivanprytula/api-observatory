# CI/CD + IaC + GitOps Portable Strategy (Frankfurt First)

Track: C — Architecture and Platform Strategy


## Goal

Build a highly automated delivery model with:

- Primary deployment region: `eu-central-1` (Frankfurt)
- Minimum manual work for release and infrastructure changes
- Maximum portability across runtime platforms (ECS now, Kubernetes-ready path)
- Strong security posture (OIDC, least privilege, no long-lived cloud keys)

## Current Baseline (What Exists)

- GitHub Actions workflows for unit, integration/e2e, migration checks, and Docker build
- Terraform module-based infrastructure under `infra/terraform`
- GitHub OIDC role scaffolding in Terraform IAM module
- CI and deployment examples now target `eu-central-1`
- Docker build workflow still has push/deploy steps disabled

## Recommended Target Architecture

```text
Developer Push/PR
    |
    v
GitHub Actions CI
  - lint, type-check, unit, integration/e2e, migration verification
  - image build + SBOM + vulnerability scan + signing
    |
    v
Artifact Registry (ECR)
  - immutable tags: sha-<commit>
  - promotion tags: dev, prod
    |
    +-----------------------------+
    |                             |
    v                             v
IaC Pipeline                   GitOps Pipeline
  - Terraform plan/apply       - Update desired state repo
  - OIDC auth to AWS           - Argo CD/Flux reconciles runtime
  - drift detection            - automated health gates + rollback

Runtime options:
- Option A (near-term): ECS Fargate (low ops)
- Option B (portable): EKS + Argo CD (true GitOps portability)
```

## Region Strategy (Frankfurt)

### Recommendation

- Set `eu-central-1` as default for all environments unless there is a specific exception
- Keep DR/backup strategy in one secondary region later (for example `eu-west-1`)

### Required repository updates

1. Terraform environment defaults:

- `infra/terraform/environments/dev/variables.tf`
- `infra/terraform/environments/prod/variables.tf`
- `infra/terraform/environments/dev/terraform.tfvars.example`
- `infra/terraform/environments/prod/terraform.tfvars.example`

1. GitHub Actions workflow defaults:

- `.github/workflows/docker-build.yml` (`AWS_REGION` and `ECR_REGISTRY` domain)

1. Availability zones in tfvars/examples:

- Use `eu-central-1a`, `eu-central-1b`, `eu-central-1c` as needed

## CI/CD Design for Portability and Automation

### Implementation Status (2026-04-23)

- Implemented: queued CI and reusable deployment foundations
  - `.github/workflows/ci.yml` (single ordered CI pipeline)
  - `.github/workflows/docker-build-reusable.yml`
  - `.github/workflows/deploy-reusable.yml`
- Implemented: caller workflows with CI/CD split
  - `.github/workflows/cd-deploy.yml` (event-driven deploy entrypoint)
- Implemented: security hardening baseline
  - immutable SHA-pinned action refs
  - mutable action reference validation job in `security-full.yml`
- Implemented: GitHub configuration automation
  - `gh` native CLI for vars/secrets/OIDC maintenance (no wrapper script)
- Remaining for full target state:
  - enable cosign signing + verification gate before deploy
  - finalize digest-only deployment promotion pipeline (`dev` -> `prod`)

## 1. Split CI and CD responsibilities clearly

- CI (always on PR and push): build, test, security checks, produce signed artifacts
- CD (event-driven): deploy only from approved environment and immutable image digest

## 2. Use reusable GitHub workflows where they reduce duplication

Create reusable workflows via `workflow_call`:

- `docker-build-reusable.yml` for image build/scan/sign/push
- `deploy-reusable.yml` for environment deployment

Benefits:

- one source of truth
- easier multi-service expansion
- lower maintenance cost

## 3. Secrets vs variables model in GitHub

Use this split:

### Repository Variables (`vars`)

- `AWS_REGION=eu-central-1`
- `ECR_REPOSITORY_PREFIX=data-zoo`
- `PYTHON_VERSION=3.14`
- `UV_VERSION=0.11.211`

### Environment Variables (`vars` in `dev`, `prod`)

- `ECS_CLUSTER_NAME`
- `ECS_SERVICE_NAME`
- `AWS_ROLE_ARN` (can be variable, not secret)
- `DEPLOYMENT_STRATEGY` (`rolling`, `blue_green`, `canary`)

### Repository/Environment Secrets (`secrets`)

Only sensitive values:

- `SLACK_WEBHOOK_URL` (if used)
- `SENTRY_AUTH_TOKEN` (if used)
- `TF_API_TOKEN` (only if Terraform Cloud is used)

Do not store:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

Use OIDC only.

### Programmatic management with `gh` CLI

Use `gh` directly — it natively supports vars, secrets, and environment-scoped configuration:

```bash
# Repository variable
gh variable set AWS_REGION --body "eu-central-1" --repo ivanprytula/api-observatory

# Environment variable
gh variable set ECS_CLUSTER_NAME --env dev --body "data-zoo-dev" --repo ivanprytula/api-observatory

# Repository secret
gh secret set AWS_ACCOUNT_ID --body "123456789012" --repo ivanprytula/api-observatory

# Environment secret (value from local env var of same name)
gh secret set SENTRY_AUTH_TOKEN --env prod --repo ivanprytula/api-observatory

# OIDC subject template customization
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
"/repos/ivanprytula/api-observatory/actions/oidc/customization/sub" \
  -f use_default=false \
  -f "include_claim_keys[]=repo" \
  -f "include_claim_keys[]=context"

# OIDC template show/reset
gh api "/repos/ivanprytula/api-observatory/actions/oidc/customization/sub"
gh api --method PUT "/repos/ivanprytula/api-observatory/actions/oidc/customization/sub" \
  -f use_default=true
```

Notes:

- `gh secret` and `gh variable` handle configuration writes natively.
- OIDC customization uses GitHub REST API through `gh api`.
- Authenticate first with `gh auth login`.

## 4. Supply chain security in CI

Add automated controls:

- Dependency review on PR
- SAST (`CodeQL`)
- Image scanning (`Trivy`)
- SBOM generation (`syft` or similar)
- Image signing (`cosign` keyless via OIDC)
- Verification gate before deployment

## 5. Promotion model

Use immutable promotion, not rebuild per env:

1. Build once on merge
2. Push image tagged with commit SHA and digest
3. Promote same digest to `dev` then `prod`
4. Deploy only promoted digest

This improves reproducibility and rollback reliability.

## IaC Automation Strategy

## 1. Keep Terraform modules, automate plan/apply

Use pull-request based IaC workflow:

- PR: `terraform fmt`, `validate`, `tflint`, `tfsec/checkov`, `plan`
- Merge to environment branch: `apply`
- Post apply outputs to artifact/summary

## 2. State and locking

- Keep remote state in S3 with lockfile locking
- Enable versioning and encryption on state bucket
- Restrict state bucket access to CI role + admin break-glass role

## 3. Drift detection

Add scheduled workflow:

- daily `terraform plan -detailed-exitcode`
- open issue automatically on drift

## 4. Environment isolation

Recommended account layout (best):

- AWS account 1: `data-zoo-dev`
- AWS account 2: `data-zoo-prod`

If keeping single account for now, isolate with strict IAM boundaries and tags.

## GitOps Strategy (Practical Path)

## Option A: ECS-first GitOps-like flow (minimal migration)

- Keep ECS runtime
- Store desired deployment state in Git (image tag/digest per env)
- CD workflow reads desired state and updates ECS service
- Add automated post-deploy smoke tests and rollback on failure

Good for fast adoption, lower complexity.

## Option B: Full GitOps with Argo CD (maximum portability)

- Move runtime to EKS (or any Kubernetes)
- Use Helm/Kustomize manifests in Git
- Argo CD reconciles desired state continuously
- Progressive delivery via Argo Rollouts (canary/blue-green)

Best long-term portability across AWS/Azure/GCP and on-prem Kubernetes.

## Suggested staged migration

1. Stage 1: Harden current GHA + Terraform + ECS
2. Stage 2: Add promotion, signing, policy gates
3. Stage 3: Introduce GitOps repo and reconciler
4. Stage 4: Optional EKS move when platform portability becomes priority

## Online Service Accounts You Need

This section is the requested checklist of online accounts/services.

## Mandatory Accounts

| Service | Account Type Needed | Purpose | Owner | Notes |
| --- | --- | --- | --- | --- |
| GitHub | Organization or dedicated project owner account | Source control, PRs, Actions, environments, branch protection | Team/Admin | Enable branch protection + required checks |
| AWS | At least one AWS account (prefer separate dev/prod) | Runtime, networking, data services, IAM OIDC trust | Cloud/Admin | Primary region: `eu-central-1` |
| AWS IAM Identity Center (SSO) | User + group assignments | Human access management with least privilege | Security/Admin | Avoid direct IAM users for humans |
| AWS ECR | Registry in AWS account | Store signed container images | Platform | Repositories per service |
| AWS ACM | Certificate management | TLS for ALB/API endpoints | Platform | Certificates must exist in deployment region |
| AWS Route 53 | Hosted zone management | DNS for app endpoints | Platform | Optional if using external DNS provider |
| GitHub Container/Artifact tooling | Built-in | Store artifacts, test reports, provenance metadata | CI | Already available with GitHub |

## Strongly Recommended Accounts/Services

| Service | Account Type Needed | Purpose | Why it matters |
| --- | --- | --- | --- |
| Terraform Cloud or Spacelift (optional) | Team workspace account | Centralized runs, policy as code, RBAC | Reduces manual Terraform operations |
| Sentry | Team project account | Error tracking and release health | Faster production incident triage |
| Grafana Cloud (or managed Prometheus/CloudWatch setup) | Team account | Metrics, dashboards, alerts | Production observability baseline |
| PagerDuty/Opsgenie | Team account | On-call alert routing | Automated incident response |
| Slack/Teams App integration | Workspace app/bot | CI/CD and alert notifications | Shorter feedback loop |
| Docker Hub (optional) | Org account | Secondary image mirror (if desired) | Registry redundancy |

## Optional Security/Quality Services

| Service | Account Type Needed | Purpose |
| --- | --- | --- |
| SonarCloud | Organization account | Code quality gates |
| Snyk | Organization account | Dependency and image vulnerability monitoring |
| Codecov | Organization account | Coverage reporting and PR annotations |

## Minimum Manual Work Setup Checklist

1. Create GitHub environments: `dev`, `prod`
2. Configure environment protection rules (reviewers, branch restrictions)
3. Create one AWS OIDC deploy role per environment
4. Store only non-sensitive config in `vars`, sensitive config in `secrets`
5. Enable reusable workflows and matrix jobs where useful
6. Enable auto-merge only after required checks pass
7. Add scheduled drift detection and dependency update workflows
8. Add deployment health checks and automatic rollback criteria
9. Tag releases semantically and produce changelog automatically
10. Add ChatOps notification for deploy start/success/failure

## Example GitHub Environments and OIDC Roles

| Environment | Branch | AWS Account | Region | OIDC Role |
| --- | --- | --- | --- | --- |
| `dev` | `develop` | `data-zoo-dev` | `eu-central-1` | `arn:aws:iam::<dev-account-id>:role/data-zoo-gha-dev` |
| `prod` | `main` | `data-zoo-prod` | `eu-central-1` | `arn:aws:iam::<prod-account-id>:role/data-zoo-gha-prod` |

Trust policy condition should match branch/environment to enforce least privilege.

## Recommended Next Changes in This Repository

1. Keep all new AWS examples and defaults aligned to `eu-central-1`
2. Pin all GitHub Actions to full commit SHA (supply chain hardening)
3. Add explicit workflow-level permissions with `id-token: write` only where needed
4. Enable OIDC auth and ECR push in Docker workflow
5. Add `terraform-plan.yml` and `terraform-apply.yml` workflows
6. Add `security.yml` workflow (CodeQL + Trivy + dependency review)
7. Add `release-promote.yml` workflow for digest-based promotion

## Decision Guidance

- If your near-term goal is shipping quickly with low ops burden, keep ECS and apply Option A.
- If your main goal is cloud portability and GitOps purity, plan Option B with EKS + Argo CD.
- In both cases, OIDC + immutable artifacts + policy gates are the highest-impact changes.
