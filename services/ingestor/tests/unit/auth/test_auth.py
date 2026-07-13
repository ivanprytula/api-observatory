"""Unit tests for all authentication layers in services/ingestor/auth.py.

Covers:
- Layer 1: Docs auth (HTTP Basic)
- Layer 2: Bearer token + session cookie
- Layer 3: JWT create/verify

Note: No @pytest.mark.asyncio — asyncio_mode='auto' is set in pyproject.toml.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from services.ingestor.auth import (
    _extract_roles,
    create_jwt_token,
    create_refresh_token,
    create_session,
    jwt_role_guard,
    require_roles,
    revoke_refresh_token,
    session_role_guard,
    verify_bearer_token,
    verify_docs_credentials,
    verify_jwt_token,
    verify_jwt_token_str,
    verify_refresh_token,
    verify_session,
)


class TestDocsAuth:
    """HTTP Basic Auth for documentation endpoints."""

    async def test_valid_credentials_returns_credentials(self) -> None:
        """Correct username+password passes through unchanged."""
        creds = HTTPBasicCredentials(username="admin", password="secret")
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.docs_username = "admin"
            mock_settings.docs_password = "secret"
            result = await verify_docs_credentials(creds)
        assert result is creds

    async def test_wrong_username_raises_403(self) -> None:
        """Wrong username raises 403 Forbidden."""
        creds = HTTPBasicCredentials(username="hacker", password="secret")
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.docs_username = "admin"
            mock_settings.docs_password = "secret"
            with pytest.raises(HTTPException) as exc:
                await verify_docs_credentials(creds)
        assert exc.value.status_code == 403

    async def test_wrong_password_raises_403(self) -> None:
        """Wrong password raises 403 Forbidden."""
        creds = HTTPBasicCredentials(username="admin", password="wrongpass")
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.docs_username = "admin"
            mock_settings.docs_password = "secret"
            with pytest.raises(HTTPException) as exc:
                await verify_docs_credentials(creds)
        assert exc.value.status_code == 403

    async def test_auth_disabled_passes_through(self) -> None:
        """When docs_username is not set, any credentials pass through."""
        creds = HTTPBasicCredentials(username="anyone", password="anything")
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.docs_username = None
            mock_settings.docs_password = None
            result = await verify_docs_credentials(creds)
        assert result is creds


# ---------------------------------------------------------------------------
# Layer 2: Bearer Token
# ---------------------------------------------------------------------------
class TestBearerToken:
    """Bearer token auth for v1 API endpoints."""

    async def test_valid_token_returns_credentials(self) -> None:
        """Correct bearer token returns the token string."""
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.api_v1_bearer_token = "secret-token"
            result = await verify_bearer_token("Bearer secret-token")
        assert result == "secret-token"

    async def test_missing_header_raises_401(self) -> None:
        """No Authorization header raises 401."""
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.api_v1_bearer_token = "secret-token"
            with pytest.raises(HTTPException) as exc:
                await verify_bearer_token(None)
        assert exc.value.status_code == 401

    async def test_wrong_scheme_raises_401(self) -> None:
        """Non-Bearer scheme (e.g., Basic) raises 401."""
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.api_v1_bearer_token = "secret-token"
            with pytest.raises(HTTPException) as exc:
                await verify_bearer_token("Basic secret-token")
        assert exc.value.status_code == 401

    async def test_invalid_token_raises_403(self) -> None:
        """Wrong token value raises 403 Forbidden."""
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.api_v1_bearer_token = "secret-token"
            with pytest.raises(HTTPException) as exc:
                await verify_bearer_token("Bearer wrong-token")
        assert exc.value.status_code == 403

    async def test_auth_disabled_returns_public(self) -> None:
        """When api_v1_bearer_token is not set, any request returns 'public'."""
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.api_v1_bearer_token = None
            result = await verify_bearer_token(None)
        assert result == "public"


class TestRbacHelpers:
    """RBAC helper unit tests for role extraction and permission checks."""

    def test_extract_roles_from_role_and_roles_fields(self) -> None:
        """`role` and `roles` payloads normalize into a single lowercase role set."""
        claims = {"role": "Admin", "roles": ["Writer", "viewer"]}
        assert _extract_roles(claims) == {"admin", "writer", "viewer"}

    def test_require_roles_raises_403_when_missing(self) -> None:
        """require_roles rejects auth contexts lacking required role membership."""
        with pytest.raises(HTTPException) as exc:
            require_roles({"admin"}, {"viewer"})
        assert exc.value.status_code == 403

    async def test_session_role_guard_allows_admin(self) -> None:
        """session_role_guard allows sessions with matching roles."""
        guard = session_role_guard("admin")
        session_data = {"user_id": "u1", "role": "admin"}
        result = await guard(session_data)
        assert result["user_id"] == "u1"

    async def test_jwt_role_guard_denies_viewer_for_writer_route(self) -> None:
        """jwt_role_guard blocks insufficient roles with 403."""
        guard = jwt_role_guard("writer", "admin")
        with pytest.raises(HTTPException) as exc:
            await guard({"sub": "u2", "roles": ["viewer"]})
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Layer 2: Session Cookie
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSessionCookie:
    """Cookie-based session auth for v1 API endpoints."""

    async def test_valid_session_returns_data(self) -> None:
        """Valid non-expired session ID returns session data dict."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.hgetall.return_value = {"user_id": "user-42", "role": "viewer"}
            result = await verify_session("valid-session-id")
            assert result["user_id"] == "user-42"

    async def test_missing_cookie_raises_401(self) -> None:
        """No session_id cookie raises 401."""
        with pytest.raises(HTTPException) as exc:
            await verify_session(None)
        assert exc.value.status_code == 401

    async def test_unknown_session_raises_401(self) -> None:
        """Non-existent session ID raises 401."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.hgetall.return_value = {}
            with pytest.raises(HTTPException) as exc:
                await verify_session("00000000-0000-0000-0000-000000000000")
            assert exc.value.status_code == 401

    async def test_create_session_stores_user_id(self) -> None:
        """create_session returns a session_id that maps to the correct user."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            session_id, _ = await create_session("user-123", {"role": "admin"})
            assert session_id is not None
            mock_cache.hset.assert_called_once()
            args, kwargs = mock_cache.hset.call_args
            assert kwargs["mapping"]["user_id"] == "user-123"
            assert kwargs["mapping"]["role"] == "admin"

    async def test_create_session_fails_open_when_cache_write_raises(self) -> None:
        """create_session still returns a session_id if Cache is merely
        unreachable (not just unconfigured) — a live client whose write raises
        must degrade the same way an absent (`None`) client does, otherwise
        login() 500s on any transient Cache outage instead of failing open
        like the rest of this module (see create_refresh_token)."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.hset.side_effect = ConnectionError("cache unreachable")
            session_id, _ = await create_session("user-123", {"role": "admin"})
        assert session_id  # session_id issued despite the Cache write failing


# ---------------------------------------------------------------------------
# Layer 3: JWT
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestJWT:
    """JWT create and verify for v2 API endpoints."""

    async def test_valid_token_returns_claims(self) -> None:
        """Valid JWT returns decoded payload with correct subject."""
        token = create_jwt_token("user-1")
        claims = await verify_jwt_token(f"Bearer {token}")

        assert claims["sub"] == "user-1"

    async def test_custom_claims_included(self) -> None:
        """Custom claims are preserved in the encoded token."""
        token = create_jwt_token("user-2", {"role": "admin", "tier": "pro"})
        claims = await verify_jwt_token(f"Bearer {token}")

        assert claims["role"] == "admin"
        assert claims["tier"] == "pro"

    async def test_missing_header_raises_401(self) -> None:
        """No Authorization header raises 401."""
        with pytest.raises(HTTPException) as exc:
            await verify_jwt_token(None)
        assert exc.value.status_code == 401

    async def test_wrong_scheme_raises_401(self) -> None:
        """Non-Bearer scheme raises 401."""
        token = create_jwt_token("user-3")
        with pytest.raises(HTTPException) as exc:
            await verify_jwt_token(f"Basic {token}")
        assert exc.value.status_code == 401

    async def test_expired_token_raises_401(self) -> None:
        """Expired JWT raises 401 with 'Token expired' detail."""

        import jwt as pyjwt

        from services.ingestor.config import settings

        expired_payload = {
            "sub": "user-4",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iss": settings.app_name,
        }
        expired_token = pyjwt.encode(
            expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(HTTPException) as exc:
            await verify_jwt_token(f"Bearer {expired_token}")
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    async def test_tampered_token_raises_401(self) -> None:
        """Token with altered signature raises 401."""
        with pytest.raises(HTTPException) as exc:
            await verify_jwt_token(
                "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.invalidsig"
            )
        assert exc.value.status_code == 401

    async def test_previous_jwt_secret_is_accepted_during_rotation(self) -> None:
        """Tokens signed with configured previous secret stay valid during cutover."""
        import jwt as pyjwt

        old_secret = "old-secret-1234567890"
        with patch("services.ingestor.auth.settings") as mock_settings:
            mock_settings.jwt_secret = "new-secret-0987654321"
            mock_settings.jwt_previous_secrets = old_secret
            mock_settings.jwt_algorithm = "HS256"
            mock_settings.app_name = "Data Pipeline API (async)"

            payload = {
                "sub": "rotating-user",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "iss": mock_settings.app_name,
            }
            rotated_token = pyjwt.encode(payload, old_secret, algorithm="HS256")

            claims = await verify_jwt_token(f"Bearer {rotated_token}")

        assert claims["sub"] == "rotating-user"

    async def test_malformed_token_raises_401(self) -> None:
        """Completely invalid token string raises 401."""
        with pytest.raises(HTTPException) as exc:
            await verify_jwt_token("Bearer not.a.jwt")
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------
class TestRefreshToken:
    """Single-use refresh token lifecycle."""

    async def test_create_and_verify_refresh_token(self) -> None:
        """create_refresh_token issues a token that verify_refresh_token accepts."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.setex = AsyncMock(return_value=True)
            token = await create_refresh_token("user-99")

        assert token

        # Verify it (stub Cache to confirm JTI present)
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.exists = AsyncMock(return_value=1)
            claims = await verify_refresh_token(token)

        assert claims["sub"] == "user-99"
        assert claims["token_type"] == "refresh"

    async def test_verify_refresh_token_raises_401_when_revoked(self) -> None:
        """verify_refresh_token raises 401 when JTI has been revoked in Cache."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.setex = AsyncMock(return_value=True)
            token = await create_refresh_token("user-99")

        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.exists = AsyncMock(return_value=0)  # revoked
            with pytest.raises(HTTPException) as exc:
                await verify_refresh_token(token)

        assert exc.value.status_code == 401

    async def test_verify_refresh_token_rejects_access_token(self) -> None:
        """verify_refresh_token rejects a regular access token (wrong token_type)."""
        access_token = create_jwt_token("user-1")
        with pytest.raises(HTTPException) as exc:
            await verify_refresh_token(access_token)
        assert exc.value.status_code == 401

    async def test_revoke_refresh_token_deletes_cache_key(self) -> None:
        """revoke_refresh_token removes the JTI from Cache."""
        with patch(
            "services.ingestor.auth._session_client", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.delete = AsyncMock()
            await revoke_refresh_token("some-jti-uuid")
            mock_cache.delete.assert_called_once_with("refresh:some-jti-uuid")

    async def test_create_refresh_token_fails_open_when_cache_unavailable(self) -> None:
        """create_refresh_token still returns a token even if Cache is down."""
        with patch("services.ingestor.auth._session_client", None):
            token = await create_refresh_token("user-no-cache")
        assert token  # token issued despite no Cache

    async def test_verify_jwt_token_str_accepts_valid_token(self) -> None:
        """verify_jwt_token_str accepts a raw bearer string (no 'Bearer ' prefix)."""
        token = create_jwt_token("user-ws")
        claims = await verify_jwt_token_str(token)
        assert claims["sub"] == "user-ws"

    async def test_verify_jwt_token_str_rejects_invalid_token(self) -> None:
        """verify_jwt_token_str raises 401 for a garbage token."""
        with pytest.raises(HTTPException) as exc:
            await verify_jwt_token_str("not.a.valid.jwt")
        assert exc.value.status_code == 401
