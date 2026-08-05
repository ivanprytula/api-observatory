# Security and image-quality checks. These are manual/CI assurance commands,
# not part of the core local onboarding flow.

sec-trivy-image image="api-observatory:local":
    docker compose --profile security run --rm trivy image \
        --scanners vuln --severity CRITICAL --ignore-unfixed --timeout 15m \
        --exit-code 1 {{image}}
    echo "No CRITICAL CVEs detected"

sec-gitleaks-staged:
    uv run pre-commit run gitleaks

sec-gitleaks-repo:
    docker compose --profile security run --rm gitleaks detect --verbose --config /repo/.gitleaks.toml

sec-pip-audit:
    uv run python scripts/ci/pip_audit_wrapper.py

sec-hadolint:
    docker compose --profile security run --rm hadolint /repo/Dockerfile /repo/services/dashboard/Dockerfile /repo/infra/database/Dockerfile

sec-checkov:
    docker compose --profile security run --rm checkov --directory /repo/infra/ --compact --soft-fail
