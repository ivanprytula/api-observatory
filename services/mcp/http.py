"""Shared httpx client for calls to the ingestor API.

Mirrors `services.ingestor.fetch.get_http_client()`: one `AsyncClient` per
running event loop, so a client created on one loop is never reused (and
never closed) from another — safe for both the long-running stdio server and
per-test event loops.
"""

from __future__ import annotations

import asyncio

import httpx


_http_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}


async def get_http_client() -> httpx.AsyncClient:
    """Return an `AsyncClient` associated with the current running event loop."""
    loop = asyncio.get_running_loop()
    client = _http_clients.get(loop)
    if client is not None:
        return client

    client = httpx.AsyncClient()
    _http_clients[loop] = client
    return client


async def close_http_client() -> None:
    """Close the `AsyncClient` associated with the current running event loop."""
    loop = asyncio.get_running_loop()
    client = _http_clients.pop(loop, None)
    if client is not None:
        await client.aclose()
