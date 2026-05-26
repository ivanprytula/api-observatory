#!/usr/bin/env bash
set -euo pipefail

repo=""
apply_changes="false"
branches_csv="main,develop"
approvals="1"
discover_contexts="false"
discover_ref=""
enforce_admins="false"
bypass_users_csv=""
owner_type=""

usage() {
	cat <<'EOF'
Usage:
	set-branch-protection-gh.sh [--repo owner/name] [--branches main,develop] [--approvals 1] [--discover] [--discover-ref main] [--enforce-admins true|false] [--bypass-users user1,user2] [--apply]

Examples:
	set-branch-protection-gh.sh
	set-branch-protection-gh.sh --apply
	set-branch-protection-gh.sh --bypass-users ivanprytula --apply
	set-branch-protection-gh.sh --discover --discover-ref main
	set-branch-protection-gh.sh --repo ivanprytula/api-observatory --branches main --apply

Notes:
	- Default mode is dry-run (prints payloads only).
	- --discover auto-discovers required checks from latest check-runs on the selected ref.
	- Personal repositories cannot use user/team bypass lists; admin bypass is controlled via --enforce-admins.
	- For personal repos, use --enforce-admins false to allow direct push only for admins.
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
		--approvals)
			approvals="$2"
			shift 2
			;;
		--apply)
			apply_changes="true"
			shift
			;;
		--discover)
			discover_contexts="true"
			shift
			;;
		--discover-ref)
			discover_ref="$2"
			shift 2
			;;
		--enforce-admins)
			enforce_admins="$2"
			shift 2
			;;
		--bypass-users)
			bypass_users_csv="$2"
			shift 2
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

if ! command -v gh >/dev/null 2>&1; then
	echo "gh CLI is required." >&2
	exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
	echo "jq is required." >&2
	exit 1
fi

if [[ -z "$repo" ]]; then
	repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

owner_type="$(gh api "repos/${repo}" -q .owner.type)"

if [[ "$enforce_admins" != "true" && "$enforce_admins" != "false" ]]; then
	echo "--enforce-admins must be 'true' or 'false'." >&2
	exit 1
fi

owner="${repo%/*}"
name="${repo#*/}"

IFS=',' read -r -a branches <<<"$branches_csv"

if [[ -z "$bypass_users_csv" ]]; then
	bypass_users_csv="$(gh api user -q .login)"
fi

bypass_users_json="$(
	printf '%s' "$bypass_users_csv" \
	| tr ',' '\n' \
	| sed 's/^ *//; s/ *$//' \
	| sed '/^$/d' \
	| jq -R . \
	| jq -s .
)"

supports_user_bypass="false"
if [[ "$owner_type" == "Organization" ]]; then
	supports_user_bypass="true"
elif [[ -n "$bypass_users_csv" ]]; then
	echo "Info: Personal repository detected; user/team bypass lists are not supported by GitHub API." >&2
	echo "Info: Ignoring --bypass-users and relying on admin bypass via --enforce-admins=false." >&2
fi

default_contexts_json='[
	"CI / 01 Quality checks — Python 3.14",
	"CI / 01b Change impact routing",
	"CI / 02 Unit tests — Python 3.14",
	"Security Secrets Lite / Secrets Scan (changed lines)"
]'

discover_required_contexts() {
	local ref="$1"
	local sha
	sha="$(gh api "repos/${owner}/${name}/commits/${ref}" -q .sha 2>/dev/null || true)"
	if [[ -z "$sha" ]]; then
		return 1
	fi

	local targets_json
	targets_json='[
		"01 Quality checks — Python 3.14",
		"01b Change impact routing",
		"02 Unit tests — Python 3.14",
		"Secrets Scan (changed lines)"
	]'

	gh api "repos/${owner}/${name}/commits/${sha}/check-runs" \
		| jq -c --argjson targets "$targets_json" '
			.check_runs
			| map({
				workflow: (.check_suite.workflow_run.workflow.name // .check_suite.workflow_run.name // ""),
				name: .name
			})
			| map(select(.name as $n | $targets | index($n)))
			| map(if .workflow == "" then .name else (.workflow + " / " + .name) end)
			| unique'
}

contexts_json="$default_contexts_json"

if [[ "$discover_contexts" == "true" ]]; then
	ref_for_discovery="$discover_ref"
	if [[ -z "$ref_for_discovery" ]]; then
		ref_for_discovery="${branches[0]}"
	fi

	discovered="$(discover_required_contexts "$ref_for_discovery" || true)"
	if [[ -n "$discovered" && "$discovered" != "[]" ]]; then
		contexts_json="$discovered"
		echo "Using auto-discovered contexts from ref: ${ref_for_discovery}"
	else
		echo "Auto-discovery found no matching contexts on ref '${ref_for_discovery}'. Using default contexts." >&2
	fi
fi

if [[ "$discover_contexts" != "true" ]]; then
read -r -d '' contexts_json <<'JSON' || true
[
	"CI / 01 Quality checks — Python 3.14",
	"CI / 01b Change impact routing",
	"CI / 02 Unit tests — Python 3.14",
	"Security Secrets Lite / Secrets Scan (changed lines)"
]
JSON
fi

for branch in "${branches[@]}"; do
	payload="$(jq -n \
		--argjson contexts "$contexts_json" \
		--argjson approvals "$approvals" \
		--argjson enforce_admins "$enforce_admins" \
		--argjson bypass_users "$bypass_users_json" \
		--argjson supports_user_bypass "$supports_user_bypass" \
		'{
			required_status_checks: {
				strict: true,
				contexts: $contexts
			},
			enforce_admins: $enforce_admins,
			required_pull_request_reviews: {
				dismiss_stale_reviews: true,
				require_code_owner_reviews: false,
				required_approving_review_count: $approvals,
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
		}
		| if $supports_user_bypass then
			.required_pull_request_reviews.bypass_pull_request_allowances = {
				users: $bypass_users,
				teams: [],
				apps: []
			}
		  else
			.
		  end')"

	echo "=== Branch: ${branch} ==="
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
