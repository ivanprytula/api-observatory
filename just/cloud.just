# Disposable cloud-emulator labs. Run through `just --justfile just/labs.just`.
# These commands manage only the selected emulator; they never start the application,
# run migrations, seed data, launch host processes, or access real cloud accounts.

# Start one provider emulator and wait for its Compose healthcheck.
lab-cloud-up provider:
    #!/usr/bin/env bash
    set -euo pipefail
    provider="{{ provider }}"
    case "${provider}" in
        azure) service="floci-az" ;;
        aws) service="floci-aws" ;;
        gcp) service="floci-gcp" ;;
        *)
            printf 'Unknown cloud emulator: %s. Use azure, aws, or gcp.\n' "${provider}" >&2
            exit 2
            ;;
    esac
    docker compose --profile "${provider}" up --detach --no-deps --wait \
        --wait-timeout "${CLOUD_EMULATOR_WAIT_TIMEOUT_SECONDS:-60}" "${service}"
    printf '%s emulator ready.\n' "${provider}"

# Stop and remove one provider emulator without affecting the application stack.
lab-cloud-down provider:
    #!/usr/bin/env bash
    set -euo pipefail
    provider="{{ provider }}"
    case "${provider}" in
        azure) service="floci-az" ;;
        aws) service="floci-aws" ;;
        gcp) service="floci-gcp" ;;
        *)
            printf 'Unknown cloud emulator: %s. Use azure, aws, or gcp.\n' "${provider}" >&2
            exit 2
            ;;
    esac
    docker compose --profile "${provider}" rm --stop --force "${service}"
    printf '%s emulator stopped.\n' "${provider}"

# Check the selected emulator's HTTP health endpoint.
lab-cloud-verify provider:
    #!/usr/bin/env bash
    set -euo pipefail
    provider="{{ provider }}"
    case "${provider}" in
        azure) endpoint="http://127.0.0.1:4577" ;;
        aws) endpoint="http://127.0.0.1:4566" ;;
        gcp) endpoint="http://127.0.0.1:4588" ;;
        *)
            printf 'Unknown cloud emulator: %s. Use azure, aws, or gcp.\n' "${provider}" >&2
            exit 2
            ;;
    esac
    curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
        "${endpoint}/health" >/dev/null
    printf '%s emulator healthy: %s\n' "${provider}" "${endpoint}"

# Exercise Blob Storage against a running local Azure emulator.
lab-cloud-test-azure:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_ROOT="$(git -C "{{ justfile_directory() }}" rev-parse --show-toplevel)"
    if ! curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
        http://127.0.0.1:4577/health >/dev/null; then
        printf 'Azure emulator is unavailable. Start it with: just --justfile just/labs.just lab-cloud-up azure\n' >&2
        exit 1
    fi
    cd "${PROJECT_ROOT}" && \
        env -u AZURE_ENDPOINT_URL -u AZURE_STORAGE_CONNECTION_STRING \
            uv run pytest tests/e2e/test_floci_integration.py -v -m azure --no-cov
