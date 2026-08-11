#!/usr/bin/env bash
set -euo pipefail

apply_changes="false"
branches_csv="main"
repo=""

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
	set-branch-protection-gh.sh [--repo owner/name] [--branches main] [--apply]

Examples:
	set-branch-protection-gh.sh
	set-branch-protection-gh.sh --apply
	set-branch-protection-gh.sh --branches main --apply
	set-branch-protection-gh.sh --repo ivanprytula/api-observatory --apply

Notes:
	- Default mode is dry-run (prints payloads only).
	- This script is tailored for a single personal repository where the owner is the admin.
	- Direct pushes are restricted for normal users. The admin (you) can do emergency pushes.
	- Use --apply to update branch protection rules through GitHub API.
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--repo)
			repo="$2"
			shift 2
			;;
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

if [[ -z "$repo" ]]; then
	repo="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" || {
		die "Failed to auto-detect default repository. Please run 'gh repo set-default' or pass '--repo owner/name'."
	}
fi
owner="${repo%/*}"
name="${repo#*/}"

IFS=',' read -r -a branches <<<"$branches_csv"
if [[ ${#branches[@]} -eq 0 ]]; then
	die "No branches provided. Use --branches main"
fi

# Keep check names aligned with current .github/workflows/ci.yml job names.
# Format: "<workflow name> / <job display name>"
#
# Protect one stable aggregate gate so internal CI jobs can evolve without
# requiring branch-protection changes. Manual assurance and publication remain excluded.
default_contexts_json='[
 	"CI / Quality",
 	"CI / Unit and contract tests"
]'

for branch in "${branches[@]}"; do
	contexts_json="$default_contexts_json"

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
		if ! api_output=$(gh api \
			--method PUT \
			-H "Accept: application/vnd.github+json" \
			"/repos/${owner}/${name}/branches/${branch}/protection" \
			--input - <<<"$payload" 2>&1); then
			echo "Failed to apply protection rules to ${branch}." >&2
			echo "$api_output" >&2
			if echo "$api_output" | grep -q "403"; then
				echo "Hint: GitHub restricts branch protection on private repos on the Free tier." >&2
				echo "You can explicitly target a public repository using the --repo flag." >&2
				echo "Example: ./scripts/tools/set-branch-protection-gh.sh --repo ivanprytula/api-observatory --apply" >&2
			fi
			exit 1
		fi
		echo "Applied protection to ${owner}/${name}:${branch}"
	else
		echo "Dry-run only. Re-run with --apply to persist."
	fi
done
