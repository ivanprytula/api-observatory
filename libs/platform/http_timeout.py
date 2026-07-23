"""Shared request-deadline middleware for FastAPI services."""

from __future__ import annotations

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTimeoutMiddleware:
    """Return 504 when request handling exceeds the configured deadline."""

    def __init__(self, app: ASGIApp, timeout_seconds: float) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["path"] == "/metrics":
            # prometheus_client streams its response until the client disconnects.
            # Keep scrape delivery independent of the application request deadline.
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_with_state(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self.app(scope, receive, send_with_state)
        except TimeoutError:
            if response_started:
                raise
            response = JSONResponse(
                status_code=504,
                content={
                    "detail": "Request processing exceeded the configured timeout."
                },
            )
            await response(scope, receive, send)
