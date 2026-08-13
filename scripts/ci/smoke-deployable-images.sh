#!/usr/bin/env bash

set -o errexit -o pipefail -o nounset -o errtrace

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly PROJECT_ROOT
readonly COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.image-smoke.yml"
readonly COMPOSE_PROJECT="api-obs-image-smoke-${GITHUB_RUN_ID:-local}-${RANDOM}"
readonly INGESTOR_IMAGE="api-obs/ingestor:ci-smoke"
readonly INFERENCE_IMAGE="api-obs/inference:ci-smoke"
readonly DASHBOARD_IMAGE="api-obs/dashboard:ci-smoke"

info() { echo "[INFO] $*" >&2; }
success() { echo "[SUCCESS] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }
compose() { docker compose --project-name "${COMPOSE_PROJECT}" --file "${COMPOSE_FILE}" "$@"; }

cleanup() {
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  docker image rm "${DASHBOARD_IMAGE}" "${INFERENCE_IMAGE}" "${INGESTOR_IMAGE}" >/dev/null 2>&1 || true
}

show_logs() { compose logs --no-color || true; }

main() {
  docker info >/dev/null 2>&1 || error "Docker daemon is not running."
  info "Building disposable MVP workload images."
  compose build --pull

  info "Scanning images for high/critical CVEs."
  mkdir -p "${PROJECT_ROOT}/.local-dev/tmp/trivy-cache"
  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v "${PROJECT_ROOT}/.local-dev/tmp/trivy-cache:/root/.cache/trivy" \
    aquasec/trivy:0.56.2 \
    image --severity HIGH,CRITICAL --exit-code 1 \
    "${INGESTOR_IMAGE}" "${INFERENCE_IMAGE}" "${DASHBOARD_IMAGE}"

  compose up --wait --wait-timeout 180
  compose exec --no-TTY dashboard python -c \
    "import urllib.request; urllib.request.urlopen('http://ingestor:8000/readyz', timeout=5)"
  compose exec --no-TTY ingestor python -c '
import urllib.request
from services.ingestor.auth import create_jwt_token
token = create_jwt_token("image-smoke", {"roles": ["admin"]})
request = urllib.request.Request("http://127.0.0.1:8000/api/v1/scorecards", headers={"Authorization": f"Bearer {token}"})
urllib.request.urlopen(request, timeout=5).close()
'
  success "MVP workload images built and passed Compose health checks."
}

trap cleanup EXIT
trap show_logs ERR
main "$@"
