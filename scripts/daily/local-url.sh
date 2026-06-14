#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
fi

: "${LOCAL_API_SCHEME:=http}"
: "${LOCAL_API_HOST:=127.0.0.1}"
: "${LOCAL_API_PORT:=8000}"
: "${LOCAL_EDGE_HOST:=127.0.0.1}"
: "${LOCAL_DASHBOARD_HOST:=127.0.0.1}"
: "${LOCAL_DASHBOARD_PORT:=8501}"
: "${LOCAL_DASHBOARD_SCHEME:=http}"

_invalid_scheme() {
  echo "LOCAL_API_SCHEME must be 'http' or 'https' (got '${LOCAL_API_SCHEME}')" >&2
  if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    exit 2
  fi
  return 2
}

case "${LOCAL_API_SCHEME}" in
  http|https) ;;
  *)
    _invalid_scheme
    if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
      exit 2
    fi
    return 2
    ;;
esac

local_api_base_url() {
  if [[ -n "${LOCAL_API_BASE_URL:-}" ]]; then
    printf '%s\n' "${LOCAL_API_BASE_URL%/}"
    return 0
  fi

  if [[ "${LOCAL_API_SCHEME}" == "https" ]]; then
    printf 'https://%s/api\n' "${LOCAL_EDGE_HOST}"
  else
    printf 'http://%s:%s\n' "${LOCAL_API_HOST}" "${LOCAL_API_PORT}"
  fi
}

local_api_public_base_url() {
  if [[ "${LOCAL_API_SCHEME}" == "https" ]]; then
    printf 'https://%s\n' "${LOCAL_EDGE_HOST}"
  else
    local_api_base_url
  fi
}

local_api_url() {
  local path="${1:-/}"
  path="/${path#/}"

  if [[ "${LOCAL_API_SCHEME}" == "https" ]]; then
    if [[ -n "${LOCAL_API_BASE_URL:-}" ]]; then
      local base
      base="$(local_api_base_url)"
      if [[ "${path}" == /api* && "${base}" == */api ]]; then
        path="${path#/api}"
      fi
      printf '%s%s\n' "${base}" "${path}"
      return 0
    fi

    case "${path}" in
      /health|/healthz|/readyz|/metrics)
        printf 'https://%s%s\n' "${LOCAL_EDGE_HOST}" "${path}"
        return 0
        ;;
      /docs|/openapi.json|/redoc)
        printf 'https://%s/api%s\n' "${LOCAL_EDGE_HOST}" "${path}"
        return 0
        ;;
      /api*)
        path="${path#/api}"
        ;;
    esac
  fi

  printf '%s%s\n' "$(local_api_base_url)" "${path}"
}

local_dashboard_url() {
  if [[ -n "${LOCAL_DASHBOARD_URL:-}" ]]; then
    printf '%s\n' "${LOCAL_DASHBOARD_URL%/}"
    return 0
  fi

  if [[ "${LOCAL_DASHBOARD_SCHEME}" == "https" ]]; then
    printf 'https://%s/\n' "${LOCAL_DASHBOARD_HOST}"
  else
    printf 'http://%s:%s/\n' "${LOCAL_DASHBOARD_HOST}" "${LOCAL_DASHBOARD_PORT}"
  fi
}

local_websocket_base_url() {
  if [[ "${LOCAL_API_SCHEME}" == "https" ]]; then
    printf 'wss://%s' "${LOCAL_EDGE_HOST}"
  else
    printf 'ws://%s:%s' "${LOCAL_API_HOST}" "${LOCAL_API_PORT}"
  fi
}

local_websocket_url() {
  local path="${1:-/ws/observations/stream}"
  path="/${path#/}"
  printf '%s%s\n' "$(local_websocket_base_url)" "${path}"
}

_tls_verify_enabled() {
  case "${LOCAL_TLS_VERIFY:-true}" in
    false|0|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

local_curl_flags() {
  if [[ "${LOCAL_API_SCHEME}" == "https" ]] && ! _tls_verify_enabled; then
    printf '%s\n' '-k'
  fi
}

curl_local() {
  local -a flags=()
  while IFS= read -r flag; do
    [[ -n "${flag}" ]] && flags+=("${flag}")
  done < <(local_curl_flags)

  curl "${flags[@]}" "$@"
}

local_open_url() {
  local url
  if [[ "${1:-}" == http://* || "${1:-}" == https://* || "${1:-}" == ws://* || "${1:-}" == wss://* ]]; then
    url="$1"
  else
    url="$(local_api_url "$1")"
  fi

  if [[ -n "${OPEN_COMMAND:-}" ]]; then
    "${OPEN_COMMAND}" "${url}"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}"
  elif command -v open >/dev/null 2>&1; then
    open "${url}"
  else
    printf '%s\n' "${url}"
  fi
}

local_bruno_env() {
  if [[ "${LOCAL_API_SCHEME}" == "https" ]]; then
    printf '%s\n' 'local-https'
  else
    printf '%s\n' 'local'
  fi
}

local_bruno_base_url() {
  local_api_base_url
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    api-base-url)
      local_api_base_url
      ;;
    api-public-base-url)
      local_api_public_base_url
      ;;
    api-url)
      shift
      local_api_url "${1:-/}"
      ;;
    dashboard-url)
      local_dashboard_url
      ;;
    websocket-url)
      shift
      local_websocket_url "${1:-/ws/observations/stream}"
      ;;
    curl-flags)
      local_curl_flags
      ;;
    bruno-env)
      local_bruno_env
      ;;
    bruno-base-url)
      local_bruno_base_url
      ;;
    open)
      shift
      local_open_url "${1:-/}"
      ;;
    *)
      local_api_base_url
      ;;
  esac
fi
