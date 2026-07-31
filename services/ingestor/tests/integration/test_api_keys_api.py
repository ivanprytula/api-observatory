"""Integration tests for /api/v1/api-keys endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.integration


_VALID_PAYLOAD = {
    "name": "test-key",
    "tenant_id": 42,
    "scopes": ["observations:read", "sources:read"],
    "expires_at": None,
}


# ---------------------------------------------------------------------------
# POST /api/v1/api-keys — create
# ---------------------------------------------------------------------------


async def test_create_api_key_returns_201(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert "full_key" in body
    assert body["full_key"].startswith("dpak_")
    assert body["name"] == "test-key"
    assert body["tenant_id"] == 42
    assert body["is_active"] is True
    assert set(body["scopes"]) == {"observations:read", "sources:read"}
    assert "key_prefix" in body
    # full_key prefix portion should match stored prefix
    assert body["full_key"][5:13] == body["key_prefix"]


async def test_create_api_key_without_tenant(client: AsyncClient) -> None:
    payload = {**_VALID_PAYLOAD, "tenant_id": None}
    resp = await client.post("/api/v1/api-keys", json=payload)
    assert resp.status_code == 201
    assert resp.json()["tenant_id"] is None


async def test_create_api_key_admin_scope(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/api-keys", json={**_VALID_PAYLOAD, "scopes": ["admin"]}
    )
    assert resp.status_code == 201


async def test_create_api_key_invalid_scope(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/api-keys", json={**_VALID_PAYLOAD, "scopes": ["invalid:scope"]}
    )
    assert resp.status_code == 422


async def test_create_api_key_missing_name(client: AsyncClient) -> None:
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "name"}
    resp = await client.post("/api/v1/api-keys", json=payload)
    assert resp.status_code == 422


async def test_create_api_key_empty_scopes(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/api-keys", json={**_VALID_PAYLOAD, "scopes": []})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/api-keys — list
# ---------------------------------------------------------------------------


async def test_list_api_keys_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/api-keys")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_api_keys_after_create(client: AsyncClient) -> None:
    await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    resp = await client.get("/api/v1/api-keys")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "test-key"


async def test_list_api_keys_filter_by_tenant(client: AsyncClient) -> None:
    await client.post("/api/v1/api-keys", json={**_VALID_PAYLOAD, "tenant_id": 1})
    await client.post("/api/v1/api-keys", json={**_VALID_PAYLOAD, "tenant_id": 2})
    resp = await client.get("/api/v1/api-keys?tenant_id=1")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["tenant_id"] == 1


async def test_list_api_keys_filter_active(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    key_id = create_resp.json()["id"]
    # revoke it
    await client.delete(f"/api/v1/api-keys/{key_id}")

    active_resp = await client.get("/api/v1/api-keys?is_active=true")
    inactive_resp = await client.get("/api/v1/api-keys?is_active=false")
    assert len(active_resp.json()) == 0
    assert len(inactive_resp.json()) == 1


# ---------------------------------------------------------------------------
# DELETE /api/v1/api-keys/{id} — revoke
# ---------------------------------------------------------------------------


async def test_revoke_api_key(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    key_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/api-keys/{key_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["is_active"] is False


async def test_revoke_nonexistent_key(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/api-keys/999999")
    assert resp.status_code == 404


async def test_revoke_is_idempotent_in_list(client: AsyncClient) -> None:
    """Revoked key remains in the list with is_active=False."""
    create_resp = await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    key_id = create_resp.json()["id"]
    await client.delete(f"/api/v1/api-keys/{key_id}")
    resp = await client.get("/api/v1/api-keys")
    assert resp.status_code == 200
    # Key still shows in the list (soft delete)
    assert any(k["id"] == key_id for k in resp.json()), resp.json()


# ---------------------------------------------------------------------------
# GET /api/v1/api-keys/scopes
# ---------------------------------------------------------------------------


async def test_list_scopes(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/api-keys/scopes")
    assert resp.status_code == 200
    scopes = resp.json()
    assert isinstance(scopes, list)
    assert "observations:read" in scopes
    assert "admin" in scopes


# ---------------------------------------------------------------------------
# full_key uniqueness
# ---------------------------------------------------------------------------


async def test_two_keys_have_different_full_keys(client: AsyncClient) -> None:
    r1 = await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    r2 = await client.post("/api/v1/api-keys", json=_VALID_PAYLOAD)
    assert r1.json()["full_key"] != r2.json()["full_key"]
