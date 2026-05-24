"""Integration tests for v2 JWT + RBAC endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.shared.payloads import RECORD_API


@pytest.mark.integration
async def test_v2_jwt_create_requires_writer_or_admin_role(client: AsyncClient) -> None:
    """JWT writer role is accepted for /api/v2/records/jwt."""
    token_resp = await client.post("/api/v2/records/token", params={"user_id": "alice"})
    assert token_resp.status_code == 200

    token = token_resp.json()["access_token"]
    create_resp = await client.post(
        "/api/v2/records/jwt",
        json=RECORD_API,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201


@pytest.mark.integration
async def test_v2_jwt_create_denies_viewer_role(client: AsyncClient) -> None:
    """JWT viewer role is rejected with 403 on write endpoint."""
    import services.ingestor.auth as auth_module

    viewer_token = auth_module.create_jwt_token("viewer", {"roles": ["viewer"]})
    response = await client.post(
        "/api/v2/records/jwt",
        json=RECORD_API,
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 403
