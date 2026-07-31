# Repository scripts

Scripts are grouped by how they participate in the repository workflow.

## Maintained automation

- `ci/` — CI and pre-commit checks.
- `setup/` — local environment and system checks.
- `load/` — current k6 smoke and resilience workloads.
- `eval/` — deterministic, provider-free agent evaluation.
- `register_mcp_service_user.py` — local MCP service-user bootstrap.
- `run-retention.py` — bounded retention operation.
- `smoke-test.sh` — post-start HTTP smoke checks.
- `validate_release_manifest.py` — portable image-release manifest validation.
- `ci/smoke-deployable-images.sh` — CI wrapper for the disposable Compose build/readiness proof of the three Stage 0 images.
- `verify-resilience-fault.sh` — controlled local failure-injection verification.

## Manual development and learning tools

These are useful for focused local exercises but are not part of the default CI
path:

- `azure-env.sh` — Azure emulator/login environment helper.
- `bump_contracts_version.py` — manual contracts versioning helper.
- `daily/05-reset-test-db.sh` — manual testcontainers cleanup.
- `refresh-sandbox-claude.sh` — local Codex/Claude sandbox documentation refresh.
- `setup/03-bootstrap-k3d.sh` — optional Kubernetes lab bootstrap.
- `testing/04-gateway-smoke.sh` — local ingress smoke test.
- `testing/05-service-discovery-dns.sh` — Compose/DNS topology check.
- `testing/06-architecture-principles-guard.sh` — broader manual architecture guard.
- `testing/test_logging_formats.py` — logging-format demonstration.
- `tools/http-clients-demo.py` — resilience/client learning demonstration.
- `tools/set-branch-protection-gh.sh` — manually reviewed GitHub branch protection helper.
- `tools/apply-github-environment-protection.sh` — manually reviewed GitHub environment helper.

Account and GitHub mutation helpers remain manual by design and are not invoked
automatically by CI.
