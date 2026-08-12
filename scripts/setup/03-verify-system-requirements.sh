#!/usr/bin/env bash

set -o errexit -o pipefail -o nounset -o errtrace

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly PROJECT_ROOT
readonly PYTHON_VERSION_FILE="${PROJECT_ROOT}/.python-version"

FAILED=0

info() {
    printf '[INFO] %s\n' "$*" >&2
}

success() {
    printf '[OK] %s\n' "$*" >&2
}

failure() {
    printf '[MISSING] %s\n' "$*" >&2
    ((++FAILED))
}

trap_error() {
    local line_number="$1"
    printf '[ERROR] doctor failed at line %s\n' "${line_number}" >&2
    exit 1
}

trap 'trap_error ${LINENO}' ERR

check_command() {
    local label="$1"
    local command_name="$2"

    if command -v "${command_name}" >/dev/null 2>&1; then
        success "${label}: $(command -v "${command_name}")"
        return 0
    fi

    failure "${label} not found"
    return 1
}

check_docker() {
    if ! check_command 'Docker' docker; then
        failure 'Docker Compose v2 unavailable because Docker is not installed'
        return
    fi

    if docker info >/dev/null 2>&1; then
        success 'Docker daemon is running'
    else
        failure 'Docker daemon is not running (start Docker and rerun just doctor)'
    fi

    if docker compose version >/dev/null 2>&1; then
        success 'Docker Compose v2 is available'
    else
        failure 'Docker Compose v2 is not available'
    fi
}

check_uv_python() {
    local python_path
    local required_python_version

    if ! check_command 'uv' uv; then
        failure 'Python selected by uv is unavailable'
        return
    fi
    if [[ ! -r "${PYTHON_VERSION_FILE}" ]]; then
        failure "Python version selector is missing: ${PYTHON_VERSION_FILE}"
        return
    fi

    required_python_version="$(<"${PYTHON_VERSION_FILE}")"
    if ! python_path="$(uv python find "${required_python_version}" 2>/dev/null)"; then
        failure "Python ${required_python_version} selected by uv is unavailable (run: uv python install ${required_python_version})"
        return
    fi
    success "Python selected by uv: $("${python_path}" --version 2>&1)"
}

main() {
    info 'Checking core local prerequisites'
    check_docker
    check_uv_python
    check_command Just just || true
    check_command Git git || true
    check_command curl curl || true

    if ((FAILED > 0)); then
        printf '[ERROR] %s required prerequisite(s) failed\n' "${FAILED}" >&2
        exit 1
    fi

    success 'Core local prerequisites are ready'
    printf '%s\n' 'Next: cp .env.example .env → just generate-secrets → just dev-up → just db-migrate → just test-smoke'
}

main "$@"
