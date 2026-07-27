"""Tests for the shared HTTP request deadline middleware."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from libs.platform.http_timeout import RequestTimeoutMiddleware


async def test_request_timeout_returns_504_and_cancels_handler() -> None:
    cancelled = asyncio.Event()
    app = FastAPI()
    app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=0.01)

    @app.get("/slow")
    async def slow() -> dict[str, str]:
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()
        return {"status": "unreachable"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/slow")

    assert response.status_code == 504
    assert response.json() == {
        "detail": "Request processing exceeded the configured timeout."
    }
    assert cancelled.is_set()
