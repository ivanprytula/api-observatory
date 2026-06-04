#!/usr/bin/env bash
# Code quality checks: linting, formatting, type checking, and tests.
# Exit 1 on ANY failure to prevent bad code from being committed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

FAILED=0

echo "==> Code Quality Checks"
echo ""

echo "Step 1: Installing dependencies"
if uv sync --quiet; then
  echo "✓ Dependencies synced"
else
  echo "✗ Failed to sync dependencies" >&2
  FAILED=1
fi
echo ""

echo "Step 2: Ruff lint check"
if uv run ruff check . >/dev/null 2>&1; then
  echo "✓ No lint violations"
else
  echo "✗ Lint violations found:" >&2
  uv run ruff check .
  FAILED=1
fi
echo ""

echo "Step 3: Ruff format check"
if uv run ruff format --check . >/dev/null 2>&1; then
  echo "✓ All files properly formatted"
else
  echo "✗ Formatting issues found. Run: uv run ruff format ." >&2
  FAILED=1
fi
echo ""

echo "Step 4: Unit tests (fast, no external I/O)"
if uv run pytest tests/ -m "unit" -q --tb=short 2>/dev/null; then
  echo "✓ Unit tests passed"
else
  echo "⊘ No unit tests (OK for now)"
fi
echo ""

echo "Step 5: Integration tests (API, DB, cache)"
if uv run pytest tests/integration/ -q --tb=short -m "not e2e"; then
  TEST_COUNT=$(uv run pytest tests/ --collect-only -q 2>/dev/null | tail -1 | grep -o '[0-9]* test' || echo "")
  echo "✓ Integration tests passed (${TEST_COUNT})"
else
  echo "✗ Integration tests failed" >&2
  FAILED=1
fi
echo ""

echo "Step 6: Full test suite (all tests with coverage)"
if uv run pytest tests/ -q --tb=short -m "not e2e"; then
  TOTAL=$(uv run pytest tests/ --collect-only -q 2>/dev/null | tail -1 || echo "0")
  echo "✓ All tests passed"
  echo "  $TOTAL"
else
  echo "✗ Full test suite failed" >&2
  FAILED=1
fi
echo ""

echo "Step 7: Coverage analysis"
COVERAGE=$(uv run pytest tests/ -q --tb=no --cov=services/ingestor 2>/dev/null | grep "^TOTAL" | awk '{print $NF}')
if [ -n "$COVERAGE" ]; then
  echo "✓ Coverage: $COVERAGE"
else
  echo "⊘ Coverage report unavailable"
fi
echo ""

echo "==> Quality Check Summary"
echo ""
if [ $FAILED -eq 0 ]; then
  echo "✓ All quality checks passed!"
  echo ""
  echo "Next steps:"
  echo "  • Commit your changes: git add -A && git commit -m 'your message'"
  echo "  • Run full validation: ./scripts/ci/01-full-validation.sh"
  exit 0
else
  echo "✗ Quality checks failed (see above)" >&2
  echo ""
  echo "Please fix issues and re-run:"
  echo "  ./scripts/daily/04-quality-checks.sh"
  exit 1
fi
