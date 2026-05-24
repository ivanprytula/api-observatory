"""Small async HTTP client wrapper that uses a CircuitBreaker.

This module provides `AsyncResilientHTTPClient` which delegates circuit
behaviour to `CircuitBreaker`. By default 5xx responses are considered failures.
The wrapper is intentionally minimal; users can supply a custom failure
predicate or a shared `CircuitBreaker` instance.
"""

from __future__ import annotations

from collections.abc import Callable

import aiohttp

from libs.platform.circuit_breaker import CircuitBreaker


class ResilientHTTPError(RuntimeError):
    def __init__(
        self, status: int, body: str | None = None, message: str | None = None
    ) -> None:
        self.status = status
        self.body = body
        super().__init__(message or f"HTTP {status}")


class AsyncResilientHTTPClient:
    """Async HTTP client that uses a `CircuitBreaker`.

    Example::

        from libs.platform.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        client = AsyncResilientHTTPClient(circuit_breaker=cb)

        resp = await client.get('https://example.local/health')
        text = await resp.text()
        await client.close()
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker | None = None,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        is_failure: Callable[[aiohttp.ClientResponse], bool] | None = None,
    ) -> None:
        self._breaker = circuit_breaker or CircuitBreaker()
        if session is None:
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owned_session = True
        else:
            self._session = session
            self._owned_session = False
        # default: treat 5xx as failure
        self._is_failure = is_failure or (lambda resp: resp.status >= 500)

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        async def do_request():
            resp = await self._session.request(method, url, **kwargs)
            if self._is_failure(resp):
                body = await resp.text()
                raise ResilientHTTPError(status=resp.status, body=body)
            return resp

        return await self._breaker.call(do_request)

    async def get(
        self, url: str, **kwargs
    ) -> aiohttp.ClientResponse:  # pragma: no cover - thin wrapper
        return await self.request("GET", url, **kwargs)

    async def post(
        self, url: str, **kwargs
    ) -> aiohttp.ClientResponse:  # pragma: no cover - thin wrapper
        return await self.request("POST", url, **kwargs)

    async def close(self) -> None:
        if getattr(self, "_owned_session", False):
            await self._session.close()
