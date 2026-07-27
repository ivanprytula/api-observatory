# ADR 009: Historical Azure Free-Tier Deployment Choice

## Status

Superseded (2026-07-24) by the AWS Stage 0 direction documented in
[current roadmap](../../03-planning/mvp-roadmap.md). The Azure deployment was
not completed and this file is historical evidence, not the current deployment contract.

## Context

The API Observatory MVP needs a cloud deployment to demonstrate end-to-end production readiness. Two options were evaluated:

- **AWS**: Existing Terraform infrastructure (ECS Fargate, RDS, ElastiCache, ALB) and CI/CD pipeline. Free tier expired.
- **Azure**: 172 EUR credit balance, 12-month free tier with B1s VM (750 hrs/month), ACR Standard, PostgreSQL Flexible Server (B1ms), 5 GB Blob Storage.

The deployment serves a portfolio demo, not production traffic. Cost and learning value are the primary drivers.

## Decision

Deploy to Azure Free Tier using:

- **B1s VM** running Docker Compose (ingestor, dashboard, PostgreSQL, Redis, nginx — all containers on one VM)
- **ACR Standard** for Docker image storage (already provisioned, 16% utilization)
- **PostgreSQL Flexible Server (B1ms)** available if needed (750 hrs/month free) — but MVP runs PostgreSQL in Docker on the VM to conserve resources
- **floci-az** for local development (Azure-compatible emulator)

AWS infrastructure code preserved on `develop` branch for future reference.

## Consequences

### Positive

- Zero monthly cost for 3-week demo window
- Hands-on experience with a second cloud provider (resume differentiator)
- Simpler deployment model (Docker Compose on VM vs. managed ECS + ALB + RDS)
- ACR-to-VM image pulls stay within Azure network (no egress)

### Negative

- No managed container orchestration (manual SSH deploy vs. ECS rolling updates)
- B1s VM (1 vCPU, 1 GB RAM) limits concurrent load
- No managed database backups (must script pg_dump to Blob Storage)
- WebSocket streaming dashboard may hit memory limits under load

### Neutral

- CI pipeline remains GitHub Actions (unchanged)
- Docker images are the same regardless of cloud target
- Can migrate to AKS or Azure Container Apps when ready for paid tier

## Future Path

After MVP validation (3 weeks), evaluate:
1. Stay on Azure free tier if demo is sufficient
2. Upgrade to paid Azure (B2s VM or Container Apps) for sustained hosting
3. Return to AWS if ECS/Fargate pipeline is needed for production scale
