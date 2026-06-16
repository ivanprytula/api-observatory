#!/usr/bin/env bash
# Metadata: checks documentation for stale Justfile recipe references.
set -o errexit
set -o pipefail
set -o nounset
set -o errtrace

trap 'echo "ERROR: ${BASH_SOURCE[0]}:${LINENO}: ${BASH_COMMAND}" >&2' ERR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCAN_DIRS=(
  "docs"
  ".github/prompts"
  "infra/terraform/environments"
)
REMOVED_RECIPES=(
  "tf-plan-local"
  "tf-apply-local"
  "tf-show-local"
  "tf-state-list"
  "tf-apply-local-fresh"
  "tf-destroy-local"
  "up-aws"
  "sandbox-test"
  "sandbox-seed"
  "test-aws-connectivity"
  "deploy-dev"
  "floci-start"
  "tf-plan-dev"
  "tf-apply-dev"
)
COMPATIBILITY_ALIASES=(
  "sandbox-up"
  "sandbox-down"
  "sandbox-reset"
  "sandbox-deploy"
  "sandbox-dev"
)
ALLOWED_ALIAS_FILES=(
  "docs/dev/commands.md"
)

errors=0
warnings=0

contains_file() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

scan_file() {
  local file="$1"
  local rel_file="${file#"$REPO_ROOT"/}"
  local recipe
  local line

  for recipe in "${REMOVED_RECIPES[@]}"; do
    line="$(grep -nE "(^|[^A-Za-z0-9_-])${recipe}([^A-Za-z0-9_-]|$)" "$file" || true)"
    if [[ -n "$line" ]]; then
      printf 'ERROR: %s contains removed Justfile recipe %s\n%s\n' "$rel_file" "$recipe" "$line" >&2
      errors=$((errors + 1))
    fi
  done

  if contains_file "$rel_file" "${ALLOWED_ALIAS_FILES[@]}"; then
    return
  fi

  for recipe in "${COMPATIBILITY_ALIASES[@]}"; do
    line="$(grep -nE "(^|[^A-Za-z0-9_-])${recipe}([^A-Za-z0-9_-]|$)" "$file" || true)"
    if [[ -n "$line" ]]; then
      printf 'WARN: %s uses compatibility alias %s; prefer the canonical floci-* recipe\n%s\n' "$rel_file" "$recipe" "$line" >&2
      warnings=$((warnings + 1))
    fi
  done
}

while IFS= read -r -d '' file; do
  scan_file "$file"
done < <(find "${SCAN_DIRS[@]}" -type f \( -name '*.md' -o -name '*.prompt.md' \) -print0)

if [[ "$errors" -gt 0 ]]; then
  printf 'Found %s stale Justfile recipe reference(s).\n' "$errors" >&2
  exit 1
fi

if [[ "$warnings" -gt 0 ]]; then
  printf 'Found %s compatibility alias reference(s); prefer canonical floci-* names in docs.\n' "$warnings" >&2
fi

printf 'No stale Justfile recipe references found.\n'
