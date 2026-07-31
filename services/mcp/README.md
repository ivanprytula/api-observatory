# MCP server — `services/mcp/`

Exposes the observatory's source/scorecard/drift-event/agent-run toolset as
[MCP](https://modelcontextprotocol.io) tools for LLM clients (Claude Desktop,
or any MCP-compatible client) — Phase 5 of
`docs/.plans/ai-augmented-observatory-agent-mcp.md`.

Built on [FastMCP](https://gofastmcp.com). Talks to the ingestor's real HTTP
API over `httpx`, authenticated as a dedicated `mcp-service` account — it does
not import the ingestor's internals, and never bypasses its JWT auth.

## One-time setup

1. Start the ingestor (`just dev-up`, or
   `uv run uvicorn services.ingestor.main:app --port 8000` for a lighter loop). The MCP process is
   local stdio only; it is not a Compose service.
2. Create the ignored MCP configuration, restrict it to your user, and choose a strong local
   password:
   ```bash
   cp services/mcp/.env.example services/mcp/.env
   chmod 600 services/mcp/.env
   ```
   Edit `services/mcp/.env`:
   ```dotenv
   INGESTOR_URL=http://localhost:8000
   MCP_SERVICE_USERNAME=mcp-service
   MCP_SERVICE_PASSWORD=<choose-a-strong-password>
   ```
3. Register the service account (idempotent — safe to re-run) in a subshell. The password stays
   out of shell history and the parent shell remains unchanged:
   ```bash
   (
     set -a
     source services/mcp/.env
     set +a
     uv run python scripts/register_mcp_service_user.py
   )
   ```

## Run it

```bash
uv run python -m services.mcp.main
```

Runs over stdio by default and blocks until the client (or you, via Ctrl+C)
disconnects — this is expected; it's not a long-running network server in v1.
It reads the same ignored `services/mcp/.env` file automatically.

## Connect Claude Desktop

Add to Claude Desktop's `claude_desktop_config.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "api-observatory": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/api-observatory",
        "python",
        "-m",
        "services.mcp.main"
      ]
    }
  }
}
```

Restart Claude Desktop and confirm `api-observatory` shows as connected with
its 11 tools listed. Try a query that chains multiple tools, e.g. *"Which
registered source has the worst uptime, and has its contract drifted
recently?"*

## Tests

```bash
uv run pytest services/mcp/tests/ -v
```

No database, no testcontainers — everything is mocked at the `httpx`
transport boundary via `respx` (this service holds no state of its own).
