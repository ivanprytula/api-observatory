"""HTTP transport layer — singleton client with auth injection and retry.

Two classes:
  - SyncClient  — synchronous (httpx.Client) for Streamlit
  - AsyncClient — async (httpx.AsyncClient) for Dash / React / uvicorn

Use via the module-level singleton::

    from services.dashboard.core.http_client import sync_client
    data = sync_client.request("GET", "/api/v1/sources", token="...")

Resource classes (Layer 2) wrap these for typed access.
"""

from __future__ import annotations

from typing import Any

import httpx

from services.dashboard.core.config import config


class SyncClient:
    """Synchronous HTTP client with auto-injected auth header."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    @property
    def base_url(self) -> str:
        return self._base_url

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str = "",
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"{self._base_url}{path}"
        r = self._client.request(method, url, headers=headers, json=json, params=params)
        r.raise_for_status()
        return r.json()

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        token: str = "",
        **kwargs: Any,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"{self._base_url}{path}"
        return self._client.request(method, url, headers=headers, **kwargs)

    def close(self) -> None:
        self._client.close()


class AsyncClient:
    """Async HTTP client with auto-injected auth header."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str = "",
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"{self._base_url}{path}"
        r = await self._client.request(
            method, url, headers=headers, json=json, params=params
        )
        r.raise_for_status()
        return r.json()

    async def request_raw(
        self,
        method: str,
        path: str,
        *,
        token: str = "",
        **kwargs: Any,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"{self._base_url}{path}"
        return await self._client.request(method, url, headers=headers, **kwargs)

    async def close(self) -> None:
        await self._client.aclose()


# Module-level singletons — one per process.
sync_client = SyncClient(config.api_base_url, timeout=config.request_timeout)
async_client = AsyncClient(config.api_base_url, timeout=config.request_timeout)
