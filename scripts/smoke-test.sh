#!/usr/bin/env bash

set -o errexit -o pipefail -o nounset -o errtrace

readonly DEFAULT_BASE_URL="http://127.0.0.1:8000"
readonly HTTP_TIMEOUT_SECONDS=10

BASE_URL="${1:-${BASE_URL:-${DEFAULT_BASE_URL}}}"
SMOKE_JWT="${SMOKE_JWT:-}"

info() {
  printf '[INFO] %s\n' "$*" >&2
}

success() {
  printf '[PASS] %s\n' "$*" >&2
}

warn() {
  printf '[WARN] %s\n' "$*" >&2
}

error() {
  printf '[FAIL] %s\n' "$*" >&2
  exit 1
}

trap_error() {
  local line_number="$1"
  error "Unexpected failure at line ${line_number}"
}

trap 'trap_error ${LINENO}' ERR

base_url() {
  printf '%s' "${BASE_URL%/}"
}

request_status() {
  local method="$1"
  local url="$2"
  local payload="${3:-}"
  local -a curl_arguments=(
    --silent
    --output /dev/null
    --write-out '%{http_code}'
    --request "${method}"
    --max-time "${HTTP_TIMEOUT_SECONDS}"
  )

  if [[ -n "${SMOKE_JWT}" ]]; then
    curl_arguments+=(--header "Authorization: Bearer ${SMOKE_JWT}")
  fi
  if [[ -n "${payload}" ]]; then
    curl_arguments+=(--header 'Content-Type: application/json' --data "${payload}")
  fi

  curl "${curl_arguments[@]}" "${url}" || true
}

check_status() {
  local name="$1"
  local expected="$2"
  local method="$3"
  local url="$4"
  local payload="${5:-}"
  local status_code

  status_code="$(request_status "${method}" "${url}" "${payload}")"
  if [[ "${status_code}" != "${expected}" ]]; then
    error "${name}: expected HTTP ${expected}, got ${status_code:-000} (${url})"
  fi
  success "${name} (HTTP ${status_code})"
}

run_public_checks() {
  check_status 'GET /readyz' 200 GET "$(base_url)/readyz"
  check_status 'GET /health' 200 GET "$(base_url)/health"
  check_status 'GET /metrics' 200 GET "$(base_url)/metrics"
  check_status 'GET /docs' 200 GET "$(base_url)/docs"
  check_status 'GET /openapi.json' 200 GET "$(base_url)/openapi.json"
}

run_authenticated_checks() {
  local observation_payload

  if [[ -z "${SMOKE_JWT}" ]]; then
    warn 'Skipping authenticated API checks; set SMOKE_JWT to a writer/admin JWT.'
    return 0
  fi

  check_status 'GET /api/v1/scorecards' 200 GET "$(base_url)/api/v1/scorecards"
  check_status 'GET /api/v1/sources' 200 GET "$(base_url)/api/v1/sources"

  observation_payload="{\"source\":\"smoke-test\",\"data\":{\"test\":true,\"ts\":$(date +%s)},\"tags\":[\"smoke\"]}"
  check_status \
    'POST /api/v1/observations' \
    201 \
    POST \
    "$(base_url)/api/v1/observations" \
    "${observation_payload}"
  check_status 'GET /api/v1/observations' 200 GET "$(base_url)/api/v1/observations?limit=5"
}

main() {
  info "Core API smoke test: $(base_url)"
  run_public_checks
  run_authenticated_checks
  info 'Core API smoke test passed.'
}

main "$@"
