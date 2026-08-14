# Online and Cloud Services and Accounts for Long-Term Project Operation

Track: D — Business and Interview Narrative

## Purpose

This document is the long-term reference for all external services, accounts, and paid tools required to build, ship, secure, and operate this project.

Use it as:

- onboarding checklist for new maintainers
- billing visibility document
- operations ownership matrix
- periodic maintenance checklist

## Scope

Covers services required to:

- develop and collaborate
- run CI/CD
- deploy and host runtime workloads
- observe and secure production
- support incident response and reliability

## Service Inventory

| Service | Required | Account Type | Pay Likely | Primary Use |
| --- | --- | --- | --- | --- |
| GitHub | Yes | Organization or owner account | Yes (Team/Actions usage) | Source control, PRs, Actions, security features |
| AWS | Yes | Cloud account(s) | Yes | Runtime, storage, networking, IAM |
| AWS IAM Identity Center | Yes | Org-level identity setup | No direct fee | SSO, access governance |
| AWS ECR | Yes | In AWS account | Yes | Container image registry |
| AWS S3 | Yes | In AWS account | Yes | Terraform state + lockfile locking |
| AWS ACM | Yes | In AWS account | Low/none for public cert issuance | TLS certificates |
| AWS Route 53 (or external DNS) | Usually | In AWS account / external DNS account | Yes | DNS and domain routing |
| GitHub OIDC trust to AWS | Yes | IAM role + trust config | No direct fee | Keyless CI/CD auth |
| CloudWatch | Yes | In AWS account | Yes | Logs/metrics/alarms |
| Prometheus + Grafana | Recommended | Self-hosted or Grafana Cloud | Yes (if managed) | Metrics dashboards and SLOs |
| Sentry | Recommended | Team account | Yes | Error tracking and release health |
| PagerDuty/Opsgenie | Recommended | Team account | Yes | On-call and incident escalation |
| Slack or Microsoft Teams | Recommended | Workspace + app integration | Usually | Alerts and deployment notifications |
| Terraform Cloud or Spacelift | Optional | Team workspace | Yes | IaC policy, central runs, RBAC |
| SonarCloud | Optional | Organization account | Yes | Code quality gates |
| Snyk | Optional | Organization account | Yes | Dependency/container vulnerability tracking |
| Codecov | Optional | Organization account | Yes | Coverage tracking and PR annotations |
| Docker Hub mirror | Optional | Org account | Yes (if private/high usage) | Secondary image distribution |

## Must-Have Account Setup

## 1. GitHub

Create and maintain:

- repository owner/organization account
- branch protection rules for main and develop
- GitHub Environments: dev, prod
- repository variables and secrets
- Dependabot enabled for actions and dependencies

Critical configuration:

- enforce required status checks before merge
- restrict direct pushes to protected branches
- enforce least-privilege workflow permissions

## 2. AWS Foundation

Create and maintain:

- one AWS account for the first approved `aws-dev` exercise
- IAM Identity Center users/groups/permission sets
- OIDC federation from GitHub to AWS IAM roles
- ECR repositories for service images
- S3 with lockfile locking for Terraform remote state
- VPC, ECR, one SSM-operated EC2 host, encrypted EBS, Parameter Store, and retained S3 backups

ECS on Fargate and EKS are later AWS learning stages. Do not create their resources before the EC2
deployment, recovery, rollback, and teardown path has exercised evidence.

Primary region:

- eu-central-1

Recommended account model:

- api-observatory-dev

## 3. Domain and TLS

Create and maintain:

- DNS hosted zone (Route 53 or external provider)
- ACM certificates in deployment region
- validation records and renewal monitoring

## 4. CI/CD Security and Artifact Chain

Create and maintain:

- GitHub Actions OIDC role mapping per environment
- cosign signing and verification path
- dependency-review + CodeQL workflows
- immutable digest-based image promotion

## 5. Observability and Incident Stack

Create and maintain:

- CloudWatch log groups and alarm baselines
- Prometheus/Grafana dashboards (self-hosted or managed)
- Sentry project and environment mapping
- PagerDuty/Opsgenie escalation policy
- Slack/Teams alert routing channels

## Ownership Matrix

| Domain | Owner | Backup Owner | Review Cadence |
| --- | --- | --- | --- |
| GitHub org/repo admin | Platform/Admin | Tech Lead | Monthly |
| AWS org/accounts/IAM | Cloud/Admin | Security Lead | Monthly |
| CI/CD workflows | Platform | Senior Backend Engineer | Per PR + monthly |
| Terraform state and access | Platform | Cloud/Admin | Monthly |
| Runtime infrastructure (EC2 MVP; ECS on Fargate and EKS later) | Platform | SRE/DevOps | Weekly |
| Security scanners and policies | Security | Platform | Weekly |
| Monitoring/alerting | SRE/Platform | Backend Lead | Weekly |
| Incident tooling | SRE | Platform | Quarterly |

