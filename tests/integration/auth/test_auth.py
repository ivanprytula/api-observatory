"""Integration tests for /api/v1/auth endpoints."""

from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REGISTER_URL = "/api/v1/auth/register"
_TOKEN_URL = "/api/v1/auth/token"
_ME_URL = "/api/v1/auth/me"
_LOGOUT_URL = "/api/v1/auth/logout"

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
