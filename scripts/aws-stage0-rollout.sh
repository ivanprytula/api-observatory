#!/usr/bin/env bash

################################################################################
# Script: aws-stage0-rollout.sh
# Description: Roll out supplied immutable Stage 0 image references with rollback.
# Usage: Run remotely from /opt/api-observatory with image variables exported.
################################################################################

set -o errexit -o pipefail -o nounset -o errtrace

readonly COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.aws-stage0.yml}"
readonly HEALTH_ATTEMPTS=30
previous_ingestor=""
previous_inference=""
previous_dashboard=""
rollback_needed=true

info() { echo "[INFO] $*" >&2; }
warn() { echo "[WARN] $*" >&2; }
error() { echo "[ERROR] $*" >&2; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || { error "Required command not found: $1"; exit 1; }
}

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

current_image() {
  local service="$1"
  local container_id
  container_id="$(compose ps -q "${service}")"
  if [[ -n "${container_id}" ]]; then
    docker inspect --format '{{.Config.Image}}' "${container_id}"
  fi
}

rollback() {
  if [[ "${rollback_needed}" != true ]]; then
    return
  fi
  if [[ -z "${previous_ingestor}" || -z "${previous_inference}" || -z "${previous_dashboard}" ]]; then
    warn "Rollback skipped because a complete previous image set was not running."
    return
  fi

  warn "Restoring the captured image set. Database schema rollback is intentionally excluded."
  export INGESTOR_IMAGE="${previous_ingestor}"
  export INFERENCE_IMAGE="${previous_inference}"
  export DASHBOARD_IMAGE="${previous_dashboard}"
  compose up -d ingestor inference dashboard
}

on_error() {
  local line_no="$1"
  trap - ERR
  error "Rollout failed at line ${line_no}."
  rollback || warn "Rollback command failed; retain this SSM output for manual recovery."
  exit 1
}

wait_for() {
  local url="$1"
  local attempt=1
  while (( attempt <= HEALTH_ATTEMPTS )); do
    if curl --fail --silent --show-error "${url}" >/dev/null; then
      return 0
    fi
    sleep 2
    ((attempt += 1))
  done
  error "Readiness check failed: ${url}"
  return 1
}

main() {
  require_command docker
  require_command curl
  : "${INGESTOR_IMAGE:?Set INGESTOR_IMAGE to an ECR digest reference}"
  : "${INFERENCE_IMAGE:?Set INFERENCE_IMAGE to an ECR digest reference}"
  : "${DASHBOARD_IMAGE:?Set DASHBOARD_IMAGE to an ECR digest reference}"
  : "${SERVICE_VERSION:?Set SERVICE_VERSION to the selected tree identity}"

  previous_ingestor="$(current_image ingestor)"
  previous_inference="$(current_image inference)"
  previous_dashboard="$(current_image dashboard)"
  info "Captured current image references before migration."

  compose pull ingestor inference dashboard
  compose run --rm --no-deps ingestor alembic upgrade head
  compose run --rm --no-deps inference alembic upgrade head
  compose up -d ingestor inference dashboard

  wait_for http://127.0.0.1:8000/readyz
  wait_for http://127.0.0.1:8001/readyz
  wait_for http://127.0.0.1:8501/_stcore/health
  wait_for http://127.0.0.1:8000/openapi.json
  wait_for http://127.0.0.1:8001/openapi.json

  rollback_needed=false
  info "Stage 0 rollout and smoke checks succeeded."
}

trap 'on_error ${LINENO}' ERR
main "$@"
