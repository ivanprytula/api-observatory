# Cloud Deployment Model

Track: C - Architecture and Platform Strategy

This document defines cloud deployment policy and architecture choices.

Execution runbook for deployments:

- AWS ECS

Local sandbox progression:

- Floci Sandbox Workflow

## Scope

This project deploys to AWS ECS/Fargate.
Kubernetes remains a separate learning path and is not the default runtime target for this repository.

## Safe Defaults

- CD is manual by default for deployment workflows.
- Production deployments require protected environments and reviewer approval.
- Environment-scoped secrets are preferred over repository-global deployment secrets.
- Branch protection should track current required check contexts only.

## Why ECS/Fargate

ECS/Fargate is the operationally lean target for this project scale:

- minimal control-plane burden
- simple deployment primitives
- straightforward CI/CD integration
- predictable cost profile for small-to-medium service counts

## Reference Architecture

```text
Internet
  -> Route53
  -> ALB
  -> ECS services (private subnets)
     -> RDS PostgreSQL
     -> ElastiCache Cache
     -> Messaging layer (when enabled)
```

## IaC Structure

Infrastructure is managed via Terraform modules under [infra/terraform](../../infra/terraform).
Environment-specific plans are under [infra/terraform/environments](../../infra/terraform/environments).

## Governance Checklist

Before production rollout:

1. Environment protections enabled.
2. OIDC role wiring verified.
3. Deployment secrets and variables scoped per environment.
4. Rollback path documented and tested.
5. Cost teardown steps prepared.

## Related Documents

- AWS ECS
- Cost Teardown
- Floci Sandbox Workflow
- CI/CD Workflow Reference
- ADR-008: ECS Fargate vs EKS
