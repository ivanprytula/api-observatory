"""RLS (Row-Level Security) integration test for tenant isolation.

Proves that PostgreSQL RLS correctly isolates observations between different tenant IDs.
Requires DATABASE_URL_TEST set to a PostgreSQL instance.

Note: No @pytest.mark.asyncio — asyncio_mode='auto' is set in pyproject.toml.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


async def test_tenant_isolation_rls(db: AsyncSession, client: AsyncClient) -> None:
    """Proves that RLS correctly isolates observations between tenants.

    1. Injects observations for Tenant 1 and Tenant 2 directly into DB.
    2. Verifies Tenant 1 can only see their own observations via API.
    3. Verifies Tenant 2 can only see their own observations via API.

    Skipped if running against SQLite (RLS is PostgreSQL-only).
    """
    # Skip if using SQLite
    import os

    db_url = os.environ.get("DATABASE_URL_TEST", "sqlite+aiosqlite:///:memory:")
    if "sqlite" in db_url:
        pytest.skip("RLS test requires PostgreSQL")
    # 1. Setup: Insert observations for two different tenants
    # Clear existing observations to ensure clean test
    await db.execute(text("DELETE FROM observations"))

    # Tenant 1 observation
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES (:source, :ts, :data, :tags, :tid, :now, false)"
        ),
        {
            "source": "tenant1_private",
            "ts": datetime(2026, 5, 1, 10, 0, tzinfo=None),
            "data": "{}",
            "tags": "[]",
            "tid": 1,
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    )

    # Tenant 2 observation
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES (:source, :ts, :data, :tags, :tid, :now, false)"
        ),
        {
            "source": "tenant2_private",
            "ts": datetime(2026, 5, 1, 11, 0, tzinfo=None),
            "data": "{}",
            "tags": "[]",
            "tid": 2,
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    )

    # Global observation (no tenant_id)
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES (:source, :ts, :data, :tags, NULL, :now, false)"
        ),
        {
            "source": "global_public",
            "ts": datetime(2026, 5, 1, 12, 0, tzinfo=None),
            "data": "{}",
            "tags": "[]",
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    )
    await db.commit()

    # 2. Test: Access as Tenant 1
    resp1 = await client.get("/api/v1/observations", headers={"X-Tenant-ID": "1"})
    assert resp1.status_code == 200
    recs1 = resp1.json()["observations"]
    sources1 = [r["source"] for r in recs1]

    assert "tenant1_private" in sources1
    assert "global_public" in sources1
    assert "tenant2_private" not in sources1, "Tenant 1 should NOT see Tenant 2's data"

    # 3. Test: Access as Tenant 2
    resp2 = await client.get("/api/v1/observations", headers={"X-Tenant-ID": "2"})
    assert resp2.status_code == 200
    recs2 = resp2.json()["observations"]
    sources2 = [r["source"] for r in recs2]

    assert "tenant2_private" in sources2
    assert "global_public" in sources2
    assert "tenant1_private" not in sources2, "Tenant 2 should NOT see Tenant 1's data"

    # 4. Test: Access without Tenant ID
    resp0 = await client.get("/api/v1/observations")
    assert resp0.status_code == 200
    recs0 = resp0.json()["observations"]
    sources0 = [r["source"] for r in recs0]

    assert "global_public" in sources0
    assert "tenant1_private" not in sources0
    assert "tenant2_private" not in sources0

    # 5. Test: Analytics Tenant Status (No WHERE clause in code)
    resp_stats = await client.get(
        "/api/v1/analytics/tenant-status", headers={"X-Tenant-ID": "1"}
    )
    assert resp_stats.status_code == 200
    data = resp_stats.json()
    assert data["active_tenant_id"] == 1
    # Should see 1 private + 1 global = 2
    assert data["observation_count"] == 2


@pytest.mark.postgresonly
async def test_token_based_rls_isolation(db: AsyncSession, client: AsyncClient):
    """Verifies that RLS isolation works when tenant is derived from JWT token.

    1. Registers a user with tenant_id=5.
    2. Logs in to get a token.
    3. Verifies that the token automatically scopes data to tenant 5.
    """
    # 1. Setup
    username = "tenant5_user"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": "t5@example.com",
            "password": "securepassword123",
            "tenant_id": 5,
        },
    )
    assert registration.status_code == 201, registration.text
    # Public registration deliberately ignores caller-supplied tenant assignment.
    # Model the administrator-assignment step before issuing a tenant-scoped token.
    await db.execute(
        text("UPDATE users SET tenant_id = 5 WHERE username = :username"),
        {"username": username},
    )
    await db.commit()

    # 2. Ingest some data for tenant 5 and tenant 6
    await db.execute(text("DELETE FROM observations"))
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES ('t5_data', :now, '{}', '[]', 5, :now, false)"
        ),
        {"now": datetime.now(UTC).replace(tzinfo=None)},
    )
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES ('t6_data', :now, '{}', '[]', 6, :now, false)"
        ),
        {"now": datetime.now(UTC).replace(tzinfo=None)},
    )
    await db.commit()

    # 3. Login
    login_resp = await client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": "securepassword123"},
    )
    token = login_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 4. Verify isolation (WITHOUT X-Tenant-ID header)
    resp = await client.get("/api/v1/observations", headers=auth_headers)
    assert resp.status_code == 200
    recs = resp.json()["observations"]
    sources = [r["source"] for r in recs]

    assert "t5_data" in sources
    assert "t6_data" not in sources, (
        "Token-based RLS should hide tenant 6 data even if no header is sent"
    )

    # 5. Verify tenant-status
    resp_stats = await client.get(
        "/api/v1/analytics/tenant-status", headers=auth_headers
    )
    assert resp_stats.json()["active_tenant_id"] == 5
    assert resp_stats.json()["observation_count"] == 1


@pytest.mark.postgresonly
async def test_admin_rls_bypass(db: AsyncSession, client: AsyncClient):
    """Verifies that an Admin can bypass RLS to see all tenant data.

    1. Registers an admin user.
    2. Logs in.
    3. Verifies they see observations from all tenants.
    """
    # 1. Setup Admin
    username = "super_admin"
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": "admin@example.com",
            "password": "adminpassword123",
        },
    )
    # Manually promote to admin in DB (since register defaults to viewer)
    await db.execute(
        text("UPDATE users SET role = 'admin' WHERE username = :u"), {"u": username}
    )
    await db.commit()

    # 2. Setup Data (Tenant 10 and 11)
    await db.execute(text("DELETE FROM observations"))
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES ('t10_data', :now, '{}', '[]', 10, :now, false)"
        ),
        {"now": datetime.now(UTC).replace(tzinfo=None)},
    )
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, tenant_id, "
            "created_at, processed) VALUES ('t11_data', :now, '{}', '[]', 11, :now, false)"
        ),
        {"now": datetime.now(UTC).replace(tzinfo=None)},
    )
    await db.commit()

    # 3. Login as Admin
    login_resp = await client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": "adminpassword123"},
    )
    token = login_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 4. Verify bypass
    resp = await client.get("/api/v1/observations", headers=auth_headers)
    assert resp.status_code == 200
    recs = resp.json()["observations"]
    sources = [r["source"] for r in recs]

    assert "t10_data" in sources
    assert "t11_data" in sources, (
        "Admin should see data from all tenants (bypass active)"
    )

    # 5. Verify tenant-status
    resp_stats = await client.get(
        "/api/v1/analytics/tenant-status", headers=auth_headers
    )
    assert resp_stats.status_code == 200
    data = resp_stats.json()
    print(f"DEBUG: Tenant Status: {data}")
    # The observation count should be 2 because admin bypasses isolation
    assert data["observation_count"] == 2