## Cost Planning and Budget Buckets

Track spend in these buckets:

1. Core cloud runtime (compute, storage, networking)
2. CI/CD and developer platform (GitHub Actions minutes/storage)
3. Security tooling (Snyk/SonarCloud and related services)
4. Observability (logs, metrics, tracing, error monitoring)
5. Incident response and communication tooling

Practical budget controls:

- set AWS Budgets with monthly alert thresholds
- separate tags/cost allocation per environment
- cap log retention where possible
- use non-prod scaling policies aggressively in dev

## Ongoing Maintenance Checklist

## Daily

- review failed deployments and critical alerts
- triage dependency/security workflow failures

## Weekly

- review cloud spend anomalies
- review open Dependabot PRs and merge safe updates
- verify backup/restore and alert routing are healthy

## Monthly

- rotate or validate high-risk credentials/tokens if any remain
- audit IAM roles and least-privilege policy drift
- verify GitHub branch protection and environment rules
- review observability noise and adjust alert thresholds

## Quarterly

- disaster recovery drill (at least tabletop)
- dependency and tool vendor reassessment
- CI/CD control audit (signing, verification, permissions)

## Setup Checklist (One-Time)

| Setup Item | Create Now | Can Defer | Free Tier / Low Cost | Owner | Current Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| GitHub repository governance baseline | Yes | No | Partial | Platform/Admin | Partial | Workflows, required-check scripts, and environment scaffolding exist. Branch protection is not fully applied yet. |
| AWS account for `aws-dev` | Yes if deploying to cloud soon | Yes if staying local-only | No | Cloud/Admin | Not verified | Repository configuration does not prove that the target account or its controls exist. |
| IAM Identity Center and permission sets | No | Yes | Yes for service itself | Cloud/Admin | Not started / not verified | No repo evidence of Identity Center setup. Needed once multiple human operators need controlled AWS access. |
| GitHub OIDC trust and deploy roles | Yes before push/promote/deploy | No once cloud deploy starts | Yes for OIDC itself | Platform/Admin + Cloud/Admin | Partial | Workflows are wired for OIDC, but AWS auth inputs are still incomplete in GitHub configuration. |
| ECR repositories for all service images | Yes before image push/promotion | Yes if only building locally | No | Platform/Admin | Not verified | CI/build/promotion support `ingestor`, `inference`, `dashboard`, and `cache`; repository configuration does not prove that ECR repositories exist. |
| Terraform backend (S3 + lockfile locking) | Yes before shared Terraform use | Yes if Terraform is not being applied yet | Low cost | Platform/Admin | Not verified | Documented in cloud setup docs, but live backend provisioning is not visible from this repo alone. |
| DNS and ACM certificates | No for the private MVP | Yes until public exposure is approved | ACM public certs are low/no direct cost; DNS is paid | Cloud/Admin | Deferred | Add only when a public ingress, stable domain, and ownership requirement exists. |
| GitHub environments `aws-image-publish` / `aws-dev` | Yes before image publication/deployment | No once cloud deployment starts | Yes | Platform/Admin | Not verified | Workflows define the contract, but external environment variables, protection rules, and OIDC trust are not proven from the repository. |
| Monitoring, error tracking, and incident routing | No for initial local-only development | Yes | Mixed | SRE/Platform | Partial | CloudWatch, Prometheus/Grafana, and security workflows are represented in repo docs/workflows; Sentry/PagerDuty/Slack setup is not verified. |
| Budget alerts and ownership rotation | No for earliest prototype stage | Yes | Yes / low cost | Cloud/Admin + Platform/Admin | Not started / not verified | Should be added before sustained cloud usage to prevent silent spend growth. |

Status legend:

- `Not started / not verified`: no reliable repo evidence that the external setup exists yet
- `Partial`: repo wiring or docs exist, but the external account/service setup is still incomplete
- `Ready`: both repo wiring and external setup are in place

## Optional but High-Value Services

Adopt when team/project complexity grows:

- Terraform Cloud/Spacelift for policy-based IaC operations
- Snyk for broader supply chain visibility
- SonarCloud for quality gate governance
- Codecov for strict test coverage management

## Related Project Documents

- [CI/CD](../06-ci-cd/ci-cd.md)
- Infrastructure Deployment Guide
