# Local URL Matrix

Track: B — Engineering Execution

Use this page as the single source of truth for local API, browser, Bruno, WebSocket, smoke-test, and load-test URLs.

## Single switch

Set `LOCAL_API_SCHEME` before any local command that talks to the ingestor API:

```bash
LOCAL_API_SCHEME=http just api-check
LOCAL_API_SCHEME=https just api-check
```

`http` is fastest for day-to-day development. `https` routes API requests through the local edge proxy and matches production HTTPS behavior.

### Localhost vs 127.0.0.1 Performance Note

The URL matrix uses `127.0.0.1` for local request targets by default. Unlike `localhost`, which triggers glibc hostname resolution (checking `/etc/hosts` and potentially dual-stack IPv6/IPv4 lookups), `127.0.0.1` is an IPv4 literal that bypasses DNS resolution entirely. This avoids the small but measurable overhead of name resolution on each connection, making it the preferred choice for local development URLs.

## URL matrix

| Mode | Public base URL | API base URL | API docs URL | Dashboard URL | WebSocket base | Bruno `baseUrl` |
|---|---|---|---|---|---|---|
| Direct HTTP | `http://127.0.0.1:8000` | `http://127.0.0.1:8000` | `http://127.0.0.1:8000/docs` | `http://127.0.0.1:8501` | `ws://127.0.0.1:8000` | `http://127.0.0.1:8000` |
| Edge HTTPS | `https://127.0.0.1` | `https://127.0.0.1/api` | `https://127.0.0.1/api/docs` | `https://127.0.0.1/` | `wss://127.0.0.1` | `https://127.0.0.1/api` |

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LOCAL_API_SCHEME` | `http` | `http` for direct API, `https` for edge proxy. |
| `LOCAL_API_BASE_URL` | computed | Override the ingestor API base URL for local or deployed targets. |
| `LOCAL_DASHBOARD_URL` | computed | Override the dashboard URL used by smoke tests and docs. |
| `LOCAL_TLS_VERIFY` | `true` | Set to `false` to make helper curl calls pass `-k` for local HTTPS. |
| `LOCAL_API_HOST` / `LOCAL_API_PORT` | `127.0.0.1` / `8000` | Direct HTTP host and port. |
| `LOCAL_EDGE_HOST` | `127.0.0.1` | Edge HTTPS host. |

`LOCAL_API_BASE_URL` and `LOCAL_DASHBOARD_URL` win over computed values, so they can point at a cloud ALB, staging URL, or a custom local proxy.

## Shared helper

Scripts and recipes should use `scripts/daily/local-url.sh` instead of hardcoding local URLs.

```bash
source scripts/daily/local-url.sh

curl_local -sf "$(local_api_url /health)"
curl_local -sf "$(local_api_url /readyz)"
curl_local -sf "$(local_api_url /metrics)"

local_open_url /api/docs
local_open_url /
```

Command-line helpers:

```bash
bash scripts/daily/local-url.sh api-base-url
bash scripts/daily/local-url.sh api-public-base-url
bash scripts/daily/local-url.sh api-url /api/v1/sources
bash scripts/daily/local-url.sh dashboard-url
bash scripts/daily/local-url.sh websocket-url /ws/observations/stream
bash scripts/daily/local-url.sh bruno-env
bash scripts/daily/local-url.sh bruno-base-url
```

## Just recipes

```bash
# Fast local HTTP
just up
just api-check
just api-test

# Local HTTPS parity
just up-https
LOCAL_API_SCHEME=https just api-check
LOCAL_API_SCHEME=https just api-test
LOCAL_TLS_VERIFY=false LOCAL_API_SCHEME=https just api-check
```

`just stack-info` prints the active `INGESTOR_URL` from the same helper.

## Browser and CLI usage

```bash
# API docs
local_open_url /api/docs

# Dashboard
local_open_url /

# Bruno with the active local base URL
BRUNO_BASE_URL="$(bash scripts/daily/local-url.sh bruno-base-url)"
cd bruno && bru run . -r --env local --env-var "baseUrl=${BRUNO_BASE_URL}"

# WebSocket
wscat -c "$(bash scripts/daily/local-url.sh websocket-url /ws/observations/stream)"
```

## Cloud and non-local overrides

Cloud deployments are HTTPS by default. Use explicit base URLs when the target is not the local edge proxy:

```bash
LOCAL_API_BASE_URL=https://api.example.com
LOCAL_DASHBOARD_URL=https://dashboard.example.com
just smoke-test
```

For one-off tests:

```bash
BASE_URL=https://api.example.com scripts/smoke-test.sh
BASE_URL=https://api.example.com scripts/testing/03-load-test.sh k6
```
