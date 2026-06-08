#!/usr/bin/env bash
set -euo pipefail

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
    if command -v docker-compose &>/dev/null; then
        echo -e "${GREEN}✓${NC} docker-compose (v1)"
        return 0
    elif docker compose version &>/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} docker compose (v2 - bundled with Docker)"
        return 0
    else
        echo -e "${RED}✗${NC} docker-compose ${RED}NOT FOUND${NC} (install: docker-compose)"
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
    # Check if python3.14 is available
    if command -v python3.14 &>/dev/null; then
        local version
        version=$(python3.14 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        echo -e "${GREEN}✓${NC} python3.14 (${version})"
        return 0
    fi

    # Fallback: check default python3
    if command -v python3 &>/dev/null; then
        local version
        version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        if awk 'BEGIN{exit !($version >= 3.14)}'; then
            echo -e "${GREEN}✓${NC} python3 (${version})"
            return 0
        else
            echo -e "${YELLOW}⚠${NC} python3 VERSION ${version} (uv can use system Python to bootstrap; 3.14+ needed for app)"
            return 0
        fi
    fi

    echo -e "${RED}✗${NC} python3 ${RED}NOT FOUND${NC} (install: python3.14)"
    return 1
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
check_docker_compose || ((FAILED++))
check_python_version || ((FAILED++))
check_command "uv" "uv" || ((FAILED++))
check_command "curl" "curl" || ((FAILED++))

echo ""
echo "Floci / Terraform (optional)"
# Terraform CLI — required when using the local Floci Terraform stacks
check_command_warning "terraform" "terraform (install: https://www.terraform.io/downloads) - required for Floci/infra/terraform" || true
# tflocal — helper wrapper commonly installed via `uv tool install terraform-local`
check_command_warning "tflocal" "tflocal (install: uv tool install terraform-local) - wrapper for local Terraform/Floci workflows" || true

echo ""
echo "Database Backup/Restore:"
check_command "pg_dump" "postgresql" || ((FAILED++))
check_command "pg_restore" "postgresql" || ((FAILED++))
check_command "psql" "postgresql" || ((FAILED++))
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

if command -v docker-compose &>/dev/null; then
    echo "Docker Compose:  $(docker-compose --version)"
elif docker compose version &>/dev/null 2>&1; then
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
    echo "  2. just up"
    echo "  3. uv run pytest tests/ -v"
    echo "  4. bash infra/scripts/backup.sh"
    exit 0
else
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}✗ ${FAILED} required package(s) missing. See docs/setup/system-requirements.md${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════${NC}"
    exit 1
fi
