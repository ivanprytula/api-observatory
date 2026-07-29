#!/usr/bin/env bash

################################################################################
# Script: smoke-deployable-images.sh
# Description: Build and health-check the three AWS Stage 0 service images.
# Usage: scripts/ci/smoke-deployable-images.sh
################################################################################

set -o errexit -o pipefail -o nounset -o errtrace

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly PROJECT_ROOT
readonly RUN_SUFFIX="${GITHUB_RUN_ID:-local}-${RANDOM}"
readonly NETWORK_NAME="api-obs-image-smoke-${RUN_SUFFIX}"
readonly INGESTOR_DB="api-obs-ingestor-db-${RUN_SUFFIX}"
readonly INFERENCE_DB="api-obs-inference-db-${RUN_SUFFIX}"
readonly INGESTOR_CONTAINER="api-obs-ingestor-${RUN_SUFFIX}"
readonly INFERENCE_CONTAINER="api-obs-inference-${RUN_SUFFIX}"
readonly DASHBOARD_CONTAINER="api-obs-dashboard-${RUN_SUFFIX}"
readonly INGESTOR_IMAGE="api-obs/ingestor:ci-smoke"
readonly INFERENCE_IMAGE="api-obs/inference:ci-smoke"
readonly DASHBOARD_IMAGE="api-obs/dashboard:ci-smoke"

info() { echo "[INFO] $*" >&2; }
success() { echo "[SUCCESS] $*" >&2; }
warn() { echo "[WARNING] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }
command_exists() { command -v "$1" >/dev/null 2>&1; }
require_command() { command_exists "$1" || error "Required command not found: $1"; }

cleanup() {
  info "Removing disposable image-smoke containers and network."
  docker rm -f \
    "${DASHBOARD_CONTAINER}" "${INFERENCE_CONTAINER}" "${INGESTOR_CONTAINER}" \
    "${INFERENCE_DB}" "${INGESTOR_DB}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK_NAME}" >/dev/null 2>&1 || true
  docker image rm \
    "${DASHBOARD_IMAGE}" "${INFERENCE_IMAGE}" "${INGESTOR_IMAGE}" >/dev/null 2>&1 || true
}

trap_error() {
  local line_no="$1"
  for container in "${INGESTOR_CONTAINER}" "${INFERENCE_CONTAINER}" "${DASHBOARD_CONTAINER}"; do
    docker logs "${container}" 2>/dev/null || true
  done
  error "Image smoke failed at line ${line_no}."
}

wait_for_postgres() {
  local container="$1"
  for _ in {1..30}; do
    if docker exec "${container}" pg_isready -U postgres >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  error "PostgreSQL did not become ready: ${container}"
}

wait_for_http() {
  local container="$1"
  local url="$2"
  for _ in {1..45}; do
    if docker exec "${container}" python -c \
      "import urllib.request; urllib.request.urlopen('${url}', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  error "Health endpoint did not become ready: ${container} ${url}"
}

assert_non_root() {
  local image="$1"
  local user
  user="$(docker image inspect "${image}" --format '{{.Config.User}}')"
  [[ -n "${user}" && "${user}" != "0" && "${user}" != "root" ]] \
    || error "Image must declare a non-root user: ${image}"
}

main() {
  require_command docker
  docker info >/dev/null 2>&1 || error "Docker daemon is not running."
  cd "${PROJECT_ROOT}"

  info "Building Stage 0 images without publishing them."
  docker build --tag "${INGESTOR_IMAGE}" .
  docker build --file services/inference/Dockerfile --tag "${INFERENCE_IMAGE}" .
  docker build --file services/dashboard/Dockerfile --tag "${DASHBOARD_IMAGE}" .

  assert_non_root "${INGESTOR_IMAGE}"
  assert_non_root "${INFERENCE_IMAGE}"
  assert_non_root "${DASHBOARD_IMAGE}"

  docker network create "${NETWORK_NAME}" >/dev/null
  docker run --detach --name "${INGESTOR_DB}" --network "${NETWORK_NAME}" \
    --env POSTGRES_DB=api_obs_ingestor --env POSTGRES_PASSWORD=postgres \
    --env POSTGRES_USER=postgres pgvector/pgvector:pg17-trixie >/dev/null
  docker run --detach --name "${INFERENCE_DB}" --network "${NETWORK_NAME}" \
    --env POSTGRES_DB=api_obs_inference --env POSTGRES_PASSWORD=postgres \
    --env POSTGRES_USER=postgres pgvector/pgvector:pg17-trixie >/dev/null
  wait_for_postgres "${INGESTOR_DB}"
  wait_for_postgres "${INFERENCE_DB}"

  docker run --rm --network "${NETWORK_NAME}" \
    --env "DATABASE_URL=postgresql+asyncpg://postgres:postgres@${INGESTOR_DB}:5432/api_obs_ingestor" \
    "${INGESTOR_IMAGE}" alembic upgrade head
  docker run --rm --network "${NETWORK_NAME}" \
    --env "DATABASE_URL=postgresql+asyncpg://postgres:postgres@${INFERENCE_DB}:5432/api_obs_inference" \
    "${INFERENCE_IMAGE}" alembic upgrade head

  docker run --detach --name "${INFERENCE_CONTAINER}" --network "${NETWORK_NAME}" \
    --env "DATABASE_URL=postgresql+asyncpg://postgres:postgres@${INFERENCE_DB}:5432/api_obs_inference" \
    "${INFERENCE_IMAGE}" >/dev/null
  docker run --detach --name "${INGESTOR_CONTAINER}" --network "${NETWORK_NAME}" \
    --env "DATABASE_URL=postgresql+asyncpg://postgres:postgres@${INGESTOR_DB}:5432/api_obs_ingestor" \
    --env CACHE_ENABLED=false --env BROKER_ENABLED=false --env MONGO_ENABLED=false \
    --env OTEL_ENABLED=false --env SENTRY_ENABLED=false \
    --env "INFERENCE_URL=http://${INFERENCE_CONTAINER}:8001" \
    "${INGESTOR_IMAGE}" >/dev/null
  docker run --detach --name "${DASHBOARD_CONTAINER}" --network "${NETWORK_NAME}" \
    --env "INGESTOR_URL=http://${INGESTOR_CONTAINER}:8000" \
    --env "INFERENCE_URL=http://${INFERENCE_CONTAINER}:8001" \
    "${DASHBOARD_IMAGE}" >/dev/null

  wait_for_http "${INGESTOR_CONTAINER}" "http://127.0.0.1:8000/readyz"
  wait_for_http "${INFERENCE_CONTAINER}" "http://127.0.0.1:8001/readyz"
  wait_for_http "${DASHBOARD_CONTAINER}" "http://127.0.0.1:8501/_stcore/health"
  success "All Stage 0 images built, ran as non-root, and passed readiness checks."
}

trap cleanup EXIT
trap 'trap_error ${LINENO}' ERR
main "$@"
