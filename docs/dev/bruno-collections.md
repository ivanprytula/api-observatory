# Bruno API Collections

Version-controlled API collections for local testing and living documentation.
No accounts or cloud required — the `.bru` format works identically in Bruno Desktop and `bru` CLI.

## Setup (Desktop — recommended for day-to-day)

1. Download and install [Bruno Desktop](https://www.usebruno.com/downloads)
2. **File → Open Collection** → select the `bruno/` directory in this repo
3. In the **Environments** panel (right sidebar), select the `local` environment
4. Ensure `baseUrl` is set to `http://127.0.0.1:8000` — adjust if using HTTPS
5. Run `auth/1-register.bru` then `auth/2-login.bru` first — the post-response script auto-sets the `token` variable

No CLI install needed for exploration. The Desktop app auto-generates `token` and `source_id` env vars via post-response scripts (same as the CLI runner).

## Run all collections (CI / automated smoke test)

```bash
just up
just api-test
```

This runs `auth`, `ops`, `sources`, `contracts`, `scorecards`, `websocket` collections headlessly. All requests should return 2xx; exit code is 0 on success.

## Run a single collection (CLI)

```bash
cd bruno && bru run sources --env local --env-var "baseUrl=http://127.0.0.1:8000"
cd bruno && bru run scorecards --env local --env-var "baseUrl=http://127.0.0.1:8000"
```

## Environment variables

Defined in [bruno/environments/local.bru](../../bruno/environments/local.bru).

| Variable | Default | Description |
|----------|---------|-------------|
| `baseUrl` | `http://127.0.0.1:8000` | Ingestor base URL |
| `token` | _(auto-set by login)_ | Bearer token |
| `source_id` | `1` | Source ID used by get/patch/contracts/scorecards |

Bruno Desktop: edit in **Environments** sidebar → pencil icon on `local`.
CLI: override with `--env-var source_id=3`.

## Collections

| Collection | Requests | Endpoints |
|------------|----------|-----------|
| `auth` | 4 | register, login, me, refresh |
| `sources` | 4 | GET list, POST create, GET by ID, PATCH deactivate |
| `contracts` | 3 | POST snapshot, GET snapshots, GET drift events |
| `scorecards` | 2 | GET list, GET by source |
| `ops` | 2 | health, readyz |
| `websocket` | 1 (smoke) | GET `/health` — see notes for wscat usage |

## Adding a new request

**Desktop:** Right-click a collection folder → **New Request** → fill the form (URL, method, auth, body). Bruno writes the `.bru` file automatically.

**CLI/file:** Create a `.bru` file in the relevant collection directory. Use an existing file as a template; set `seq` to control run order.

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

Bruno does not support WebSocket connections. Use wscat:

```bash
npm install -g wscat
wscat -c "ws://127.0.0.1:8000/ws/observations/stream"
```

Or open the Streamlit dashboard for a browser-based live tail:

```bash
uv run streamlit run services/dashboard/streamlit_app.py
```

## CI integration

```yaml
- name: Test API with Bruno
  run: |
    npm install -g @usebruno/cli
    just up
    cd bruno && bru run . -r --env local --env-var "baseUrl=http://127.0.0.1:8000"
    just down
```
