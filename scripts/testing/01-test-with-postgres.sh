#!/usr/bin/env bash
set -euo pipefail

echo "Running tests with auto-provisioned PostgreSQL (testcontainers)..."

if [ "$#" -gt 0 ]; then
    unset DATABASE_URL_TEST
    uv run pytest "$@"
else
    unset DATABASE_URL_TEST
    uv run pytest tests/integration/records/test_concurrency.py -v
fi
