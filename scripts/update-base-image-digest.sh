#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

readonly IMAGE="python:3.14-slim"
readonly DOCKERFILES=(
  "Dockerfile"
  "services/inference/Dockerfile"
  "services/dashboard/Dockerfile"
)

info()    { echo "[INFO]    $*" >&2; }
success() { echo "[SUCCESS] $*" >&2; }
error()   { echo "[ERROR]   $*" >&2; exit 1; }

# Fetch the current digest for the image
fetch_digest() {
  local raw
  raw="$(docker buildx imagetools inspect "${IMAGE}" 2>/dev/null)" \
    || error "Failed to inspect ${IMAGE}. Is Docker running and buildx available?"

  local digest
  digest="$(echo "${raw}" | grep -m1 '^Name:' -A5 | grep 'Digest:' | awk '{print $2}')"

  if [[ -z "${digest}" ]]; then
    # Fallback: first sha256: line in the output
    digest="$(echo "${raw}" | grep -m1 'sha256:[a-f0-9]\{64\}' -o)"
  fi

  [[ -n "${digest}" ]] || error "Could not parse digest from imagetools output."
  echo "${digest}"
}

main() {
  cd "${PROJECT_ROOT}"

  info "Inspecting ${IMAGE} ..."
  local new_digest
  new_digest="$(fetch_digest)"
  info "Current digest: ${new_digest}"

  local updated=0
  for df in "${DOCKERFILES[@]}"; do
    if [[ ! -f "${df}" ]]; then
      info "Skipping ${df} (not found)"
      continue
    fi

    # Detect whichever sha256 digest is currently in the file
    local old_digest
    old_digest="$(grep -o 'sha256:[a-f0-9]\{64\}' "${df}" | head -1 || true)"

    if [[ -z "${old_digest}" ]]; then
      info "No digest found in ${df}, skipping"
      continue
    fi

    if [[ "${old_digest}" == "${new_digest}" ]]; then
      info "${df}: already up to date (${new_digest})"
      continue
    fi

    sed -i "s|${old_digest}|${new_digest}|g" "${df}"
    success "${df}: ${old_digest} → ${new_digest}"
    (( updated++ )) || true
  done

  if (( updated == 0 )); then
    info "All Dockerfiles already use the current digest."
  else
    success "Updated ${updated} Dockerfile(s)."
  fi
}

main "$@"
