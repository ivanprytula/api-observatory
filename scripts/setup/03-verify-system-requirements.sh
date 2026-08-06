#!/usr/bin/env bash

################################################################################
# Script: 03-verify-system-requirements.sh
# Description: Verify required local tools for API Observatory development.
################################################################################

set -o errexit -o pipefail -o nounset -o errtrace

# ─── Configuration ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REQUIRED_PYTHON_VERSION="$(<"${PROJECT_ROOT}/.python-version")"

# Workstation baselines. These are minimum CLI versions, not dependency
# versions; keep them conservative so Ubuntu 22.04/macOS installations remain
# supported while still covering the commands used by this repository.
MIN_DOCKER_VERSION="20.10.0"
MIN_COMPOSE_VERSION="2.20.0"
MIN_UV_VERSION="0.4.0"
MIN_JUST_VERSION="1.0.0"
MIN_GIT_VERSION="2.30.0"
MIN_CURL_VERSION="7.81.0"
MIN_POSTGRES_TOOLS_VERSION="15.0"
MIN_MONGO_TOOLS_VERSION="100.8.0"

# ─── Helper functions ─────────────────────────────────────────────────────────
check_command() {
    if command -v "$1" &>/dev/null; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 ${RED}NOT FOUND${NC} (install: $2)"
        return 1
    fi
}

extract_version() {
    sed -nE 's/[^0-9]*([0-9]+(\.[0-9]+){1,3}).*/\1/p' | head -n1
}

