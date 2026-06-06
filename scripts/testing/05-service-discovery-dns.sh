#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset
set -o errtrace

readonly SCRIPT_NAME="$(basename "$0")"
readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
readonly NGINX_CONF="${PROJECT_ROOT}/infra/nginx/nginx.conf"

info() {
  echo "[INFO] $*"
}

pass() {
  echo "[PASS] $*"
}

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

trap_error() {
  local line_no="$1"
  echo "[FAIL] ${SCRIPT_NAME} failed at line ${line_no}" >&2
  exit 1
}

trap 'trap_error ${LINENO}' ERR

main() {
  require_command docker
  require_command grep
  require_command awk
  require_command cut
  require_command sort

  [[ -f "${COMPOSE_FILE}" ]] || fail "Missing compose file: ${COMPOSE_FILE}"
  [[ -f "${NGINX_CONF}" ]] || fail "Missing nginx config: ${NGINX_CONF}"

  info "Validating compose model"
  docker compose -f "${PROJECT_ROOT}/docker-compose.yml" config >/tmp/compose.out
  pass "compose-config-ok"

  info "Collecting compose service DNS names"
  local services
  services="$(
    awk '
      /^services:/ {in_services=1; next}
      in_services && /^[^[:space:]]/ {in_services=0}
      in_services && /^  [A-Za-z0-9_-]+:/ {
        name=$1
        sub(":", "", name)
        print name
      }
    ' "${COMPOSE_FILE}" | sort -u
  )"

  [[ -n "${services}" ]] || fail "No services found in docker-compose.yml"

  info "Collecting nginx upstream hosts"
  local upstream_hosts
  upstream_hosts="$(
    awk '{sub(/#.*/, ""); print}' "${NGINX_CONF}" \
      | grep -Eo 'server[[:space:]]+[A-Za-z0-9._-]+:[0-9]+' \
      | awk '{print $2}' \
      | cut -d: -f1 \
      | sort -u
  )"

  [[ -n "${upstream_hosts}" ]] || fail "No upstream hosts found in nginx config"

  while IFS= read -r host; do
    [[ -n "${host}" ]] || continue

    if [[ "${host}" == "localhost" || "${host}" == 127.* ]]; then
      fail "Upstream host '${host}' uses local loopback; use orchestrator service DNS name"
    fi

    if ! grep -Fxq "${host}" <<<"${services}"; then
      fail "Upstream host '${host}' is not a compose service name"
    fi

    pass "upstream host '${host}' resolves to compose service DNS"
  done <<<"${upstream_hosts}"

  pass "Service discovery stage 1 validated (orchestrator DNS/service names)"
}

main "$@"
