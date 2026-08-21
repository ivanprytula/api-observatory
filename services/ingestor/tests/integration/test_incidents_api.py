"""Tenant isolation and state-machine coverage for incident APIs."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.auth import get_casbin_enforcer, verify_jwt_token
from services.ingestor.main import app
from services.ingestor.models import SourceProfile
from services.ingestor.repositories.incidents import open_or_update_incident


pytestmark = pytest.mark.integration


async def _seed_incident(db: AsyncSession, *, tenant_id: int, name: str) -> int:
    source = SourceProfile(
        name=name,
        base_url="https://example.com",
        tenant_id=tenant_id,
    )
    db.add(source)
    await db.flush()
    transition = await open_or_update_incident(
        db,
        source=source,
        trigger_type="availability",
        severity="critical",
        summary=f"{name} is unavailable.",
        details={"status": 503},
    )
    await db.commit()
    return transition.incident.id


async def test_tenant_can_only_read_own_incidents(
    client: AsyncClient, db: AsyncSession
) -> None:
    own_id = await _seed_incident(db, tenant_id=10, name="tenant-ten")
    other_id = await _seed_incident(db, tenant_id=20, name="tenant-twenty")

    async def tenant_user() -> dict:
        return {"sub": "tenant-user-10", "tenant_id": 10}

    app.dependency_overrides[verify_jwt_token] = tenant_user
    response = await client.get("/api/v1/incidents")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [own_id]

    hidden = await client.get(f"/api/v1/incidents/{other_id}")
    assert hidden.status_code == 404


async def test_tenant_user_cannot_change_another_tenants_incident(
    client: AsyncClient, db: AsyncSession
) -> None:
    other_id = await _seed_incident(db, tenant_id=20, name="tenant-twenty")

    async def tenant_user() -> dict:
        return {"sub": "tenant-user-10", "tenant_id": 10}

    app.dependency_overrides[verify_jwt_token] = tenant_user
    get_casbin_enforcer().add_role_for_user_in_domain("tenant-user-10", "user", "10")
    for action in ("acknowledge", "resolve"):
        response = await client.post(f"/api/v1/incidents/{other_id}/{action}")
        assert response.status_code == 404


async def test_admin_can_read_incidents_across_tenants(
    client: AsyncClient, db: AsyncSession
) -> None:
    first_id = await _seed_incident(db, tenant_id=10, name="tenant-ten")
    second_id = await _seed_incident(db, tenant_id=20, name="tenant-twenty")

    async def admin() -> dict:
        return {"sub": "admin"}

    app.dependency_overrides[verify_jwt_token] = admin
    get_casbin_enforcer().add_role_for_user_in_domain("admin", "admin", "*")
    response = await client.get("/api/v1/incidents")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {first_id, second_id}


async def test_tenant_user_acknowledges_and_resolves_incident(
    client: AsyncClient, db: AsyncSession
) -> None:
    incident_id = await _seed_incident(db, tenant_id=30, name="tenant-thirty")

    async def tenant_user() -> dict:
        return {"sub": "tenant-user-30", "tenant_id": 30}

    app.dependency_overrides[verify_jwt_token] = tenant_user
    get_casbin_enforcer().add_role_for_user_in_domain("tenant-user-30", "user", "30")
    acknowledged = await client.post(f"/api/v1/incidents/{incident_id}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"
    assert acknowledged.json()["acknowledged_by"] == "tenant-user-30"

    resolved = await client.post(f"/api/v1/incidents/{incident_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    duplicate = await client.post(f"/api/v1/incidents/{incident_id}/resolve")
    assert duplicate.status_code == 409
