"""Integration tests for the Source Registry API endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from services.ingestor.api_schemas.source_registry import SourceHealthResponse


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Test fixtures / payloads
# ---------------------------------------------------------------------------
_SOURCE: dict[str, Any] = {
    "name": "test-weather-api",
    "base_url": "https://1.1.1.1",
    "health_check_path": "/weather",
    "probe_interval_seconds": 60,
    "is_active": True,
}


# ---------------------------------------------------------------------------
# POST /api/v1/sources
# ---------------------------------------------------------------------------
class TestRegisterSource:
    """POST /api/v1/sources — register a new source profile."""

    async def test_create_returns_201(self, client: AsyncClient) -> None:
        """Successful registration returns 201 and the profile id."""
        response = await client.post("/api/v1/sources", json=_SOURCE)
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "test-weather-api"
        assert body["base_url"] == "https://1.1.1.1/"
        assert isinstance(body["id"], int)

    async def test_http_scheme_rejected(self, client: AsyncClient) -> None:
        """Non-HTTPS base URLs are rejected for SSRF safety."""
        response = await client.post(
            "/api/v1/sources",
            json={
                **_SOURCE,
                "name": "insecure-source",
                "base_url": "http://example.com",
            },
        )
        assert response.status_code == 422

    async def test_private_network_rejected(self, client: AsyncClient) -> None:
        """Private/local resolved destinations are rejected."""
        response = await client.post(
            "/api/v1/sources",
            json={**_SOURCE, "name": "local-source", "base_url": "https://localhost"},
        )
        assert response.status_code == 422

    async def test_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """Registering the same name twice returns 409 Conflict."""
        await client.post("/api/v1/sources", json=_SOURCE)
        response = await client.post("/api/v1/sources", json=_SOURCE)
        assert response.status_code == 409

    async def test_missing_required_field_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Omitting a required field returns 422 Unprocessable Entity."""
        payload = {k: v for k, v in _SOURCE.items() if k != "base_url"}
        response = await client.post("/api/v1/sources", json=payload)
        assert response.status_code == 422

    async def test_invalid_health_path_returns_422(self, client: AsyncClient) -> None:
        """Health check path must start with slash."""
        payload = {**_SOURCE, "name": "bad-path-source", "health_check_path": "status"}
        response = await client.post("/api/v1/sources", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/sources
# ---------------------------------------------------------------------------
class TestListSources:
    """GET /api/v1/sources — list with optional filters."""

    async def test_empty_list(self, client: AsyncClient) -> None:
        """Empty registry returns an empty items list with total=0."""
        response = await client.get("/api/v1/sources")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_returns_registered_source(self, client: AsyncClient) -> None:
        """A registered source appears in the list."""
        await client.post("/api/v1/sources", json=_SOURCE)
        response = await client.get("/api/v1/sources")
        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_limit_offset_pagination(self, client: AsyncClient) -> None:
        """List endpoint applies limit/offset pagination."""
        await client.post("/api/v1/sources", json=_SOURCE)
        await client.post(
            "/api/v1/sources",
            json={
                **_SOURCE,
                "name": "second-source",
                "base_url": "https://example.org",
            },
        )

        response = await client.get("/api/v1/sources?offset=0&limit=1")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 1

    async def test_filter_by_is_active(self, client: AsyncClient) -> None:
        """Filtering by is_active=true excludes deactivated sources."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        # Deactivate the source
        await client.delete(f"/api/v1/sources/{source_id}")

        # Filter active only — should return nothing
        response = await client.get("/api/v1/sources?is_active=true")
        assert response.status_code == 200
        assert response.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/sources/summary
# ---------------------------------------------------------------------------
class TestSourceSummary:
    """GET /api/v1/sources/summary — aggregate statistics."""

    async def test_empty_summary(self, client: AsyncClient) -> None:
        """Empty registry returns zeroed summary."""
        response = await client.get("/api/v1/sources/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total_sources"] == 0
        assert body["active_sources"] == 0
        assert body["avg_probe_interval_seconds"] is None

    async def test_summary_after_registration(self, client: AsyncClient) -> None:
        """Summary reflects registered source counts and type breakdown."""
        await client.post("/api/v1/sources", json=_SOURCE)
        response = await client.get("/api/v1/sources/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total_sources"] == 1
        assert body["active_sources"] == 1
        assert body["avg_probe_interval_seconds"] == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# GET /api/v1/sources/{source_id}
# ---------------------------------------------------------------------------
class TestGetSource:
    """GET /api/v1/sources/{source_id} — fetch by ID."""

    async def test_get_existing_source(self, client: AsyncClient) -> None:
        """Fetching an existing source returns 200 with correct data."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        response = await client.get(f"/api/v1/sources/{source_id}")
        assert response.status_code == 200
        assert response.json()["id"] == source_id

    async def test_get_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """Fetching a nonexistent source returns 404."""
        response = await client.get("/api/v1/sources/999999")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/sources/{source_id}
# ---------------------------------------------------------------------------
class TestPatchSource:
    """PATCH /api/v1/sources/{source_id} — partial update."""

    async def test_patch_updates_field(self, client: AsyncClient) -> None:
        """Patching probe interval updates only that field."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/sources/{source_id}", json={"probe_interval_seconds": 120}
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["probe_interval_seconds"] == 120
        # Other fields unchanged
        assert patch_resp.json()["name"] == "test-weather-api"

    async def test_patch_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """Patching a nonexistent source returns 404."""
        response = await client.patch(
            "/api/v1/sources/999999", json={"probe_interval_seconds": 120}
        )
        assert response.status_code == 404

    async def test_patch_private_url_rejected(self, client: AsyncClient) -> None:
        """Patch rejects private/local target URLs."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/v1/sources/{source_id}",
            json={"base_url": "https://localhost"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/sources/{source_id}
# ---------------------------------------------------------------------------
class TestDeleteSource:
    """DELETE /api/v1/sources/{source_id} — soft delete."""

    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        """Deleting an existing source returns 204 No Content."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        response = await client.delete(f"/api/v1/sources/{source_id}")
        assert response.status_code == 204

    async def test_delete_is_idempotent(self, client: AsyncClient) -> None:
        """Deleting an already deleted source returns 204."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        first = await client.delete(f"/api/v1/sources/{source_id}")
        second = await client.delete(f"/api/v1/sources/{source_id}")
        assert first.status_code == 204
        assert second.status_code == 204

    async def test_deleted_source_not_retrievable(self, client: AsyncClient) -> None:
        """A deleted source returns 404 on subsequent GET."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        await client.delete(f"/api/v1/sources/{source_id}")
        response = await client.get(f"/api/v1/sources/{source_id}")
        assert response.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """Deleting a nonexistent source returns 404."""
        response = await client.delete("/api/v1/sources/999999")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/sources/{source_id}/health
# ---------------------------------------------------------------------------
class TestSourceHealth:
    """GET /api/v1/sources/{source_id}/health — live probe (mocked)."""

    async def test_health_probe_reachable(self, client: AsyncClient) -> None:
        """Mocked reachable probe returns reachable=True and latency."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        mock_result = SourceHealthResponse(
            source_id=source_id,
            target_url="https://api.example.com/weather",
            reachable=True,
            status_code=200,
            latency_ms=120.5,
            sla_breach=False,
            error=None,
        )
        with patch(
            "services.ingestor.routers.source_registry.probe_source_health",
            new=AsyncMock(return_value=mock_result),
        ):
            response = await client.get(f"/api/v1/sources/{source_id}/health")

        assert response.status_code == 200
        body = response.json()
        assert body["reachable"] is True
        assert body["status_code"] == 200
        assert body["sla_breach"] is False

    async def test_health_probe_unreachable(self, client: AsyncClient) -> None:
        """Mocked unreachable probe returns reachable=False with error."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        mock_result = SourceHealthResponse(
            source_id=source_id,
            target_url="https://api.example.com/weather",
            reachable=False,
            status_code=None,
            latency_ms=10001.0,
            sla_breach=True,
            error="Connection refused",
        )
        with patch(
            "services.ingestor.routers.source_registry.probe_source_health",
            new=AsyncMock(return_value=mock_result),
        ):
            response = await client.get(f"/api/v1/sources/{source_id}/health")

        assert response.status_code == 200
        body = response.json()
        assert body["reachable"] is False
        assert body["sla_breach"] is True
        assert "Connection refused" in body["error"]

    async def test_health_nonexistent_source_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Health probe for a nonexistent source returns 404."""
        response = await client.get("/api/v1/sources/999999/health")
        assert response.status_code == 404
