---
name: bash-standards
description: "Apply to: shell scripts (scripts/**/*.sh, bin/**/*.sh). Enforces defensive programming, error handling, and best practices for maintainable infrastructure scripts."
applyTo: "scripts/**/*.sh, bin/**/*.sh, **/*.sh"
---

# Bash Code Standards

## Script Header & Shebang

Always start with a shebang and include metadata:
```bash
#!/bin/bash

################################################################################
# Script: start.sh
# Description: Spin up Docker Compose services
# Usage: ./start.sh [--build]
# Author: data-pipeline-async
################################################################################

set -o errexit      # Exit on error
set -o pipefail     # Exit on pipe failure
set -o nounset      # Exit on undefined variable
set -o errtrace     # Inherit ERR trap

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
```

### Strict Mode Options
| Option | Effect |
|--------|--------|
| `-e` / `errexit` | Exit if any command fails |
| `-u` / `nounset` | Exit if variable is undefined |
| `-o pipefail` | Fail if any command in a pipe fails |
| `-o errtrace` | Inherit ERR trap in functions |

---

## Functions & Error Handling

### Function Template
```bash
# Print an info message
info() {
  echo "[ℹ️  INFO] $*" >&2
}

# Print a success message
success() {
  echo "[✓ SUCCESS] $*" >&2
}

# Print a warning message
warn() {
  echo "[⚠️  WARNING] $*" >&2
}

# Print an error message and exit
error() {
  echo "[❌ ERROR] $*" >&2
  exit 1
}

# Check if command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Require command to exist
require_command() {
  command_exists "$1" || error "Required command not found: $1"
}

# Error handler (called on ERR trap)
trap_error() {
  local line_no=$1
  error "Script failed at line ${line_no}"
}

trap 'trap_error ${LINENO}' ERR
```

### Usage Example
```bash
#!/bin/bash
set -o errexit -o pipefail -o nounset -o errtrace

# ... function definitions ...

info "Starting services..."
require_command docker
require_command docker-compose

if ! command_exists k6; then
  warn "k6 not found; load testing will be unavailable"
fi

# Main script logic
main() {
  info "Building Docker images..."
  docker-compose -f "${PROJECT_ROOT}/infra/docker-compose.yml" build

  info "Starting services..."
  docker-compose -f "${PROJECT_ROOT}/infra/docker-compose.yml" up -d

  success "Services started successfully!"
  info "Web API: http://localhost:8000"
}

main "$@"
```

---

## Variables & Quoting

### Variable Best Practices
```bash
# Good: quote all variables
readonly DB_HOST="localhost"
readonly DB_PORT="5432"
user_input="$1"  # Quoted!

# Use ${} syntax for clarity
path="${PROJECT_ROOT}/data"
echo "Connecting to ${DB_HOST}:${DB_PORT}"

# Bad: unquoted variables (expands glob, splits on whitespace)
echo $user_input  # Dangerous!
cp $file /backup  # Could break if filename has spaces
```

### Configuration from .env
```bash
# Load environment variables from .env file
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a  # Auto-export variables
  # shellcheck source=/dev/null
  source "${PROJECT_ROOT}/.env"
  set +a
else
  error "Missing .env file at ${PROJECT_ROOT}/.env"
fi

# Use with defaults
DB_PASS="${DATABASE_PASSWORD:-default_password}"
API_PORT="${API_PORT:-8000}"
```

---

## Common Patterns

### Check Docker & Docker Compose
```bash
# Ensure Docker is running
docker info >/dev/null 2>&1 || error "Docker daemon is not running"

# Docker Compose version compat (v1 vs v2)
if command_exists docker-compose; then
  DOCKER_COMPOSE="docker-compose"
elif docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker compose"
else
  error "Docker Compose not found"
fi

info "Using: ${DOCKER_COMPOSE}"
```

