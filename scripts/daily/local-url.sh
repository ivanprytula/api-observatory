#!/usr/bin/env bash
#
# Simplified local URL helpers.
#
# Default: http://127.0.0.1:8000 (direct, no proxy).
# Override with API_BASE_URL or DASHBOARD_URL.
#

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
fi

: "${API_BASE_URL:=http://127.0.0.1:8000}"
: "${DASHBOARD_URL:=http://127.0.0.1:8501}"

local_api_base_url() { printf '%s\n' "${API_BASE_URL%/}"; }

local_api_public_base_url() { local_api_base_url; }

local_api_url() {
  local path="${1:-/}"
  printf '%s%s\n' "$(local_api_base_url)" "/${path#/}"
}

local_dashboard_url() { printf '%s\n' "${DASHBOARD_URL%/}"; }

local_websocket_base_url() {
  local base
  base="$(local_api_base_url)"
  base="${base#http:}" && base="${base#https:}"
  printf 'ws://%s' "${base#//}"
}

local_websocket_url() {
  local path="${1:-/ws/observations/stream}"
  printf '%s%s\n' "$(local_websocket_base_url)" "/${path#/}"
}

curl_local() { curl "$@"; }

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    api-base-url)       local_api_base_url ;;
    api-public-base-url) local_api_public_base_url ;;
    api-url)            shift; local_api_url "${1:-/}" ;;
    dashboard-url)      local_dashboard_url ;;
    websocket-url)      shift; local_websocket_url "${1:-/ws/observations/stream}" ;;
    bruno-env)          printf 'local\n' ;;
    bruno-base-url)     local_api_base_url ;;
    *)                  local_api_base_url ;;
  esac
fi
