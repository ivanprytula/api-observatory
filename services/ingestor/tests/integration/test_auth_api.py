"""Integration tests for /api/v1/auth endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGISTER_URL = "/api/v1/auth/register"
_TOKEN_URL = "/api/v1/auth/token"
_ME_URL = "/api/v1/auth/me"
_LOGOUT_URL = "/api/v1/auth/logout"
_ROLE_URL = "/api/v1/auth/users/{username}/role"

_USER: dict[str, str] = {
    "username": "testuser",
    "email": "testuser@example.com",
    "password": "s3cr3tP@ss",
}


def _form_data(username: str, password: str) -> dict[str, str]:
    return {"username": username, "password": password}


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


async def test_register_creates_user(client: AsyncClient) -> None:
    resp = await client.post(_REGISTER_URL, json=_USER)
    assert resp.status_code == 201
    data: dict[str, Any] = resp.json()
    assert data["username"] == _USER["username"]
    assert data["email"] == _USER["email"]
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


async def test_register_duplicate_username_returns_409(client: AsyncClient) -> None:
    await client.post(_REGISTER_URL, json=_USER)
    resp = await client.post(_REGISTER_URL, json=_USER)
    assert resp.status_code == 409


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await client.post(_REGISTER_URL, json=_USER)
    payload = {**_USER, "username": "different_name"}
    resp = await client.post(_REGISTER_URL, json=payload)
    assert resp.status_code == 409


async def test_register_short_password_returns_422(client: AsyncClient) -> None:
    payload = {**_USER, "password": "short"}
    resp = await client.post(_REGISTER_URL, json=payload)
    assert resp.status_code == 422


async def test_register_invalid_email_returns_422(client: AsyncClient) -> None:
    payload = {**_USER, "email": "not-an-email"}
    resp = await client.post(_REGISTER_URL, json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login / token
# ---------------------------------------------------------------------------


async def test_login_returns_jwt(client: AsyncClient) -> None:
    await client.post(_REGISTER_URL, json=_USER)
    resp = await client.post(
        _TOKEN_URL,
        data=_form_data(_USER["username"], _USER["password"]),
    )
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post(_REGISTER_URL, json=_USER)
    resp = await client.post(
        _TOKEN_URL,
        data=_form_data(_USER["username"], "wrongpassword"),
    )
    assert resp.status_code == 401


async def test_login_unknown_user_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        _TOKEN_URL,
        data=_form_data("nobody", "password"),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(_ME_URL)
    assert resp.status_code == 401


async def test_me_with_valid_token_returns_user(client: AsyncClient) -> None:
    await client.post(_REGISTER_URL, json=_USER)
    token_resp = await client.post(
        _TOKEN_URL,
        data=_form_data(_USER["username"], _USER["password"]),
    )
    token = token_resp.json()["access_token"]

    resp = await client.get(_ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()
    assert data["username"] == _USER["username"]
    assert data["email"] == _USER["email"]


async def test_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        _ME_URL, headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("session_id", [None, "some-session-uuid"])
async def test_logout_returns_204(session_id: str | None, client: AsyncClient) -> None:
    """Logout always returns 204 regardless of whether a session exists."""
    import fakeredis

    import services.ingestor.core.auth as auth_module

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch.object(auth_module, "_session_client", fake):
        cookies = {"session_id": session_id} if session_id else {}
        resp = await client.post(_LOGOUT_URL, cookies=cookies)
        assert resp.status_code == 204

    await fake.aclose()


# ---------------------------------------------------------------------------
# Role assignment (admin JWT required)
# ---------------------------------------------------------------------------


async def test_assign_role_with_admin_token(client: AsyncClient) -> None:
    """Admin JWT can promote a registered user to admin."""
    await client.post(_REGISTER_URL, json=_USER)

    resp = await client.post(
        _ROLE_URL.format(username=_USER["username"]),
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()
    assert data["role"] == "admin"
    assert data["username"] == _USER["username"]

    login = await client.post(
        _TOKEN_URL,
        data=_form_data(_USER["username"], _USER["password"]),
    )
    assert login.status_code == 200


async def test_assign_role_missing_token_returns_401(client: AsyncClient) -> None:
    """Role assignment without a JWT is rejected."""
    from services.ingestor.core.auth import verify_jwt_token
    from services.ingestor.main import app

    app.dependency_overrides.pop(verify_jwt_token, None)
    try:
        await client.post(_REGISTER_URL, json=_USER)
        resp = await client.post(
            _ROLE_URL.format(username=_USER["username"]),
            json={"role": "admin"},
        )
    finally:

        async def _mock_jwt() -> dict[str, Any]:
            return {"sub": "testuser"}

        app.dependency_overrides[verify_jwt_token] = _mock_jwt

    assert resp.status_code == 401


async def test_assign_role_non_admin_token_returns_403(client: AsyncClient) -> None:
    """A non-admin JWT is rejected for role assignment."""
    from services.ingestor.core.auth import get_casbin_enforcer, verify_jwt_token
    from services.ingestor.main import app

    async def _user_jwt() -> dict[str, Any]:
        return {"sub": "regular-user", "tenant_id": 1}

    app.dependency_overrides[verify_jwt_token] = _user_jwt
    get_casbin_enforcer().add_role_for_user_in_domain("regular-user", "user", "1")
    try:
        await client.post(_REGISTER_URL, json=_USER)
        resp = await client.post(
            _ROLE_URL.format(username=_USER["username"]),
            json={"role": "admin"},
        )
    finally:

        async def _mock_jwt() -> dict[str, Any]:
            return {"sub": "testuser"}

        app.dependency_overrides[verify_jwt_token] = _mock_jwt

    assert resp.status_code == 403


async def test_assign_role_unknown_user_returns_404(client: AsyncClient) -> None:
    """Role assignment for a missing user returns 404."""
    resp = await client.post(
        _ROLE_URL.format(username="ghost"),
        json={"role": "admin"},
    )
    assert resp.status_code == 404


async def test_assign_role_invalid_role_returns_422(client: AsyncClient) -> None:
    """Roles outside the RBAC allow-list are rejected by validation."""
    await client.post(_REGISTER_URL, json=_USER)

    resp = await client.post(
        _ROLE_URL.format(username=_USER["username"]),
        json={"role": "superuser"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User deletion (admin JWT required)
# ---------------------------------------------------------------------------


async def test_delete_user_returns_204(client: AsyncClient) -> None:
    """Admin JWT can soft-delete a registered user by user ID."""
    victim = {**_USER, "username": "victim-user", "email": "victim@example.com"}
    victim_resp = await client.post(_REGISTER_URL, json=victim)
    assert victim_resp.status_code == 201
    victim_id: int = victim_resp.json()["id"]

    resp = await client.delete(f"/api/v1/auth/users/{victim_id}")
    assert resp.status_code == 204

    login = await client.post(
        _TOKEN_URL,
        data=_form_data(victim["username"], victim["password"]),
    )
    assert login.status_code == 401


async def test_delete_self_returns_403(client: AsyncClient) -> None:
    """A user cannot delete themselves, even with admin role."""
    reg_resp = await client.post(_REGISTER_URL, json=_USER)
    assert reg_resp.status_code == 201
    user_id: int = reg_resp.json()["id"]

    resp = await client.delete(f"/api/v1/auth/users/{user_id}")
    assert resp.status_code == 403


async def test_delete_last_admin_returns_403(client: AsyncClient) -> None:
    """Deleting yourself when you are the sole active admin is rejected as self-delete."""
    from services.ingestor.core.auth import get_casbin_enforcer, verify_jwt_token
    from services.ingestor.main import app

    admin1 = {**_USER, "username": "admin1", "email": "admin1@example.com"}
    admin2 = {**_USER, "username": "admin2", "email": "admin2@example.com"}

    admin1_resp = await client.post(_REGISTER_URL, json=admin1)
    assert admin1_resp.status_code == 201
    admin1_id: int = admin1_resp.json()["id"]

    admin2_resp = await client.post(_REGISTER_URL, json=admin2)
    assert admin2_resp.status_code == 201
    admin2_id: int = admin2_resp.json()["id"]

    await client.post(
        _ROLE_URL.format(username=admin1["username"]),
        json={"role": "admin"},
    )
    await client.post(
        _ROLE_URL.format(username=admin2["username"]),
        json={"role": "admin"},
    )

    async def _admin2_jwt() -> dict[str, Any]:
        return {"sub": admin2["username"], "tenant_id": 1}

    app.dependency_overrides[verify_jwt_token] = _admin2_jwt
    get_casbin_enforcer().add_role_for_user_in_domain(admin2["username"], "admin", "1")
    try:
        await client.delete(f"/api/v1/auth/users/{admin1_id}")

        resp = await client.delete(f"/api/v1/auth/users/{admin2_id}")
    finally:

        async def _mock_jwt() -> dict[str, Any]:
            return {"sub": "testuser"}

        app.dependency_overrides[verify_jwt_token] = _mock_jwt

    assert resp.status_code == 403


async def test_delete_user_missing_token_returns_401(client: AsyncClient) -> None:
    """Deleting a user without a JWT is rejected."""
    from services.ingestor.core.auth import verify_jwt_token
    from services.ingestor.main import app

    victim = {**_USER, "username": "victim-user", "email": "victim@example.com"}
    victim_resp = await client.post(_REGISTER_URL, json=victim)
    assert victim_resp.status_code == 201
    victim_id: int = victim_resp.json()["id"]

    app.dependency_overrides.pop(verify_jwt_token, None)
    try:
        resp = await client.delete(f"/api/v1/auth/users/{victim_id}")
    finally:

        async def _mock_jwt() -> dict[str, Any]:
            return {"sub": "testuser"}

        app.dependency_overrides[verify_jwt_token] = _mock_jwt

    assert resp.status_code == 401


async def test_delete_unknown_user_returns_404(client: AsyncClient) -> None:
    """Deleting a missing user returns 404."""
    resp = await client.delete("/api/v1/auth/users/999999")
    assert resp.status_code == 404
