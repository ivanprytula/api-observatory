"""Run the MCP server with the selected transport.

Transport defaults to stdio for local clients. Set ``MCP_TRANSPORT`` to a
supported network transport when an always-on service is required.
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
