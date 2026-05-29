# Project Overview

Track: A - Product and Onboarding

Start here for project scope, learning goals, and the fastest path through the documentation.

## What This Repository Is

Data Zoo is an async Python data-platform project focused on production-style backend engineering:

- event ingestion and processing
- reliability and observability patterns
- secure-by-default delivery workflows
- deployment and operations runbooks

It is designed as both a working system and a learning portfolio.

## Core Outcomes

- Learn by building with realistic architecture constraints.
- Practice production engineering patterns end to end.
- Keep decisions explicit through ADRs and design docs.
- Preserve reproducible workflows through scripts and canonical command references.

## Documentation Navigation

The canonical index for all tracks is:

- [docs/README.md](README.md)

Use this reading order for most contributors:

1. [docs/01-system-setup.md](01-system-setup.md)
2. [docs/02-first-time-setup.md](02-first-time-setup.md)
3. [docs/03-daily-development.md](03-daily-development.md)
4. [docs/dev/commands.md](dev/commands.md)
5. [docs/04-architecture-overview.md](04-architecture-overview.md)

Terminology used across Track A docs:

- Workflow intent and sequence: [docs/03-daily-development.md](03-daily-development.md)
- Canonical command source: [docs/dev/commands.md](dev/commands.md)

## Hiring and Interview Fast Path

For portfolio and interview review:

1. [docs/personal/CV.md](personal/CV.md)
2. [docs/04-architecture-overview.md](04-architecture-overview.md)
3. [docs/09-backend-concepts-and-patterns.md](09-backend-concepts-and-patterns.md)
4. [docs/personal/10-interview-prep-middle-plus.md](personal/10-interview-prep-middle-plus.md)

## Evidence Map

- Architecture and boundaries: [docs/04-architecture-overview.md](04-architecture-overview.md), [docs/design/decisions.md](design/decisions.md)
- Data and SQL reasoning: [docs/09-backend-concepts-and-patterns.md](09-backend-concepts-and-patterns.md), [docs/design/phase-5-advanced-sql-cqrs.md](design/phase-5-advanced-sql-cqrs.md)
- Reliability patterns: [docs/04-architecture-overview.md](04-architecture-overview.md), [docs/personal/portfolio-phase-4-resilience.md](personal/portfolio-phase-4-resilience.md)
- Security posture: [docs/design/pillar-5-security.md](design/pillar-5-security.md), [docs/04-architecture-overview.md](04-architecture-overview.md)
- Delivery and operations: [docs/dev/commands.md](dev/commands.md), [docs/cloud-deployment.md](cloud-deployment.md), [docs/deployment/aws-ecs.md](deployment/aws-ecs.md)

## Current Status

Current prioritized roadmap:

- [docs/personal/roadmap.md](personal/roadmap.md)

## Quick Start

For execution-first onboarding:

1. run just doctor
2. run bootstrap from [docs/02-first-time-setup.md](02-first-time-setup.md)
3. use workflow intent and sequence from [docs/03-daily-development.md](03-daily-development.md)
4. use exact commands from the canonical command source: [docs/dev/commands.md](dev/commands.md)

## Project Principles

- Keep command details centralized; avoid duplicating long command blocks.
- Keep strategy and runbooks separate.
- Keep local artifacts in .local-dev and out of git.
- Prefer explicit links to canonical docs instead of restating procedures.

## Related Top-Level Docs

- [docs/README.md](README.md)
- [docs/01-system-setup.md](01-system-setup.md)
- [docs/02-first-time-setup.md](02-first-time-setup.md)
- [docs/03-daily-development.md](03-daily-development.md)
- [docs/cloud-deployment.md](cloud-deployment.md)
