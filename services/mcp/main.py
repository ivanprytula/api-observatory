"""Entrypoint: `uv run python -m services.mcp.main`.

Transport defaults to stdio (how Claude Desktop and most local MCP clients
connect — see services/mcp/README.md). Set MCP_TRANSPORT=streamable-http (and
add a docker-compose service on port 8006) to run this as an always-on
network service instead — no code change needed, just the transport switch.
"""

from __future__ import annotations

import os

from services.mcp.server import mcp


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))
