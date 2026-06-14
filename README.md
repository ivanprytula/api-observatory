# api-observatory

Async FastAPI service for API reliability monitoring, contract drift detection, scorecard reporting, and LangGraph-powered observation enrichment.

**MVP status**: Commits 1-12 complete. All core features shippable.

## Quick Start

```bash
cp .env.example .env
just up       # db, cache, broker, ingestor
just migrate
```

API docs: <http://localhost:8000/docs>

Full setup sequence: [docs/02-first-time-setup.md](docs/02-first-time-setup.md)
All commands: [docs/dev/commands.md](docs/dev/commands.md)

## Stack

| Service | Port | Role |
|---------|-----:|------|
| ingestor | 8000 | FastAPI — probes, scorecards, drift detection, agent enrichment |
| db | 5432 | PostgreSQL 17 — primary persistence, PERCENTILE_CONT scorecards, RLS |
| cache | 6379 | Cache (scorecard TTL), pub/sub (WebSocket fan-out), rate-limit backend |
| broker | 9092/8082 | Kafka-compatible broker — drift events, async processing, DLQ |

See [docs/04-architecture-overview.md](docs/04-architecture-overview.md) for the full flow diagram.

## Read Next

- [docs/README.md](docs/README.md) — Full docs index and track navigation
- [docs/user/overview.md](docs/user/overview.md) — User-facing guide (purpose, functionality)
- [docs/dev/commands.md](docs/dev/commands.md) — All CLI commands
- [docs/04-architecture-overview.md](docs/04-architecture-overview.md) — Visual flow diagram
- [docs/tech-map.md](docs/tech-map.md) — Interview topic → exact file:function map
- [docs/deployment/aws-ecs.md](docs/deployment/aws-ecs.md) — ECS deployment sequence

Local Review for uncommitted changes
Summary
The uncommitted changes mostly standardize Floci/Terraform recipe naming and add a Justfile reference guard. The high-risk issues are deploy-safety gaps in the new CD/manual deploy path: Terraform apply is automatic, docs can double-apply, smoke checks can be skipped, and rollout waits are serialized.

Issues Found
Severity File:Line Issue
WARNING .github/workflows/cd-dev.yml:15 CD deploy can be canceled mid-run, including during Terraform apply or ECS rollout.
WARNING .github/workflows/cd-dev.yml:78 Automated dev Terraform apply runs without a reviewed saved plan.
WARNING .github/workflows/cd-dev.yml:145 CD can mark deploy successful with smoke tests skipped when ALB DNS is unavailable.
WARNING .github/workflows/release.yml:97 Mutable v1 image tag weakens release provenance.
WARNING docs/deployment/deploy-runbook.md:141 Manual deploy docs can double-apply or apply a stale plan before just deploy-ecs.
WARNING docs/deployment/aws-ecs.md:105 AWS rollout docs show the same plan → apply → deploy-ecs conflict.
SUGGESTION .github/workflows/cd-dev.yml:113 ECS stability waits for ingestor and dashboard run sequentially even though services are independent.
Detailed Findings
File: .github/workflows/cd-dev.yml:15
Confidence: 95%
Problem: cancel-in-progress: true can interrupt an in-flight Terraform apply or ECS rollout, leaving infrastructure or services in a partially updated state.
Suggestion: Use cancel-in-progress: false for deploy workflows, or split Terraform and rollout into separate concurrency groups with careful cancellation rules.
File: .github/workflows/cd-dev.yml:78
Confidence: 95%
Problem: The workflow applies Terraform directly with -auto-approve; it does not require a reviewed saved plan or manual approval gate before mutating dev infrastructure.
Suggestion: Generate a plan artifact in CI, require review/approval before apply, or apply a saved plan from a prior checked step.
File: .github/workflows/cd-dev.yml:145
Confidence: 95%
Problem: If neither DEV_ALB_DNS nor Terraform ALB output is available, smoke tests exit 0, so an ECS rollout can be reported successful without endpoint verification.
Suggestion: Fail closed when ALB DNS is unavailable, or make smoke-test skipping explicit and visible in the summary as “deployed unverified.”
File: .github/workflows/release.yml:97
Confidence: 95%
Problem: Pushing a mutable v1 tag weakens rollback provenance because the tag can be retargeted later.
Suggestion: Remove the v1 tag push and rely on immutable release tags, tree SHA tags, or image digests.
File: docs/deployment/deploy-runbook.md:141
Confidence: 95%
Problem: The manual sequence runs TF_ENV=dev just tf apply, then just deploy-ecs; deploy-ecs also applies via infra-dev, so operators can double-apply or apply a stale plan.
Suggestion: Document TF_ENV=dev just tf plan followed directly by just deploy-ecs, or change deploy-ecs to only perform ECS updates after Terraform apply.
File: docs/deployment/aws-ecs.md:105
Confidence: 95%
Problem: The AWS rollout docs repeat the same conflicting sequence: plan, apply, then just deploy-ecs.
Suggestion: Align with deploy-ecs behavior by documenting TF_ENV=dev just tf plan then just deploy-ecs.
File: .github/workflows/cd-dev.yml:113
Confidence: 90%
Problem: Ingestor and dashboard stability waits are serialized, which can roughly double deploy stabilization time for independent services.
Suggestion: Start both ECS updates first, then wait for both services concurrently or in parallel jobs after the Terraform apply step.
Recommendation
NEEDS CHANGES — Fix the deploy-safety issues before merging, especially the CD apply path and manual deploy docs.
