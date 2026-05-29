#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p .local-dev/dumps .local-dev/logs .local-dev/responses .local-dev/tracebacks .local-dev/tmp

bash scripts/setup/03-verify-system-requirements.sh

cat <<'EOF'

Local development artifact folders prepared:
  .local-dev/dumps
  .local-dev/logs
  .local-dev/responses
  .local-dev/tracebacks
  .local-dev/tmp

Use these paths for raw samples, verbose command output, API responses, and traceback captures.
EOF
