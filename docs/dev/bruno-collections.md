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
docker compose up -d

just api-test
# equivalent: bru run bruno/ --env local
```

All requests should return 2xx. Exit code is 0 on success, non-zero if any request fails.

## Run a single collection

```bash
bru run bruno/sources --env local
bru run bruno/scorecards --env local
```

## Environment variables

The `local` environment is defined in [bruno/environments/local.bru](../../bruno/environments/local.bru).

| Variable | Default | Description |
|----------|---------|-------------|
| `baseUrl` | `http://localhost:8000` | Ingestor base URL |
| `token` | _(empty)_ | Bearer token — leave blank during MVP (no auth on routes yet) |
| `source_id` | `1` | Source ID used by get/patch/contracts/scorecards requests |

To override `source_id` for a run, edit `bruno/environments/local.bru` or pass env overrides:

```bash
bru run bruno/sources --env local --env-var source_id=3
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
wscat -c "ws://localhost:8000/ws/records/stream"
```

Or open the Streamlit dashboard for a browser-based live tail:

```bash
uv run streamlit run streamlit_app.py
```

## CI integration (post-MVP)

```yaml
- name: Test API with Bruno
  run: |
    npm install -g @usebruno/cli
    docker compose up -d
    bru run bruno/ --env local
    docker compose down
```
