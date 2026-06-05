#!/usr/bin/env bash
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

MODELS="services/ingestor/models.py"
MESSAGING="services/ingestor/repositories/messaging.py"
ALERT_RULES="infra/monitoring/rules/alert.rules.yml"

check() {
  echo "==> $1"
}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

command -v uv >/dev/null 2>&1 || fail "uv required"
command -v grep >/dev/null 2>&1 || fail "grep required"

[[ -f "$MODELS" ]] || fail "Missing: $MODELS"
[[ -f "$MESSAGING" ]] || fail "Missing: $MESSAGING"
[[ -f "$ALERT_RULES" ]] || fail "Missing: $ALERT_RULES"

[[ -s "libs/contracts/VERSION" ]] || fail "Missing or empty: libs/contracts/VERSION"
[[ -s "libs/contracts/CHANGELOG.md" ]] || fail "Missing or empty: libs/contracts/CHANGELOG.md"

check "Bounded-context boundary guard"
uv run python scripts/ci/check_service_boundaries.py

check "Idempotency primitives"
grep -q "idempotency_key" "$MODELS" || fail "idempotency_key not found in models"
grep -q "ix_events_idempotency_key" "$MODELS" || fail "idempotency index not found in models"

check "Outbox/Inbox baseline"
grep -q "class OutboxEvent" "$MODELS" || fail "OutboxEvent model not found"
grep -q "class InboxConsumption" "$MODELS" || fail "InboxConsumption model not found"
grep -q "try_record_inbox_consumption" "$MESSAGING" || fail "Inbox dedup helper not found"
grep -R -q "outbox_events" alembic/versions || fail "Outbox migration markers not found"
grep -R -q "inbox_consumptions" alembic/versions || fail "Inbox migration markers not found"

check "Resilience primitives"
[[ -f "libs/platform/retry.py" ]] || fail "Missing: libs/platform/retry.py"
[[ -f "libs/platform/circuit_breaker.py" ]] || fail "Missing: libs/platform/circuit_breaker.py"
[[ -f "libs/platform/bulkhead.py" ]] || fail "Missing: libs/platform/bulkhead.py"
grep -q "class RetryBudget" "libs/platform/retry.py" || fail "RetryBudget primitive not found"
grep -q "class AsyncBulkhead" "libs/platform/bulkhead.py" || fail "AsyncBulkhead primitive not found"

check "SLO alert guardrails"
grep -q "alert: HighP95Latency" "$ALERT_RULES" || fail "Missing HighP95Latency alert"
grep -q "alert: CriticalP99Latency" "$ALERT_RULES" || fail "Missing CriticalP99Latency alert"
grep -q "alert: CriticalErrorRate" "$ALERT_RULES" || fail "Missing CriticalErrorRate alert"

if git rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
  check "Contracts versioning gate"
  merge_base=$(git merge-base HEAD origin/main)
  contracts_changed=$(git diff --name-only "$merge_base"...HEAD -- libs/contracts | grep -E '\.py$' | wc -l || true)
  if [[ "$contracts_changed" -gt 0 ]]; then
    git diff --name-only "$merge_base"...HEAD -- libs/contracts/VERSION | grep -q . || fail "contracts changed but VERSION not updated"
    git diff --name-only "$merge_base"...HEAD -- libs/contracts/CHANGELOG.md | grep -q . || fail "contracts changed but CHANGELOG.md not updated"
  fi
else
  echo "==> Contracts diff gate: skipped (origin/main not available)"
fi

echo "PASS: Architecture principles guard passed"
