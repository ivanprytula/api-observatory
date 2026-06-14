#!/usr/bin/env bash
# AWS environment helper.
# Behavior:
# - If `AWS_ENDPOINT_URL` points to a local emulator (e.g. LocalStack),
#   export the test credentials used by emulators.
# - If `AWS_ASSUME_ROLE_ARN` is set, call STS `assume-role` and export the
#   temporary credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
#   `AWS_SESSION_TOKEN`).
# - Otherwise, rely on `AWS_PROFILE` or the normal AWS CLI credential lookup.

set -euo pipefail

# Defaults
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-central-1}

# Detect whether script is sourced or executed (we prefer to be sourced)
_is_sourced() {
	# If return 0 succeeds, we're sourced
	(return 0 2>/dev/null)
}

_done() {
	if _is_sourced; then
		return "$1" 2>/dev/null || true
	else
		exit "$1"
	fi
}

usage() {
	cat <<'USAGE' >&2
Usage: source scripts/aws-env.sh [mode] [args]

Modes:
	floci|localstack        Export emulator test creds (AWS_ENDPOINT_URL defaults to http://127.0.0.1:4566)
	assume-role [ROLE_ARN]  Assume the given role (or use AWS_ASSUME_ROLE_ARN env)
	profile [NAME]          Export AWS_PROFILE=NAME
	(no args)               Auto-detect: prefer endpoint, then assume-role env, then profile
USAGE
	_done 1
}

# Simple arg parsing: mode is optional first arg
MODE=${1:-}
if [[ -n "$MODE" && ("$MODE" == "-h" || "$MODE" == "--help") ]]; then
	usage
fi

case "$MODE" in
	floci|localstack|deploy)
		# Explicit local emulator mode
		export AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL:-http://127.0.0.1:4566}
		export AWS_PROFILE=${AWS_PROFILE:-sandbox}
		export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test}
		export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
		unset AWS_SESSION_TOKEN || true
		echo "Set emulator creds for Floci/LocalStack" >&2
		_done 0
		;;

	assume-role)
		# allow role ARN to be passed as second arg
		ROLE_ARN=${2:-${AWS_ASSUME_ROLE_ARN:-}}
		if [[ -z "$ROLE_ARN" ]]; then
			echo "ERROR: assume-role requires ROLE_ARN argument or AWS_ASSUME_ROLE_ARN env" >&2
			_done 1
		fi
		SESSION_NAME=${AWS_ROLE_SESSION_NAME:-data-pipeline-session}
		DURATION=${AWS_ROLE_DURATION_SECONDS:-3600}
		echo "Assuming role ${ROLE_ARN} for ${SESSION_NAME} (duration ${DURATION}s)" >&2
		creds=$(aws sts assume-role \
			--role-arn "${ROLE_ARN}" \
			--role-session-name "${SESSION_NAME}" \
			--duration-seconds "${DURATION}" \
			--query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' \
			--output text) || {
			echo "ERROR: failed to assume role ${ROLE_ARN}" >&2
			_done 1
		}
		read -r AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN <<<"${creds}"
		export AWS_ACCESS_KEY_ID
		export AWS_SECRET_ACCESS_KEY
		export AWS_SESSION_TOKEN
		unset AWS_PROFILE || true
		echo "Temporary AWS credentials exported (expires in ${DURATION}s)" >&2
		_done 0
		;;

	profile)
		NEW_PROFILE=${2:-}
		if [[ -z "$NEW_PROFILE" ]]; then
			echo "ERROR: profile mode requires a profile name argument" >&2
			_done 1
		fi
		export AWS_PROFILE="$NEW_PROFILE"
		echo "Using AWS profile: $NEW_PROFILE" >&2
		_done 0
		;;

	"")
		# No explicit mode: fall back to previous auto-detect behavior
		if [[ -n "${AWS_ENDPOINT_URL:-}" && "${AWS_ENDPOINT_URL}" =~ ^http://127\.0\.0\.1 ]]; then
			export AWS_PROFILE=${AWS_PROFILE:-sandbox}
			export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test}
			export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
			unset AWS_SESSION_TOKEN || true
			echo "Auto-detected emulator endpoint; exported test creds" >&2
			_done 0
		fi

		if [[ -n "${AWS_ASSUME_ROLE_ARN:-}" ]]; then
			# behave like assume-role mode
			MODE=assume-role
			set -- assume-role
			exec "$0" "$@"
		fi

		if [[ -n "${AWS_PROFILE:-}" ]]; then
			echo "Using AWS profile: ${AWS_PROFILE}" >&2
			_done 0
		fi

		echo "No AWS_PROFILE, AWS_ASSUME_ROLE_ARN, or emulator detected; AWS CLI will use default credential chain." >&2
		_done 0
		;;

	*)
		echo "Unknown mode: $MODE" >&2
		usage
		;;
esac
