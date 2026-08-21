#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly PROJECT_ROOT

cd "${PROJECT_ROOT}"

export DATABASE_URL_TEST="sqlite+aiosqlite:///:memory:"
export CACHE_ENABLED="false"

uv run pytest tests/unit services/ingestor/tests/unit -q -m unit
uv run pytest services/mcp/tests -q --no-cov
uv run pytest services/ingestor/tests/contract -q -m contract --no-cov
