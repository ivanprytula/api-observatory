#!/usr/bin/env bash
set -euo pipefail

# Local runner for the 'Security Secrets Lite' workflow scan step.
# Usage: ./scripts/ci/run_secrets_scan_local.sh [base_sha] [head_sha]
# If base/head omitted, defaults to HEAD~1 and HEAD.

findings_file="secrets-findings.json"
echo "[]" > "$findings_file"

BASE=${1:-}
HEAD=${2:-}

if [[ -z "$HEAD" ]]; then
  HEAD=$(git rev-parse --verify HEAD)
fi

if [[ -z "$BASE" ]]; then
  # default to previous commit
  if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
    BASE=$(git rev-parse --verify HEAD~1)
  else
    BASE=$(git rev-list --max-parents=0 "$HEAD" | tail -n 1)
  fi
fi

echo "Scanning diff from $BASE to $HEAD"

mapfile -t all_changed_files < <(git diff --name-only --diff-filter=ACMR "$BASE" "$HEAD" | sort -u)

# Filter: exclude dev-only and example files
declare -a EXCLUDE_PATTERNS=(
  '\.example\.'          # *.example.* files (e.g., .env.example, secret.example.yaml)
  '/local/'              # local/ directories (e.g., infra/kubernetes/overlays/local/)
  '^\.env\.local'        # .env.local* files  '^@\.env\.test'         # .env.test files (test environment vars)
  'conftest\.py$'        # pytest conftest.py (test fixtures)
  '\.test\.'            # *.test.* test fixtures          # *.test.* test fixtures
  '^scripts/testing/'    # scripts/testing/ directory (test-only scripts)
  '^tests/'              # tests/ directory (unit/integration tests)
  'services/*/tests/'    # test directories within services
  '\.md$'                # Markdown files (documentation only)
)

mapfile -t changed_files < <(
  for file in "${all_changed_files[@]}"; do
    skip=0
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
      if [[ "$file" =~ $pattern ]]; then
        skip=1
        break
      fi
    done
    [[ $skip -eq 0 ]] && echo "$file"
  done
)

if [[ ${#changed_files[@]} -eq 0 ]]; then
  echo "No files to scan (all changes were in dev-only or example paths)."
  exit 0
fi

declare -a PATTERNS=(
  "AWS_ACCESS_KEY|critical|AKIA[0-9A-Z]{16}"
  "GITHUB_FINE_GRAINED_PAT|critical|github_pat_[0-9A-Za-z_]{82}"
  "GITHUB_PAT|critical|ghp_[0-9A-Za-z]{36}"
  "GITHUB_OAUTH|critical|gho_[0-9A-Za-z]{36}"
  "PRIVATE_KEY|critical|-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
  "GENERIC_SECRET_ASSIGNMENT|high|(secret|token|password|passwd|api[_-]?key|access[_-]?key|client[_-]?secret)[[:space:]]*[:=][[:space:]]*['\"]?[A-Za-z0-9_/+=~.-]{12,}"
  "CONNECTION_STRING_WITH_CREDS|high|[a-zA-Z]+://[^/@[:space:]]+:[^/@[:space:]]+@[^[:space:]]+"
  "JWT_TOKEN|medium|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
)

finding_count=0

for file in "${changed_files[@]}"; do
  [[ -f "$file" ]] || continue

  # read added lines only
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue

    # Skip lines marked with # pragma: no-scan (developer-documented test values)
    if printf '%s' "$line" | grep -q 'pragma: no-scan'; then
      continue
    fi

    # Skip obvious placeholders and test values to reduce noise.
    # Expanded patterns: test keys (sk_test_*, pk_test_*), fake values, demo, example
    if printf '%s' "$line" | grep -qiE -- '(example|placeholder|changeme|dummy|sample|fake|sk_test_|pk_test_|test_|_test_value|demo_|localhost:|test[-_]?key)'; then
      continue
    fi

    # Ignore lines that are reading secrets from environment variables or secret managers
    # (these are expected patterns, not hard-coded secrets).
    if printf '%s' "$line" | grep -qiE -- 'os\.environ\.get\(|os\.getenv\(|dotenv\.|load_dotenv|get_secret|secretmanager|secret_manager|vault\.|keyring\.|get_secret_value|sm_client|aws_secretsmanager'; then
      continue
    fi

    # Skip lines that assign the result of secret-generation functions
    # (token = create_jwt_token(...), key = generate_key(...), etc.)
    if printf '%s' "$line" | grep -qiE -- '(create_|generate_|make_)[a-z_]*\('; then
      continue
    fi

    for entry in "${PATTERNS[@]}"; do
      IFS='|' read -r pname psev regex <<< "$entry"
      if printf '%s\n' "$line" | grep -qE -- "$regex"; then
        match="$(printf '%s\n' "$line" | grep -oE -- "$regex" | head -n 1 || true)"
        [[ -n "$match" ]] || continue

        if [[ ${#match} -le 12 ]]; then
          redacted='[REDACTED]'
        else
          redacted="${match:0:4}...${match: -4}"
        fi

        tmp_file="$(mktemp)"
        jq --arg file "$file" \
           --arg pattern "$pname" \
           --arg severity "$psev" \
           --arg match "$redacted" \
           --arg line "$line" \
           '. + [{file: $file, pattern: $pattern, severity: $severity, match: $match, line: $line}]' \
           "$findings_file" > "$tmp_file"
        mv "$tmp_file" "$findings_file"

        finding_count=$((finding_count + 1))
      fi
    done
  done < <(git diff -U0 "$BASE" "$HEAD" -- "$file" | sed -n '/^+++ /d; s/^+//p')
done

echo "Found $finding_count potential secret-like matches."
if [[ $finding_count -gt 0 ]]; then
  jq . "$findings_file"
  exit 1
fi

echo "No secret exposures detected in added lines."
exit 0
