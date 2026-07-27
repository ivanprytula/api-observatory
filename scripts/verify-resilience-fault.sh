#!/usr/bin/env bash

################################################################################
# Script: verify-resilience-fault.sh
# Description: Prove the local inference bulkhead and circuit-breaker behavior.
# Usage: scripts/verify-resilience-fault.sh --confirm-fault-injection
# Author: api-observatory
################################################################################

set -o errexit -o pipefail -o nounset -o errtrace

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly PROJECT_ROOT
readonly INFERENCE_CONTAINER="api-obs-inference"
readonly API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
readonly INFERENCE_BASE_URL="${INFERENCE_BASE_URL:-http://127.0.0.1:8001}"
readonly PROMETHEUS_BASE_URL="${PROMETHEUS_BASE_URL:-http://127.0.0.1:9090}"

INFERENCE_PAUSED=false

info() { echo "[INFO] $*" >&2; }
success() { echo "[SUCCESS] $*" >&2; }
warn() { echo "[WARNING] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }
command_exists() { command -v "$1" >/dev/null 2>&1; }
require_command() { command_exists "$1" || error "Required command not found: $1"; }

trap_error() {
  local line_no="$1"
  error "Script failed at line ${line_no}"
}

cleanup() {
  if [[ "${INFERENCE_PAUSED}" == "true" ]]; then
    warn "Restoring inference container after fault injection"
    docker unpause "${INFERENCE_CONTAINER}" >/dev/null || warn "Could not unpause ${INFERENCE_CONTAINER}"
  fi
}

trap 'trap_error ${LINENO}' ERR
trap cleanup EXIT

usage() {
  cat >&2 <<'EOF'
Usage: scripts/verify-resilience-fault.sh --confirm-fault-injection

This pauses the local api-obs-inference container temporarily, sends 21
concurrent vector-search requests, and verifies Prometheus breaker/bulkhead
metrics. The container is always unpaused on exit.
EOF
}

require_status() {
  local url="$1"
  local expected_status="$2"
  local name="$3"
  local actual_status

  actual_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${url}")"
  [[ "${actual_status}" == "${expected_status}" ]] || error "${name} expected HTTP ${expected_status}, got ${actual_status}"
}

prometheus_value() {
  local query="$1"

  curl --fail --silent --show-error --get "${PROMETHEUS_BASE_URL}/api/v1/query" \
    --data-urlencode "query=${query}" \
    | jq --exit-status --raw-output '.data.result[0].value[1]'
}

wait_for_prometheus_value() {
  local query="$1"
  local expected_value="$2"
  local description="$3"
  local attempt=0
  local value=""

  while (( attempt < 12 )); do
    value="$(prometheus_value "${query}")"
    if [[ "${value}" == "${expected_value}" ]]; then
      success "${description}: ${value}"
      return 0
    fi
    sleep 5
    ((attempt += 1))
  done

  error "${description} expected ${expected_value}, last value was ${value}"
}

wait_for_prometheus_positive() {
  local query="$1"
  local description="$2"
  local attempt=0
  local value=""

  while (( attempt < 12 )); do
    value="$(prometheus_value "${query}")"
    if awk "BEGIN { exit !(${value} > 0) }"; then
      success "${description}: ${value}"
      return 0
    fi
    sleep 5
    ((attempt += 1))
  done

  error "${description} did not become positive; last value was ${value}"
}

main() {
  [[ "${1:-}" == "--confirm-fault-injection" && "$#" -eq 1 ]] || {
    usage
    exit 2
  }

  require_command docker
  require_command curl
  require_command jq
  require_command k6

  docker info >/dev/null 2>&1 || error "Docker daemon is not running"
  [[ "$(docker inspect --format '{{.State.Running}}' "${INFERENCE_CONTAINER}")" == "true" ]] \
    || error "${INFERENCE_CONTAINER} is not running"
  [[ "$(docker inspect --format '{{.State.Paused}}' "${INFERENCE_CONTAINER}")" == "false" ]] \
    || error "${INFERENCE_CONTAINER} is already paused; restore it before running this proof"

  require_status "${API_BASE_URL}/health" "200" "ingestor"
  require_status "${INFERENCE_BASE_URL}/health" "200" "inference"
  wait_for_prometheus_value \
    'dependency_circuit_breaker_state{dependency="inference",job="ingestor"}' \
    '0' \
    'inference breaker precondition'

  info "Pausing ${INFERENCE_CONTAINER}; this is a temporary local fault"
  docker pause "${INFERENCE_CONTAINER}" >/dev/null
  INFERENCE_PAUSED=true

  info "Running 21 concurrent vector-search health requests through k6"
  RESILIENCE_FAULT_MODE=inference-slow BASE_URL="${API_BASE_URL}" \
    k6 run "${PROJECT_ROOT}/scripts/load/k6-observations-load.js"

  wait_for_prometheus_positive \
    'dependency_bulkhead_rejected_total{dependency="inference",job="ingestor"}' \
    'inference bulkhead overflow rejections'
  wait_for_prometheus_value \
    'dependency_circuit_breaker_state{dependency="inference",job="ingestor"}' \
    '1' \
    'inference breaker opened'

  info "Restoring ${INFERENCE_CONTAINER}"
  docker unpause "${INFERENCE_CONTAINER}" >/dev/null
  INFERENCE_PAUSED=false

  info "Waiting 31 seconds for the circuit-breaker cooldown"
  sleep 31
  require_status "${API_BASE_URL}/api/v1/vector-search/health" "200" "inference recovery probe"
  wait_for_prometheus_value \
    'dependency_circuit_breaker_state{dependency="inference",job="ingestor"}' \
    '0' \
    'inference breaker recovered'

  success "Phase 2 resilience fault proof completed"
}

main "$@"
