"""Integration tests for the Source Registry API endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from services.ingestor.api_schemas.source_registry import SourceHealthResponse


# ---------------------------------------------------------------------------
# Test fixtures / payloads
# ---------------------------------------------------------------------------
_SOURCE: dict[str, Any] = {
    "name": "test-weather-api",
    "url": "https://api.example.com/weather",
    "source_type": "rest",
    "description": "Test weather source.",
    "auth_policy": {"type": "apikey", "header": "X-Api-Key"},
    "quota_per_minute": 60,
    "cost_per_call_usd": 0.001,
    "expected_schema_version": "2.5",
    "sla_ms": 800,
    "tags": ["Weather", "Test"],
    "owner_team": "data-platform",
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
        assert body["source_type"] == "rest"
        assert isinstance(body["id"], int)

    async def test_tags_lowercased(self, client: AsyncClient) -> None:
        """Tags are normalised to lowercase on creation."""
        response = await client.post("/api/v1/sources", json=_SOURCE)
        assert response.status_code == 201
        assert response.json()["tags"] == ["weather", "test"]

    async def test_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """Registering the same name twice returns 409 Conflict."""
        await client.post("/api/v1/sources", json=_SOURCE)
        response = await client.post("/api/v1/sources", json=_SOURCE)
        assert response.status_code == 409

    async def test_missing_required_field_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Omitting a required field returns 422 Unprocessable Entity."""
        payload = {k: v for k, v in _SOURCE.items() if k != "source_type"}
        response = await client.post("/api/v1/sources", json=payload)
        assert response.status_code == 422

    async def test_invalid_source_type_returns_422(self, client: AsyncClient) -> None:
        """An unknown source_type value returns 422."""
        payload = {**_SOURCE, "name": "bad-type-source", "source_type": "ftp"}
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

    async def test_filter_by_source_type(self, client: AsyncClient) -> None:
        """Filtering by source_type returns only matching sources."""
        await client.post("/api/v1/sources", json=_SOURCE)
        webhook = {**_SOURCE, "name": "webhook-source", "source_type": "webhook"}
        await client.post("/api/v1/sources", json=webhook)

        response = await client.get("/api/v1/sources?source_type=webhook")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["source_type"] == "webhook"

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
        assert body["total_estimated_cost_per_minute_usd"] == 0.0

    async def test_summary_after_registration(self, client: AsyncClient) -> None:
        """Summary reflects registered source counts and type breakdown."""
        await client.post("/api/v1/sources", json=_SOURCE)
        response = await client.get("/api/v1/sources/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total_sources"] == 1
        assert body["active_sources"] == 1
        assert body["sources_by_type"]["rest"] == 1
        # cost = 0.001 * 60
        assert body["total_estimated_cost_per_minute_usd"] == pytest.approx(0.06)


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
        """Patching sla_ms updates only that field."""
        create_resp = await client.post("/api/v1/sources", json=_SOURCE)
        source_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/sources/{source_id}", json={"sla_ms": 1200}
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["sla_ms"] == 1200
        # Other fields unchanged
        assert patch_resp.json()["name"] == "test-weather-api"

    async def test_patch_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """Patching a nonexistent source returns 404."""
        response = await client.patch("/api/v1/sources/999999", json={"sla_ms": 500})
        assert response.status_code == 404


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
            url="https://api.example.com/weather",
            reachable=True,
            status_code=200,
            latency_ms=120.5,
            sla_ms=800,
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
            url="https://api.example.com/weather",
            reachable=False,
            status_code=None,
            latency_ms=10001.0,
            sla_ms=800,
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
