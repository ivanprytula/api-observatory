"""Regression coverage for the production-v1 and opt-in-learning boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.auth import create_jwt_token, verify_jwt_token
from services.ingestor.main import app
from services.ingestor.models import Observation
from services.ingestor.security.api_keys import verify_api_key


pytestmark = pytest.mark.integration


_OBSERVATION_PAYLOAD = {
    "source": "phase4-auth",
    "timestamp": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
    "data": {"value": 1},
    "tags": ["phase4"],
}


@contextmanager
def _without_test_jwt_override() -> Iterator[None]:
    """Temporarily exercise the real missing-token dependency path."""
    saved = app.dependency_overrides.pop(verify_jwt_token, None)
    try:
        yield
    finally:
        if saved is not None:
            app.dependency_overrides[verify_jwt_token] = saved


async def test_v1_analytics_rejects_anonymous_request(client: AsyncClient) -> None:
    """A mounted v1 business route must deny callers without a JWT."""
    with _without_test_jwt_override():
        response = await client.get("/api/v1/analytics/summary")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


async def test_v1_admin_operation_rejects_viewer(
    client: AsyncClient,
) -> None:
    """A valid viewer JWT cannot run an administrative operation."""
    previous = app.dependency_overrides.get(verify_jwt_token)

    async def _viewer_claims() -> dict[str, Any]:
        return {"sub": "viewer", "roles": ["viewer"]}

    app.dependency_overrides[verify_jwt_token] = _viewer_claims
    try:
        response = await client.post("/api/v1/analytics/refresh-materialized-view")
    finally:
        if previous is None:
            app.dependency_overrides.pop(verify_jwt_token, None)
        else:
            app.dependency_overrides[verify_jwt_token] = previous

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role permissions"


async def test_v1_token_bucket_admits_authorized_observation_create(
    client: AsyncClient,
) -> None:
    """The production v1 write path exposes token-bucket response headers."""
    response = await client.post("/api/v1/observations", json=_OBSERVATION_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["source"] == "phase4-auth"
    assert response.headers["X-RateLimit-Strategy"] == "token-bucket"
    assert response.headers["X-RateLimit-Remaining"]


async def test_jwt_tenant_claim_beats_conflicting_header(
    client: AsyncClient, db: AsyncSession
) -> None:
    """An untrusted header cannot override a verified JWT tenant claim."""
    token = create_jwt_token("tenant-user", {"roles": ["writer"], "tenant_id": 7})
    with _without_test_jwt_override():
        response = await client.post(
            "/api/v1/observations",
            json={**_OBSERVATION_PAYLOAD, "source": "tenant-claim"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-ID": "999",
            },
        )

    assert response.status_code == 201
    observation = await db.scalar(
        select(Observation).where(Observation.id == response.json()["id"])
    )
    assert observation is not None
    assert observation.tenant_id == 7


async def test_public_registration_creates_viewer_with_personal_tenant(
    client: AsyncClient,
) -> None:
    """Public signup always creates an unassigned viewer account with auto-provisioned tenant."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "phase4-viewer",
            "email": "phase4-viewer@example.com",
            "password": "safe-password-123",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "viewer"
    assert response.json()["tenant_id"] is not None


def test_default_route_inventory_excludes_opt_in_features() -> None:
    """The default app has no learning-lab or unavailable Mongo surface."""
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert "/api/v2/observations/token-bucket" not in paths
    assert "/api/v1/observations/auth/login" not in paths
    assert "/api/v1/scrape/{source}" not in paths
    assert "/api/v1/mongo/ingestion-volume" not in paths


def _has_auth_dependency(route: APIRoute) -> bool:
    """Return whether a route's dependency tree reaches an auth verifier."""
    verifiers = {verify_jwt_token, verify_api_key}

    def _walk(dependencies: list[Any]) -> bool:
        for dependency in dependencies:
            if dependency.call in verifiers or _walk(dependency.dependencies):
                return True
        return False

    return _walk(route.dependant.dependencies)


def test_default_v1_routes_are_authenticated_except_auth_bootstrap() -> None:
    """New production v1 handlers cannot silently become anonymous."""
    public_paths = {
        "/api/v1/auth/register",
        "/api/v1/auth/token",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    }
    unprotected = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/v1/")
        and route.path not in public_paths
        and not _has_auth_dependency(route)
    ]

    assert unprotected == []
