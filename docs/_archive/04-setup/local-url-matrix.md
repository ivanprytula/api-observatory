# Local URL Matrix

Track: B — Engineering Execution

Use this page as the single source of truth for local API, browser, Bruno, WebSocket, smoke-test, and load-test URLs.

## Single switch

Set `LOCAL_API_SCHEME` before any local command that talks to the ingestor API. `http` is fastest for day-to-day development; `https` routes through the local edge proxy and matches production HTTPS. See `scripts/daily/local-url.sh` for usage.

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

Scripts and recipes should use `scripts/daily/local-url.sh` instead of hardcoding local URLs. Run `bash scripts/daily/local-url.sh --help` for available subcommands and examples.

## Just recipes

See the Commands Reference or `scripts/daily/local-url.sh` for available recipes and examples.

`just stack-info` prints the active `INGESTOR_URL` from the same helper.

## Browser and CLI usage

See `scripts/daily/local-url.sh` and the Commands Reference for API, dashboard, Bruno, and WebSocket commands.

## Cloud and non-local overrides

Cloud deployments are HTTPS by default. Use explicit base URLs when the target is not the local edge proxy. See `scripts/daily/local-url.sh` for override patterns and the Commands Reference for smoke-test / load-test invocation.
