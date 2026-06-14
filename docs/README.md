# Documentation Storyline

Track: Index — Multi-track Navigation

Read this repository as five tracks.

## Track A: Product and Onboarding

This is the path from zero to a working local environment and first contribution.

1. [Project Overview](00-project-overview.md): scope and technical context.
2. [System Setup](01-system-setup.md): host and package prerequisites.
3. [First-Time Setup](02-first-time-setup.md): local bootstrap end-to-end.
4. [Daily Development](03-daily-development.md): workflow intent and sequence.
5. [Cross-Functional Role Onboarding](personal/05-cross-functional-role-onboarding.md): role-specific onboarding for Agile team members.

## Track B: Engineering Execution

This is the day-to-day implementation and operations path.

1. [Dev Commands](dev/commands.md): canonical command catalog.
2. [System Requirements](setup/system-requirements.md): package/tool source of truth.
3. [Environment Setup](setup/environment-setup.md): environment and workflow wiring.
4. [Docker Security Scanning Setup](setup/docker-security-scanning-setup.md): image and dependency scanning.
5. [Local HTTPS Setup](setup/local-https-setup.md): TLS parity in local development.

## Track C: Architecture and Platform Strategy

This is the system design, cloud, and long-term technical direction path.

1. [Architecture Overview](04-architecture-overview.md): system internals and boundaries.
2. [Cloud Deployment](cloud-deployment.md): cloud runtime and deployment model.
3. [AWS ECS Deployment Guide](deployment/aws-ecs.md): deployment execution sequence and verification.
4. [Deployment Cost Teardown](deployment/cost-teardown.md): explicit shutdown and cost control checklist.
5. [ADR Index](adr/README.md): decision records and architectural trade-offs.
6. [Design Decisions](design/decisions.md): cross-cutting rationale.

Note: Architecture documents have different scopes — see [04-architecture-overview.md](04-architecture-overview.md) for the MVP single-service ingestor, and [design/architecture.md](design/architecture.md) for the long-term, multi-service vision.

## Track D: Business and Interview Narrative

This is the portfolio/career communication path.

1. [CV](personal/CV.md): candidate narrative and positioning.
2. [Interview Prep](personal/10-interview-prep-middle-plus.md): answer structures and scenario framing.
3. [Cloud Services and Accounts](personal/11-online-cloud-services-and-accounts.md): ownership and cost/account thinking.
4. [Project Evolution and Growth Playbook](design/project-evolution-and-growth-playbook.md): product value framing, monetization options, and sponsorship strategy.

## Track E: Archive and Historical Snapshots

This track preserves dated progress artifacts and portfolio snapshots.

1. [Progress Index](personal/README.md): current-vs-historical map.
2. [Roadmap](personal/roadmap.md): canonical prioritized plan.
3. Portfolio snapshots under [personal/](personal/).

## Canonical Sources (No Duplication)

Use these as the single source of truth for each domain:

| Domain | Canonical document | What belongs there |
| --- | --- | --- |
| Setup packages and tooling | [setup/system-requirements.md](setup/system-requirements.md) | Host package matrix, install commands, verification checks |
| Environment policy | [setup/environment-setup.md](setup/environment-setup.md) | Env precedence, required vars, local vs CI vs deployment rules |
| Canonical command source | [dev/commands.md](dev/commands.md) | Exact runnable commands and scripts |
| Workflow intent and sequence | [03-daily-development.md](03-daily-development.md) | Workflow sequence and cadence, without command duplication |
| Cloud runtime strategy | [cloud-deployment.md](cloud-deployment.md) | Platform choice, governance, architecture-level deployment policy |
| Deploy runbook (Floci sandbox + dev) | [deployment/deploy-runbook.md](deployment/deploy-runbook.md) | Pre-flight, deploy steps, smoke-test matrix, rollback, failure modes |
| Floci local sandbox specifics | [floci-aws-deployment-workflow.md](floci-aws-deployment-workflow.md) | Floci container management, local AWS emulation setup |
| Real AWS ECS specifics | [deployment/aws-ecs.md](deployment/aws-ecs.md) | Terraform modules, real AWS resource configuration |
| Cost teardown checklist | [deployment/cost-teardown.md](deployment/cost-teardown.md) | Explicit shutdown and cost-control operations |
| Decision records | [adr/README.md](adr/README.md) | Architecture decisions and trade-off history |

Other docs should reference these pages instead of re-copying long command blocks.

## Execution-First Onboarding

Use `just` recipes for all daily work:

```bash
# 1) Verify host requirements and create local dump folders
just doctor

# 2) Start services and open API docs
just up
just migrate

# 3) Run tests (pick one)
just test-unit          # fast, no DB required
just test-integration   # requires PostgreSQL
just test-e2e           # full stack via Bruno

# 4) Signal development harness
just dev                # docker infra + live uvicorn
```

## Local Artifact Convention

Use `.local-dev/` for noisy local outputs you do not want in git:

- `.local-dev/dumps` for raw payload/input snapshots
- `.local-dev/responses` for API response captures
- `.local-dev/tracebacks` for failure dumps
- `.local-dev/logs` for verbose command logs
- `.local-dev/tmp` for temporary scratch output

This directory is gitignored and safe for iterative troubleshooting.

## Role-Based Reading Paths

- Fresh middle backend: Track A → Track B → Track C
- Senior backend: Track A → Track C → Track E
- DevOps: Track A (setup) → Track B → Track C
- Middle frontend: Track A → Track B (commands/env) → Track C (dashboard boundaries)
- Hiring/recruiting view: Track D

## Outdated Planning Notes

Legacy short-term planning notes were removed from active docs navigation.
Use [personal/README.md](personal/README.md) and [personal/roadmap.md](personal/roadmap.md) for current context.
