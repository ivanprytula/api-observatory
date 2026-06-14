#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: apply-github-environment-protection.sh [--env env1,env2] [--secrets NAME,NAME]

Sets environment-scoped secrets (reads values from local env vars of the same name).
Also prints links to the environment UI so you can add required reviewers (manual step).

Examples:
  # set CI_POSTGRES_PASSWORD and GHCR_PAT for prod (reads local env vars)
  ./scripts/tools/apply-github-environment-protection.sh --env prod --secrets CI_POSTGRES_PASSWORD,GHCR_PAT

  # set secrets for prod and dev
  ./scripts/tools/apply-github-environment-protection.sh --env prod,dev --secrets CI_POSTGRES_PASSWORD,GHCR_PAT
USAGE
  exit 2
}

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install from https://cli.github.com/" >&2
  exit 1
fi

ENVS=(prod)
SECRETS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      shift
      IFS=',' read -r -a ENVS <<< "$1"
      shift
      ;;
    --secrets)
      shift
      IFS=',' read -r -a SECRETS <<< "$1"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      ;;
  esac
done

OWNER_REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

for ENV in "${ENVS[@]}"; do
  echo "\n=== Environment: $ENV ==="
  echo "Open the environment protection UI to add required reviewers (manual step):"
  echo "https://github.com/${OWNER_REPO}/settings/environments/${ENV}"

  if [[ ${#SECRETS[@]} -eq 0 ]]; then
    echo "No secrets requested (--secrets not provided); skipping secret set."
    continue
  fi

  for SECRET in "${SECRETS[@]}"; do
    # read local env var value with the same name as SECRET
    VAL="${!SECRET:-}"
    if [[ -z "$VAL" ]]; then
      echo "Skipping $SECRET for env $ENV: local env var $SECRET not set"
      continue
    fi

    echo "Setting secret $SECRET into environment $ENV"
    gh secret set "$SECRET" --env "$ENV" --body "$VAL"
  done
done

echo "\nDone. Remember to add required reviewers via the UI to enforce manual approvals."
