"""Integration tests for /api/v1/auth endpoints."""

from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from libs.platform.auth import generate_internal_token


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGISTER_URL = "/api/v1/auth/register"
_TOKEN_URL = "/api/v1/auth/token"
_ME_URL = "/api/v1/auth/me"
_LOGOUT_URL = "/api/v1/auth/logout"
_ROLE_URL = "/api/v1/auth/users/{username}/role"

_INTERNAL_SECRET = "test-internal-secret-for-integration-tests"

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
    assert data["role"] == "viewer"
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

    import services.ingestor.auth as auth_module

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch.object(auth_module, "_session_client", fake):
        cookies = {"session_id": session_id} if session_id else {}
        resp = await client.post(_LOGOUT_URL, cookies=cookies)
        assert resp.status_code == 204

    await fake.aclose()


# ---------------------------------------------------------------------------
# Role assignment (internal service-to-service)
# ---------------------------------------------------------------------------


async def _internal_headers() -> dict[str, str]:
    token = generate_internal_token("test-service")
    return {"Authorization": f"Bearer {token}"}


async def test_assign_role_with_internal_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Internal JWT can promote a registered viewer to admin."""
    monkeypatch.setenv("INTERNAL_JWT_SECRET", _INTERNAL_SECRET)
    await client.post(_REGISTER_URL, json=_USER)

    resp = await client.post(
        _ROLE_URL.format(username=_USER["username"]),
        json={"role": "admin"},
        headers=await _internal_headers(),
    )
    assert resp.status_code == 200
    data: dict[str, Any] = resp.json()
    assert data["role"] == "admin"
    assert data["username"] == _USER["username"]

    # Login now returns an admin JWT claim.
    login = await client.post(
        _TOKEN_URL,
        data=_form_data(_USER["username"], _USER["password"]),
    )
    assert login.status_code == 200


async def test_assign_role_missing_internal_token_returns_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Role assignment without an internal JWT is rejected."""
    monkeypatch.setenv("INTERNAL_JWT_SECRET", _INTERNAL_SECRET)
    await client.post(_REGISTER_URL, json=_USER)

    resp = await client.post(
        _ROLE_URL.format(username=_USER["username"]),
        json={"role": "admin"},
    )
    assert resp.status_code == 401


async def test_assign_role_invalid_internal_token_returns_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tampered internal JWT is rejected."""
    monkeypatch.setenv("INTERNAL_JWT_SECRET", _INTERNAL_SECRET)
    await client.post(_REGISTER_URL, json=_USER)

    resp = await client.post(
        _ROLE_URL.format(username=_USER["username"]),
        json={"role": "admin"},
        headers={"Authorization": "Bearer invalid.internal.token"},
    )
    assert resp.status_code == 401


async def test_assign_role_unknown_user_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Role assignment for a missing user returns 404."""
    monkeypatch.setenv("INTERNAL_JWT_SECRET", _INTERNAL_SECRET)

    resp = await client.post(
        _ROLE_URL.format(username="ghost"),
        json={"role": "admin"},
        headers=await _internal_headers(),
    )
    assert resp.status_code == 404


async def test_assign_role_invalid_role_returns_422(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Roles outside the RBAC allow-list are rejected by validation."""
    monkeypatch.setenv("INTERNAL_JWT_SECRET", _INTERNAL_SECRET)
    await client.post(_REGISTER_URL, json=_USER)

    resp = await client.post(
        _ROLE_URL.format(username=_USER["username"]),
        json={"role": "superuser"},
        headers=await _internal_headers(),
    )
    assert resp.status_code == 422
