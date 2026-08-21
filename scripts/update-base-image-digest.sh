#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly PROJECT_ROOT

readonly PYTHON_IMAGE="dhi.io/python:3.14-debian13"
readonly PGVECTOR_IMAGE="dhi.io/pgvector:0.8-pg17-debian13-dev"
readonly PYTHON_DOCKERFILES=(
  "Dockerfile"
  "services/inference/Dockerfile"
  "services/dashboard/Dockerfile"
  "services/ingestor/tests/harness/Dockerfile"
)
readonly PGVECTOR_DOCKERFILES=("infra/database/Dockerfile")

info()    { echo "[INFO]    $*" >&2; }
success() { echo "[SUCCESS] $*" >&2; }
error()   { echo "[ERROR]   $*" >&2; exit 1; }

# Fetch the current digest for the image
fetch_digest() {
  local image="$1"
  local raw
  raw="$(docker buildx imagetools inspect "${image}" 2>/dev/null)" \
    || error "Failed to inspect ${image}. Is Docker running and buildx available?"

  local digest
  digest="$(echo "${raw}" | grep -m1 '^Name:' -A5 | grep 'Digest:' | awk '{print $2}')"

  if [[ -z "${digest}" ]]; then
    # Fallback: first sha256: line in the output
    digest="$(echo "${raw}" | grep -m1 'sha256:[a-f0-9]\{64\}' -o)"
  fi

  [[ -n "${digest}" ]] || error "Could not parse digest for ${image} from imagetools output."
  echo "${digest}"
}

update_dockerfiles() {
  local image="$1"
  shift
  local new_digest
  new_digest="$(fetch_digest "${image}")"
  info "Current ${image} digest: ${new_digest}"

  local df old_digest
  for df in "$@"; do
    if [[ ! -f "${df}" ]]; then
      info "Skipping ${df} (not found)"
      continue
    fi

    # Detect an existing digest on the matching FROM line.
    old_digest="$(grep -E -m1 -o "^FROM ${image}@sha256:[a-f0-9]{64}" "${df}" \
      | grep -E -o 'sha256:[a-f0-9]{64}' || true)"

    if [[ -n "${old_digest}" ]]; then
      if [[ "${old_digest}" == "${new_digest}" ]]; then
        info "${df}: already up to date (${new_digest})"
        continue
      fi

      sed -i -E "s#^FROM ${image}@sha256:[a-f0-9]{64}#FROM ${image}@${new_digest}#" "${df}"
    elif grep -Eq "^FROM ${image}([[:space:]]|$)" "${df}"; then
      # Add a digest when the matching FROM line is currently tag-only.
      sed -i -E "s#^FROM ${image}([[:space:]]|$)#FROM ${image}@${new_digest}\1#" "${df}"
    else
      info "Skipping ${df} (no FROM ${image} line found)"
      continue
    fi

    success "${df}: ${old_digest:-unPinned} → ${new_digest}"
    (( ++updated ))
  done
}

main() {
  cd "${PROJECT_ROOT}"

  local updated=0
  info "Inspecting ${PYTHON_IMAGE} ..."
  update_dockerfiles "${PYTHON_IMAGE}" "${PYTHON_DOCKERFILES[@]}"
  info "Inspecting ${PGVECTOR_IMAGE} ..."
  update_dockerfiles "${PGVECTOR_IMAGE}" "${PGVECTOR_DOCKERFILES[@]}"

  if (( updated == 0 )); then
    info "All tracked base-image digests are current."
  else
    success "Updated ${updated} Dockerfile(s)."
  fi
}

main "$@"
