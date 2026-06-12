# Bruno API Collections

Version-controlled API collections for local testing and living documentation.
No accounts or cloud required — runs entirely from the CLI.

## Installation

```bash
npm install -g @usebruno/cli
```

Or run without installing:

```bash
npx @usebruno/cli run bruno/ --env local
```

## Run all collections

```bash
# Start the stack first
just up

just api-test
# equivalent:
BRUNO_BASE_URL="$(bash scripts/daily/local-url.sh bruno-base-url)"
cd bruno && bru run . -r --env local --env-var "baseUrl=${BRUNO_BASE_URL}"

# HTTPS parity
LOCAL_API_SCHEME=https just api-test
```

All requests should return 2xx. Exit code is 0 on success, non-zero if any request fails.

## Run a single collection

```bash
BRUNO_BASE_URL="$(bash scripts/daily/local-url.sh bruno-base-url)"
cd bruno && bru run sources --env local --env-var "baseUrl=${BRUNO_BASE_URL}"
cd bruno && bru run scorecards --env local --env-var "baseUrl=${BRUNO_BASE_URL}"
```

## Environment variables

The `local` environment is defined in [bruno/environments/local.bru](../../bruno/environments/local.bru). Bruno runs should pass the active base URL with `--env-var baseUrl=...` so HTTP and HTTPS modes do not diverge.

| Variable | Default | Description |
|----------|---------|-------------|
| `baseUrl` | `$(bash scripts/daily/local-url.sh bruno-base-url)` | Ingestor base URL for the active local mode |
| `token` | _(empty)_ | Bearer token — leave blank during MVP (no auth on routes yet) |
| `source_id` | `1` | Source ID used by get/patch/contracts/scorecards requests |

To override `source_id` for a run, edit `bruno/environments/local.bru` or pass env overrides:

```bash
cd bruno && bru run sources --env local --env-var source_id=3
```

## Collections

| Collection | Requests | Endpoints |
|------------|----------|-----------|
| `sources` | 4 | GET list, POST create, GET by ID, PATCH deactivate |
| `contracts` | 3 | POST snapshot, GET snapshots, GET drift events |
| `scorecards` | 2 | GET list, GET by source |
| `websocket` | 1 (smoke) | GET `/health` — see notes for wscat usage |

## Adding a new request

1. Create a `.bru` file in the relevant collection directory.
2. Use an existing file as a template.
3. Set `seq` to the next integer to control run order.
4. Use `{{baseUrl}}`, `{{token}}`, `{{source_id}}` for variables.

Example minimal GET request:

```bru
meta {
  name: My New Request
  type: http
  seq: 5
}

get {
  url: {{baseUrl}}/api/v1/sources
  body: none
  auth: bearer
}

auth:bearer {
  token: {{token}}
}
```

## WebSocket testing

Bruno CLI does not support WebSocket connections. Use wscat:

```bash
npm install -g wscat
wscat -c "$(bash scripts/daily/local-url.sh websocket-url /ws/observations/stream)"
```

Or open the Streamlit dashboard for a browser-based live tail:

```bash
uv run streamlit run services/dashboard/streamlit_app.py
```

## CI integration (post-MVP)

```yaml
- name: Test API with Bruno
  run: |
    npm install -g @usebruno/cli
    just up
    BRUNO_BASE_URL="$(bash scripts/daily/local-url.sh bruno-base-url)"
    cd bruno && bru run . -r --env local --env-var "baseUrl=${BRUNO_BASE_URL}"
    just down
```
