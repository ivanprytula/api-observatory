"""Entrypoint: `uv run python -m services.mcp.main`.

Transport defaults to stdio (how Claude Desktop and most local MCP clients
connect — see services/mcp/README.md). Set MCP_TRANSPORT=streamable-http (and
add a docker-compose service on port 8006) to run this as an always-on
network service instead — no code change needed, just the transport switch.
"""

from __future__ import annotations

import os
from typing import Literal, cast

from services.mcp.server import mcp


type MCPTransport = Literal["stdio", "http", "sse", "streamable-http"]


def _transport_from_environment() -> MCPTransport:
    configured = os.environ.get("MCP_TRANSPORT", "stdio")
    supported = {"stdio", "http", "sse", "streamable-http"}
    if configured not in supported:
        raise ValueError(
            f"Unsupported MCP_TRANSPORT={configured!r}; expected one of {sorted(supported)}"
        )
    return cast(MCPTransport, configured)


if __name__ == "__main__":
    mcp.run(transport=_transport_from_environment())
