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

check_docker_compose() {
    if docker compose version &>/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} docker compose (v2 - bundled with Docker)"
        return 0
    else
        echo -e "${RED}✗${NC} Docker Compose v2 ${RED}NOT FOUND${NC} (install Docker Engine/Desktop with Compose v2)"
        return 1
    fi
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
    if command -v python3.14 &>/dev/null; then
        python_bin="python3.14"
    elif command -v python3 &>/dev/null; then
        python_bin="python3"
    fi
    if [[ -z "${python_bin}" ]]; then
        echo -e "${RED}✗${NC} Python 3.14.6 ${RED}NOT FOUND${NC}"
        return 1
    fi
    local version
    version="$(${python_bin} -c 'import platform; print(platform.python_version())')"
    if [[ "${version}" != "3.14.6" ]]; then
        echo -e "${RED}✗${NC} Python ${version}; this project requires 3.14.6"
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
check_command "docker" "docker" || ((FAILED++))
if command -v docker &>/dev/null && ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker daemon is not running (start Docker, then rerun just doctor)"
    ((FAILED++))
fi
check_docker_compose || ((FAILED++))
check_python_version || ((FAILED++))
check_command "uv" "uv" || ((FAILED++))
check_command "just" "just" || ((FAILED++))
check_command "git" "git" || ((FAILED++))
check_command "curl" "curl" || ((FAILED++))

echo ""
echo "Cloud / Infrastructure as Code (Optional):"
check_command_warning "terraform" "terraform (install: https://www.terraform.io/downloads)" || true

echo ""
echo "Database Backup/Restore (Optional):"
check_command_warning "pg_dump" "postgresql client tools" || true
check_command_warning "pg_restore" "postgresql client tools" || true
check_command_warning "psql" "postgresql client tools" || true
check_command_warning "mongodump" "mongodb-tools" || true
check_command_warning "mongorestore" "mongodb-tools" || true

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
    echo "Python:          $(python3 --version)"
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
