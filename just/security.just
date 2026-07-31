# Security and image-quality checks. These are manual/CI assurance commands,
# not part of the core local onboarding flow.

sec-trivy-image image="api-observatory:local":
    docker compose --profile security run --rm trivy image \
        --scanners vuln --severity CRITICAL --ignore-unfixed --timeout 15m \
        --exit-code 1 {{image}}
    echo "No CRITICAL CVEs detected"

sec-gitleaks scope="repo":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ scope }}" = "staged" ]; then
        echo "=== Gitleaks: scanning staged changes (via pre-commit) ==="
        uv run pre-commit run gitleaks
    elif [ "{{ scope }}" = "repo" ]; then
        echo "=== Gitleaks: scanning full repo (Docker) ==="
        docker compose --profile security run --rm gitleaks detect --verbose --config /repo/.gitleaks.toml
    else
        echo "Usage: just sec-gitleaks [repo|staged]" >&2
        exit 1
    fi

sec-pip-audit:
    uv run python scripts/ci/pip_audit_wrapper.py

sec-hadolint target="/repo/Dockerfile /repo/services/dashboard/Dockerfile /repo/infra/database/Dockerfile":
    docker compose --profile security run --rm hadolint {{target}}

sec-checkov:
    docker compose --profile security run --rm checkov --directory /repo/infra/ --compact --soft-fail
