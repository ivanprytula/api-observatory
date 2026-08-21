#!/usr/bin/env bash

set -o errexit -o pipefail -o nounset -o errtrace

readonly DEFAULT_GATEWAY_URL='https://127.0.0.1'
readonly HTTP_TIMEOUT_SECONDS=10

GATEWAY_URL="${1:-${GATEWAY_URL:-${DEFAULT_GATEWAY_URL}}}"
TLS_VERIFY="${TLS_VERIFY:-true}"
PASS=0
FAIL=0
CURL_TLS_ARGUMENTS=()

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

gateway_url() {
  printf '%s' "${GATEWAY_URL%/}"
}

record_result() {
  local name="$1"
  local expected="$2"
  local actual="$3"

  if [[ "${actual}" =~ ${expected} ]]; then
    success "${name} (HTTP ${actual})"
    ((++PASS))
  else
    warn "${name} (HTTP ${actual}; expected ${expected})"
    ((++FAIL))
  fi
}

request_status() {
  curl \
    "${CURL_TLS_ARGUMENTS[@]}" \
    --silent \
    --output /dev/null \
    --write-out '%{http_code}' \
    --max-time "${HTTP_TIMEOUT_SECONDS}" \
    "$1" || true
}

check_status() {
  local name="$1"
  local expected_pattern="$2"
  local url="$3"
  local status_code

  status_code="$(request_status "${url}")"
  record_result "${name}" "${expected_pattern}" "${status_code:-000}"
}

check_request_id_header() {
  local headers

  headers="$(curl \
    "${CURL_TLS_ARGUMENTS[@]}" \
    --silent \
    --dump-header - \
    --output /dev/null \
    --max-time "${HTTP_TIMEOUT_SECONDS}" \
    "$(gateway_url)/api/docs" || true)"
  if grep -qi '^x-request-id:' <<<"${headers}"; then
    success 'GET /api/docs includes X-Request-ID'
    ((++PASS))
  else
    warn 'GET /api/docs is missing X-Request-ID'
    ((++FAIL))
  fi
}

main() {
  [[ "${TLS_VERIFY}" == 'true' || "${TLS_VERIFY}" == 'false' ]] || error 'TLS_VERIFY must be true or false.'
  if [[ "${TLS_VERIFY}" == 'false' ]]; then
    CURL_TLS_ARGUMENTS=(--insecure)
  fi

  info "Ingress smoke test: $(gateway_url)"
  check_status 'GET /readyz' '^200$' "$(gateway_url)/readyz"
  check_status 'GET /ping' '^200$' "$(gateway_url)/ping"
  check_status 'GET /' '^2[0-9][0-9]$|^3[0-9][0-9]$' "$(gateway_url)/"
  check_status 'GET /dashboard/_stcore/health' '^2[0-9][0-9]$|^3[0-9][0-9]$' "$(gateway_url)/dashboard/_stcore/health"
  check_status 'GET /api/docs' '^2[0-9][0-9]$|^3[0-9][0-9]$' "$(gateway_url)/api/docs"
  check_status 'GET /api/openapi.json' '^200$' "$(gateway_url)/api/openapi.json"
  check_request_id_header

  info "Results: ${PASS} passed, ${FAIL} failed."
  ((FAIL == 0)) || error 'Ingress smoke test failed.'
}

main "$@"
