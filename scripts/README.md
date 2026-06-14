# Scripts — Overview

Purpose: Central location for operational, CI, and setup scripts organized by purpose.

Subdirectory guide:
- `setup/` — First-time environment bootstrap (ordered by execution sequence)
- `daily/` — Daily developer operations (health checks, logs, local URL helpers)
- `ci/` — CI guardrails and automation (service boundary checks, dependency audits, security scans)
- `testing/` — Test execution helpers and test data
- `eval/` — Evaluation and benchmarking
- `load/` — Load testing and k6 scenarios
- `ops/` — Production operations (backup, restore, migrations)
- `sandbox/` — Local sandbox environment setup (Floci, K3d)
- `tools/` — Utility scripts (git helpers, version bumping)
- `docs/` — Documentation generation

Execution order for setup (example):
```bash
00-doctor.sh          # System health check (always first)
  → 02-setup-local-https.sh  # HTTPS certificates (required for TLS testing)
  → 03-bootstrap-k3d.sh      # Local Kubernetes sandbox (optional for Stage 3+)
```

Common patterns:
- All scripts start with `#!/bin/bash` + `set -o errexit -o pipefail -o nounset`.
- Shared helpers in `scripts/daily/` are sourced by parent scripts.
- Local environment stored in `.env.local` (never commit).

Entry points by use case:
- First-time setup: `just doctor && scripts/setup/00-doctor.sh`
- Daily development: `just up` (uses `docker-compose.yml`)
- Load testing: `scripts/load/01-test-with-postgres.sh` or `k6 run scripts/load/k6-scenarios.js`
- CI simulation: run `.github/workflows/ci.yml` jobs locally using `act`

ASCII dependency sketch (quick reference):

```text
setup/00-doctor.sh
  ├─ depends on: system commands (docker, git, etc.)
  └─ called by: just doctor, CI pre-flight checks

setup/02-setup-local-https.sh
  ├─ depends on: mkcert (installed by 00-doctor)
  └─ called by: setup sequence, local dev loop

scripts/daily/local-url.sh
  ├─ utility: returns local service URL
  └─ sourced by: smoke-test.sh, health checks

scripts/ci/check_service_boundaries.py
  ├─ enforces: lib imports only from specific paths
  └─ called by: CI lint lane (ci.yml)

scripts/load/k6-scenarios.js
  ├─ depends on: k6 (optional install)
  └─ triggered by: just deploy-audit, manual benchmarking
```
