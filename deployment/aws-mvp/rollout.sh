#!/usr/bin/env bash
set -o errexit -o pipefail -o nounset -o errtrace

readonly COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
readonly DEPLOYMENT_ENV_FILE="${DEPLOYMENT_ENV_FILE:-.runtime/deployment.env}"
readonly PREVIOUS_ENV_FILE="${DEPLOYMENT_ENV_FILE}.previous"
previous_ingestor=""
previous_cache=""
rollback_needed=true
profile_args=()
enabled_profiles=""

configure_profiles() {
  local env_file="$1"
  local profile
  profile_args=()
  enabled_profiles="$(awk -F= '$1 == "ENABLED_PROFILES" {print substr($0, index($0, "=") + 1)}' "${env_file}")"
  [[ "${enabled_profiles}" =~ ^(inference|cache|broker|monitoring)?(,(inference|cache|broker|monitoring))*$ ]] || {
    error "Invalid ENABLED_PROFILES value."
    return 1
  }
  [[ -n "${enabled_profiles}" ]] || return
  IFS=',' read -r -a profiles <<< "${enabled_profiles}"
  for profile in "${profiles[@]}"; do
    case "${profile}" in inference|cache|broker|monitoring) profile_args+=(--profile "${profile}") ;; *) error "Unsupported profile: ${profile}"; return 1 ;; esac
  done
}
profile_enabled() {
  case ",${enabled_profiles}," in
    *,"$1",*) return 0 ;;
    *) return 1 ;;
  esac
}
compose() { docker compose --env-file "${DEPLOYMENT_ENV_FILE}" "${profile_args[@]}" -f "${COMPOSE_FILE}" "$@"; }
error() { echo "[ERROR] $*" >&2; }
current_image() { local id; id="$(compose ps -q "$1")"; [[ -z "$id" ]] || docker inspect --format '{{.Config.Image}}' "$id"; }

rollback() {
  [[ "$rollback_needed" == true ]] || return
  if [[ -z "$previous_ingestor" || -z "$previous_cache" || ! -r "$PREVIOUS_ENV_FILE" ]]; then
    compose down --remove-orphans || true
    rm -f "${DEPLOYMENT_ENV_FILE}"
    return
  fi
  error "Restoring previous images: ingestor=${previous_ingestor}, cache=${previous_cache:-not-running}"
  mv "${PREVIOUS_ENV_FILE}" "${DEPLOYMENT_ENV_FILE}"
  configure_profiles "${DEPLOYMENT_ENV_FILE}"
  compose up -d --wait --wait-timeout 120
}

wait_for() {
  local url="$1" attempt=1
  while ((attempt <= 30)); do curl --fail --silent "$url" >/dev/null && return; sleep 2; ((attempt += 1)); done
  error "Readiness check failed: ${url}"; return 1
}

wait_for_redis() {
  local attempt=1
  while ((attempt <= 30)); do
    docker compose --env-file "${DEPLOYMENT_ENV_FILE}" -f "${COMPOSE_FILE}" exec -T cache redis-cli -a "$REDIS_PASSWORD" ping >/dev/null 2>&1 && return
    sleep 2
    ((attempt += 1))
  done
  error "Redis readiness check failed"; return 1
}

main() {
  [[ -r "$DEPLOYMENT_ENV_FILE" ]] || { error "Missing desired-state deployment env."; exit 1; }
  configure_profiles "${DEPLOYMENT_ENV_FILE}"
  previous_ingestor="$(current_image ingestor)"
  previous_cache="$(current_image cache)"
  compose pull
  compose up -d --wait ingestor-db
  compose run --rm --no-deps ingestor alembic upgrade head
  compose up -d --wait --wait-timeout 120
  if profile_enabled cache; then
    wait_for_redis
  fi
  wait_for http://127.0.0.1:8000/readyz
  compose exec -T ingestor python -c '
import urllib.request
from services.ingestor.auth import create_jwt_token
token = create_jwt_token("mvp-smoke", {"roles": ["admin"]})
request = urllib.request.Request("http://127.0.0.1:8000/api/v1/scorecards", headers={"Authorization": f"Bearer {token}"})
urllib.request.urlopen(request, timeout=5).close()
'
  rollback_needed=false
  rm -f "$PREVIOUS_ENV_FILE"
}

trap 'rollback' ERR
main "$@"