version_at_least() {
    local actual="$1"
    local minimum="$2"
    local actual_part minimum_part
    local -a actual_parts minimum_parts
    IFS='.' read -r -a actual_parts <<< "${actual}"
    IFS='.' read -r -a minimum_parts <<< "${minimum}"
    for ((index = 0; index < ${#minimum_parts[@]}; index++)); do
        actual_part="${actual_parts[index]:-0}"
        minimum_part="${minimum_parts[index]:-0}"
        if ((10#${actual_part} > 10#${minimum_part})); then
            return 0
        fi
        if ((10#${actual_part} < 10#${minimum_part})); then
            return 1
        fi
    done
    return 0
}

check_version() {
    local label="$1"
    local minimum="$2"
    local raw="$3"
    local actual
    actual="$(printf '%s\n' "${raw}" | extract_version)"
    if [[ -z "${actual}" ]]; then
        echo -e "${RED}✗${NC} ${label} version could not be parsed from: ${raw}"
        return 1
    fi
    if ! version_at_least "${actual}" "${minimum}"; then
        echo -e "${RED}✗${NC} ${label} ${actual}; requires >= ${minimum}"
        return 1
    fi
    echo -e "${GREEN}✓${NC} ${label} ${actual} (>= ${minimum})"
}

check_optional_version() {
    local command_name="$1"
    local minimum="$2"
    local raw
    if ! command -v "${command_name}" &>/dev/null; then
        echo -e "${YELLOW}⚠${NC} ${command_name} not found (optional: install the matching client tools)"
        return 0
    fi
    raw="$(${command_name} --version 2>&1 | head -n1)"
    check_version "${command_name}" "${minimum}" "${raw}" || true
}

check_docker_compose() {
    local raw
    if ! raw="$(docker compose version 2>&1)"; then
        echo -e "${RED}✗${NC} Docker Compose v2 ${RED}NOT FOUND${NC} (install Docker Engine/Desktop with Compose v2)"
        return 1
    fi
    check_version "Docker Compose" "${MIN_COMPOSE_VERSION}" "${raw}"
}

check_command_warning() {
    if command -v "$1" &>/dev/null; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} $1 not found (optional: $2)"
        return 1
    fi
}

check_python_version() {
    local python_bin=""
    if command -v uv &>/dev/null \
        && uv python find "${REQUIRED_PYTHON_VERSION}" >/dev/null 2>&1; then
        python_bin="$(uv python find "${REQUIRED_PYTHON_VERSION}")"
    elif command -v python3.14 &>/dev/null; then
        python_bin="python3.14"
    elif command -v python3 &>/dev/null; then
        python_bin="python3"
    fi
    if [[ -z "${python_bin}" ]]; then
        echo -e "${RED}✗${NC} Python ${REQUIRED_PYTHON_VERSION} ${RED}NOT FOUND${NC}"
        return 1
    fi
    local version
    version="$(${python_bin} -c 'import platform; print(platform.python_version())')"
    # .python-version selects a supported minor series (for example, 3.14),
    # while the interpreter reports its installed patch version (for example,
    # 3.14.6). Compare the same major.minor value instead of requiring an
    # exact patch-level match.
    local version_series="${version%.*}"
    if [[ "${version_series}" != "${REQUIRED_PYTHON_VERSION}" ]]; then
        echo -e "${RED}✗${NC} Python ${version}; .python-version requires ${REQUIRED_PYTHON_VERSION}.x"
        return 1
    fi
    echo -e "${GREEN}✓${NC} Python ${version}"
}

# ─── Main ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "System Requirements Verification"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

FAILED=0

echo "Core Development Tools:"
if command -v docker &>/dev/null; then
    check_version "Docker" "${MIN_DOCKER_VERSION}" "$(docker --version 2>&1)" || ((++FAILED))
else
    echo -e "${RED}✗${NC} docker NOT FOUND (install docker)"
    ((++FAILED))
fi
if command -v docker &>/dev/null && ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker daemon is not running (start Docker, then rerun just doctor)"
    ((++FAILED))
fi
check_docker_compose || ((++FAILED))
check_python_version || ((++FAILED))
if command -v uv &>/dev/null; then
    check_version "uv" "${MIN_UV_VERSION}" "$(uv --version 2>&1)" || ((++FAILED))
else
    echo -e "${RED}✗${NC} uv NOT FOUND (install uv)"
    ((++FAILED))
fi
if command -v just &>/dev/null; then
    check_version "just" "${MIN_JUST_VERSION}" "$(just --version 2>&1)" || ((++FAILED))
else
    echo -e "${RED}✗${NC} just NOT FOUND (install just)"
    ((++FAILED))
fi
if command -v git &>/dev/null; then
    check_version "git" "${MIN_GIT_VERSION}" "$(git --version 2>&1)" || ((++FAILED))
else
    echo -e "${RED}✗${NC} git NOT FOUND (install git)"
    ((++FAILED))
fi
if command -v curl &>/dev/null; then
    check_version "curl" "${MIN_CURL_VERSION}" "$(curl --version 2>&1 | head -n1)" || ((++FAILED))
else
    echo -e "${RED}✗${NC} curl NOT FOUND (install curl)"
    ((++FAILED))
fi

echo ""
echo "Cloud / Infrastructure as Code (Optional):"
check_command_warning "terraform" "terraform (install: https://www.terraform.io/downloads)" || true

echo ""
echo "Database Backup/Restore (Optional):"
check_optional_version "pg_dump" "${MIN_POSTGRES_TOOLS_VERSION}"
check_optional_version "pg_restore" "${MIN_POSTGRES_TOOLS_VERSION}"
check_optional_version "psql" "${MIN_POSTGRES_TOOLS_VERSION}"
check_optional_version "mongodump" "${MIN_MONGO_TOOLS_VERSION}"
check_optional_version "mongorestore" "${MIN_MONGO_TOOLS_VERSION}"

echo ""
echo "Chaos Testing (Optional but recommended):"
check_command_warning "nsenter" "util-linux" || true
check_command_warning "tc" "iproute2" || true

echo ""
echo "Documentation / Diagramming:"
check_command_warning "dot" "graphviz (install: apt install graphviz / brew install graphviz) - rendering engine for Terravision architecture diagrams" || true

echo ""
echo "Optional Diagnostics:"
check_command_warning "jq" "jq" || true
check_command_warning "htop" "htop" || true

echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo "Version Information:"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

if command -v python3 &>/dev/null; then
    echo "System Python:    $(python3 --version)"
fi

if command -v uv &>/dev/null; then
    echo "uv:              $(uv --version)"
fi

if command -v docker &>/dev/null; then
    echo "Docker:          $(docker --version)"
fi

if docker compose version &>/dev/null 2>&1; then
    echo "Docker Compose:  $(docker compose version)"
fi

if command -v pg_dump &>/dev/null; then
    echo "PostgreSQL:      $(pg_dump --version)"
fi

if command -v dot &>/dev/null; then
    echo "Graphviz:        $(dot -V 2>&1 | head -n1)"
fi

echo ""

if [[ "${FAILED}" -eq 0 ]]; then
    echo -e "${GREEN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ All required packages installed! Ready for development.${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. cp .env.example .env"
    echo "  2. just generate-secrets"
    echo "  3. just dev-up"
    echo "  4. just dev-wait-ready"
    echo "  5. just db-migrate"
    echo "  6. just test-smoke"
    exit 0
else
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}✗ ${FAILED} required package(s) missing. See docs/04-setup/setup-guide.md${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════${NC}"
    exit 1
fi
