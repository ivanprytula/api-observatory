#!/usr/bin/env bash
set -euo pipefail

apply_changes="false"
branches_csv="main,develop"

die() {
	echo "$*" >&2
	exit 1
}

info() {
	echo "Info: $*" >&2
}

usage() {
	cat <<'EOF'
Usage:
	set-branch-protection-gh.sh [--branches main,develop] [--apply]

Examples:
	set-branch-protection-gh.sh
	set-branch-protection-gh.sh --apply
	set-branch-protection-gh.sh --branches main --apply

Notes:
	- Default mode is dry-run (prints payloads only).
	- This script is tailored for a single personal repository where the owner is the admin.
	- Direct pushes are restricted for normal users. The admin (you) can do emergency pushes.
	- Use --apply to update branch protection rules through GitHub API.
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--branches)
			branches_csv="$2"
			shift 2
			;;
		--apply)
			apply_changes="true"
			shift
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			echo "Unknown argument: $1" >&2
			usage
			exit 1
			;;
	esac
done

command -v gh >/dev/null 2>&1 || die "gh CLI is required."
command -v jq >/dev/null 2>&1 || die "jq is required."

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
owner="${repo%/*}"
name="${repo#*/}"

IFS=',' read -r -a branches <<<"$branches_csv"
if [[ ${#branches[@]} -eq 0 ]]; then
	die "No branches provided. Use --branches main,develop"
fi

# Keep check names aligned with current .github/workflows/ci.yml job names.
default_contexts_develop_json='[
	"CI / Lint (ruff check + format)",
	"CI / Unit tests (sqlite)",
	"CI / Integration tests (postgres + redis)",
	"CI / Observability gates (promtool + smoke deploy)"
]'

default_contexts_main_json='[
	"CI / Lint (ruff check + format)",
	"CI / Unit tests (sqlite)",
	"Security / Security summary"
]'

for branch in "${branches[@]}"; do
	if [[ "$branch" == "main" ]]; then
		contexts_json="$default_contexts_main_json"
	else
		contexts_json="$default_contexts_develop_json"
	fi

	payload="$(jq -n \
		--argjson contexts "$contexts_json" \
		'{
			required_status_checks: {
				strict: true,
				contexts: $contexts
			},
			enforce_admins: false,
			required_pull_request_reviews: {
				dismiss_stale_reviews: true,
				require_code_owner_reviews: false,
				required_approving_review_count: 1,
				require_last_push_approval: false
			},
			restrictions: null,
			required_conversation_resolution: true,
			required_linear_history: false,
			allow_force_pushes: false,
			allow_deletions: false,
			block_creations: false,
			lock_branch: false,
			allow_fork_syncing: true
		}')"

	echo "=== Branch: ${branch} ==="
	# Compact summary: checks count, mode, repo
	checks_count=$(echo "$contexts_json" | jq 'length')
	mode=$([ "$apply_changes" = "true" ] && echo "apply" || echo "dry-run")
	echo "Summary: Checks=${checks_count}, Mode=${mode}, Repo=${repo}"
	echo "$payload" | jq .

	if [[ "$apply_changes" == "true" ]]; then
		gh api \
			--method PUT \
			-H "Accept: application/vnd.github+json" \
			"/repos/${owner}/${name}/branches/${branch}/protection" \
			--input - <<<"$payload" >/dev/null
		echo "Applied protection to ${owner}/${name}:${branch}"
	else
		echo "Dry-run only. Re-run with --apply to persist."
	fi
done
