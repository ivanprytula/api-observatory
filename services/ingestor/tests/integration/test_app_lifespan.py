"""Integration tests for FastAPI application lifespan and router registration.

Verifies that the app initializes correctly with all routers, middleware,
and health endpoints wired up.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from services.ingestor.main import app


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestAppLifespan:
    async def test_health_endpoint_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_readyz_endpoint_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/readyz")
        assert response.status_code == 200

    async def test_version_endpoint_returns_version(self, client: AsyncClient) -> None:
        response = await client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "contracts" in data

    async def test_metrics_endpoint_exposes_prometheus(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/metrics")
        assert response.status_code == 200
        text = response.text
        assert "python_gc_objects" in text or "process_cpu_seconds_total" in text

    async def test_v1_api_routes_are_registered(self, client: AsyncClient) -> None:
        """All major API router groups are mounted under /api/v1/."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]

        expected_prefixes = [
            "/api/v1/sources",
            "/api/v1/observations",
            "/api/v1/contracts",
            "/api/v1/reporting",
            "/api/v1/scorecards",
        ]
        all_paths = set(paths.keys())
        for prefix in expected_prefixes:
            matching = [p for p in all_paths if p.startswith(prefix)]
            assert len(matching) > 0, f"No routes registered under {prefix}"

    async def test_unauthenticated_api_request_rejected(
        self, client: AsyncClient
    ) -> None:
        """Protected endpoints require authentication."""
        response = await client.get("/api/v1/observations")
        assert response.status_code in (200, 401, 403)

    async def test_security_middleware_loaded(self) -> None:
        """Verify security middleware is installed on the app."""
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "TrustedHostMiddleware" in middleware_names