### Wait for Service Health
```bash
# Wait for PostgreSQL to be ready
wait_for_postgres() {
  local max_attempts=30
  local attempt=0

  while (( attempt < max_attempts )); do
    if docker exec postgres_db pg_isready -U user >/dev/null 2>&1; then
      success "PostgreSQL is ready"
      return 0
    fi
    warn "PostgreSQL not ready, waiting... (${attempt}/${max_attempts})"
    sleep 1
    ((attempt++))
  done

  error "PostgreSQL failed to start after ${max_attempts} attempts"
}

wait_for_postgres
```

### Cleanup & Exit Handlers
```bash
# Cleanup function (called on EXIT)
cleanup() {
  info "Cleaning up..."
  docker-compose down --volumes || warn "Failed to stop services"
}

trap cleanup EXIT

# Main script logic
main() {
  info "Starting services..."
  docker-compose up -d

  # Cleanup and exit will run automatically
}

main "$@"
```

---

## Logging & Colors

### Color Output for Readability
```bash
# ANSI color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'  # No Color

info() {
  echo -e "${BLUE}[ℹ️  INFO]${NC} $*" >&2
}

success() {
  echo -e "${GREEN}[✓]${NC} $*" >&2
}

warn() {
  echo -e "${YELLOW}[⚠️ ]${NC} $*" >&2
}

error() {
  echo -e "${RED}[❌]${NC} $*" >&2
  exit 1
}
```

### Verbose Mode
```bash
# Enable with -v flag: sh script.sh -v
VERBOSE_MODE=false

debug() {
  if [[ "${VERBOSE_MODE}" == "true" ]]; then
    echo "[DEBUG] $*" >&2
  fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -v | --verbose)
      VERBOSE_MODE=true
      shift
      ;;
    *)
      error "Unknown option: $1"
      ;;
  esac
done
```

---

## Script Organization

### Directory Structure
```
scripts/
  ├── start.sh         # Bring up services
  ├── test.sh          # Run tests
  ├── load_test.sh     # Run k6 load test
  ├── cleanup.sh       # Tear down services
  ├── lib/
  │   ├── common.sh    # Shared functions
  │   └── docker.sh    # Docker utilities
  └── README.md        # Script documentation
```

### Shared Functions (lib/common.sh)
```bash
#!/bin/bash

# Shared utilities used by multiple scripts
# Source this file: source "${SCRIPT_DIR}/lib/common.sh"

require_command() {
  command -v "$1" >/dev/null 2>&1 || error "Required: $1"
}

info() {
  echo "[INFO] $*" >&2
}

error() {
  echo "[ERROR] $*" >&2
  exit 1
}

success() {
  echo "[SUCCESS] $*" >&2
}
```

### Using Shared Functions
```bash
#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

require_command docker
info "Starting services..."
```

---

## Testing Scripts

### Simple Testing Example
```bash
#!/bin/bash

# tests/integration.sh

set -o errexit

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

test_api_response() {
  local response
  response=$(curl -s http://localhost:8000/health)

  if echo "${response}" | grep -q '"status":"healthy"'; then
    echo "✓ Health check passed"
  else
    echo "✗ Health check failed"
    return 1
  fi
}

test_db_connection() {
  if docker exec postgres_db pg_isready -U user; then
    echo "✓ Database is healthy"
  else
    echo "✗ Database failed"
    return 1
  fi
}

# Run tests
test_db_connection
test_api_response
echo "All tests passed!"
```

---

## Common Pitfalls

- **Unquoted variables**: Always use `"${var}"` to prevent word splitting.
- **Missing error handling**: Use `set -e` and error traps.
- **Hardcoded paths**: Use variables (`SCRIPT_DIR`, `PROJECT_ROOT`).
- **No logging**: Use info, warn, error functions for clarity.
- **Not checking command existence**: Always `require_command` before using external tools.
- **Ignoring exit codes**: Always check `if command; then`—don't assume success.

---

## Useful Tools & Resources

### ShellCheck (Linting)
Catch common bash errors:
```bash
# Install
brew install shellcheck  # macOS
apt install shellcheck   # Linux

# Run on all scripts
shellcheck scripts/**/*.sh
```

### Sample .github/workflows/ci.yml
```yaml
name: Quality Checks

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: apt-get install -y shellcheck
      - run: shellcheck scripts/**/*.sh
```
