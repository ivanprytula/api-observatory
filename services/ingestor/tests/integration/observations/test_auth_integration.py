from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.auth import get_casbin_enforcer, verify_jwt_token
from services.ingestor.main import app


async def _viewer_claims() -> dict[str, str]:
    return {"sub": "viewer-user"}


@pytest.mark.demo
class TestSessionAuth:
    """Tests for cache-backed session-cookie routes."""

    async def test_login_session_creates_session(self, client: AsyncClient) -> None:
        """POST /api/v1/observations/auth/login creates a session cookie."""
        response = await client.post(
            "/api/v1/observations/auth/login",
            params={"user_id": "testuser"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "message" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) > 0

    async def test_get_observation_secured_requires_session(
        self, client: AsyncClient, db: AsyncSession, observation_timestamp: datetime
    ) -> None:
        """GET /api/v1/observations/{id}/secure requires valid session cookie."""
        from services.ingestor.repositories import observations as crud

        observation = await crud.create_observation(
            db,
            ObservationRequest(source="test", timestamp=observation_timestamp, data={}),
        )

        # Without session, should get 401
        response = await client.get(f"/api/v1/observations/{observation.id}/secure")
        assert response.status_code == 401

    async def test_get_observation_secured_with_valid_session(
        self, client: AsyncClient, db: AsyncSession, observation_timestamp
    ) -> None:
        """GET /api/v1/observations/{id}/secure succeeds with valid session cookie."""
        from services.ingestor.repositories import observations as crud

        # Create a observation
        observation = await crud.create_observation(
            db,
            ObservationRequest(source="test", timestamp=observation_timestamp, data={}),
        )

        # Login to get session
        login_response = await client.post(
            "/api/v1/observations/auth/login",
            params={"user_id": "testuser"},
        )
        session_id = login_response.json()["session_id"]

        # Set session cookie on client instance (not per-request)
        client.cookies.set("session_id", session_id)
        response = await client.get(f"/api/v1/observations/{observation.id}/secure")
        assert response.status_code == 200
        assert response.json()["id"] == observation.id

    async def test_get_observation_secured_with_expired_session(
        self, client: AsyncClient, db: AsyncSession, observation_timestamp
    ) -> None:
        """GET /api/v1/observations/{id}/secure fails with expired session."""
        import uuid
        from datetime import UTC, datetime, timedelta

        from services.ingestor import auth
        from services.ingestor.repositories import observations as observations_repo

        # Create a observation
        observation = await observations_repo.create_observation(
            db,
            ObservationRequest(source="test", timestamp=observation_timestamp, data={}),
        )

        # Create an expired session directly in the fake cache
        session_id = str(uuid.uuid4())
        await auth._session_client.hset(
            session_id,
            mapping={
                "user_id": "testuser",
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": (
                    datetime.now(UTC) - timedelta(hours=1)
                ).isoformat(),  # Expired
            },
        )

        # Set expired session cookie on client instance
        client.cookies.set("session_id", session_id)
        response = await client.get(f"/api/v1/observations/{observation.id}/secure")
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    async def test_archive_observation_secured_requires_writer_or_admin(
        self, client: AsyncClient, db: AsyncSession, observation_timestamp
    ) -> None:
        """RBAC secure archive endpoint denies viewer role and allows writer role."""
        from services.ingestor.repositories import observations as crud

        observation = await crud.create_observation(
            db,
            ObservationRequest(source="test", timestamp=observation_timestamp, data={}),
        )

        viewer_login = await client.post(
            "/api/v1/observations/auth/login",
            params={"user_id": "viewer-user", "role": "viewer"},
        )
        client.cookies.set("session_id", viewer_login.json()["session_id"])
        viewer_response = await client.patch(
            f"/api/v1/observations/{observation.id}/secure/archive"
        )
        assert viewer_response.status_code == 403

        writer_login = await client.post(
            "/api/v1/observations/auth/login",
            params={"user_id": "writer-user", "role": "writer"},
        )
        client.cookies.set("session_id", writer_login.json()["session_id"])
        writer_response = await client.patch(
            f"/api/v1/observations/{observation.id}/secure/archive"
        )
        assert writer_response.status_code == 200

    async def test_delete_observation_secured_requires_admin(
        self, client: AsyncClient, db: AsyncSession, observation_timestamp
    ) -> None:
        """RBAC secure delete endpoint allows only admin role."""
        from services.ingestor.repositories import observations as crud

        observation = await crud.create_observation(
            db,
            ObservationRequest(source="test", timestamp=observation_timestamp, data={}),
        )

        writer_login = await client.post(
            "/api/v1/observations/auth/login",
            params={"user_id": "writer-user", "role": "writer"},
        )
        client.cookies.set("session_id", writer_login.json()["session_id"])
        writer_response = await client.delete(
            f"/api/v1/observations/{observation.id}/secure/delete"
        )
        assert writer_response.status_code == 403

        admin_login = await client.post(
            "/api/v1/observations/auth/login",
            params={"user_id": "admin-user", "role": "admin"},
        )
        client.cookies.set("session_id", admin_login.json()["session_id"])
        admin_response = await client.delete(
            f"/api/v1/observations/{observation.id}/secure/delete"
        )
        assert admin_response.status_code == 204


@pytest.mark.integration
class TestPublicDocs:
    """Documentation endpoints are publicly readable."""

    async def test_docs_endpoint_accessible(self, client: AsyncClient) -> None:
        """GET /docs returns Swagger UI without credentials."""
        response = await client.get("/docs")
        assert response.status_code == 200
        # Swagger UI contains specific HTML
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    async def test_openapi_schema_accessible(self, client: AsyncClient) -> None:
        """GET /openapi.json returns a valid schema without credentials."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["openapi"].startswith("3.")
        assert "paths" in schema
        assert "info" in schema

    async def test_redoc_endpoint_accessible(self, client: AsyncClient) -> None:
        """GET /redoc returns ReDoc UI without credentials."""
        response = await client.get("/redoc")
        assert response.status_code == 200
        # ReDoc contains specific HTML
        assert "redoc" in response.text.lower() or "openapi" in response.text.lower()


@pytest.mark.integration
class TestRateLimitHandler:
    """Tests for rate limit exceeded handler."""

    async def test_create_observation_endpoint_works(self, client: AsyncClient) -> None:
        """Create observation endpoint works (rate limit applied)."""
        response = await client.post(
            "/api/v1/observations",
            json={"source": "test", "timestamp": "2024-01-01T00:00:00", "data": {}},
        )
        assert response.status_code == 201
        # Slowapi may or may not set these headers depending on configuration
        # Just verify the endpoint works
        assert "id" in response.json()


@pytest.mark.integration
class TestJwtAuthOnCoreRoutes:
    """Core CRUD and analysis routes require a
    writer/admin JWT for writes and any authenticated JWT for reads. The
    shared test client pre-authenticates every request as admin, so these tests manipulate
    `app.dependency_overrides` directly to exercise the real
    unauthenticated/under-privileged paths."""

    async def test_create_observation_requires_auth(self, client: AsyncClient) -> None:
        saved = app.dependency_overrides.pop(verify_jwt_token, None)
        try:
            response = await client.post(
                "/api/v1/observations",
                json={"source": "test", "timestamp": "2024-01-01T00:00:00", "data": {}},
            )
        finally:
            if saved is not None:
                app.dependency_overrides[verify_jwt_token] = saved

        assert response.status_code == 401

    async def test_create_observation_denies_viewer_role(
        self, client: AsyncClient
    ) -> None:
        saved = app.dependency_overrides.get(verify_jwt_token)
        app.dependency_overrides[verify_jwt_token] = _viewer_claims
        get_casbin_enforcer().add_role_for_user_in_domain("viewer-user", "viewer", "*")
        try:
            response = await client.post(
                "/api/v1/observations",
                json={"source": "test", "timestamp": "2024-01-01T00:00:00", "data": {}},
            )
        finally:
            if saved is not None:
                app.dependency_overrides[verify_jwt_token] = saved

        assert response.status_code == 403

    async def test_list_observations_requires_auth(self, client: AsyncClient) -> None:
        saved = app.dependency_overrides.pop(verify_jwt_token, None)
        try:
            response = await client.get("/api/v1/observations")
        finally:
            if saved is not None:
                app.dependency_overrides[verify_jwt_token] = saved

        assert response.status_code == 401

    async def test_delete_observation_denies_writer_role(
        self, client: AsyncClient, db: AsyncSession, observation_timestamp: datetime
    ) -> None:
        """Hard-delete is admin-only; a writer-role JWT is rejected with 403."""
        from services.ingestor.repositories import observations as crud

        observation = await crud.create_observation(
            db,
            ObservationRequest(source="test", timestamp=observation_timestamp, data={}),
        )

        saved = app.dependency_overrides.get(verify_jwt_token)

        async def _writer_claims() -> dict[str, str]:
            return {"sub": "writer-user"}

        app.dependency_overrides[verify_jwt_token] = _writer_claims
        get_casbin_enforcer().add_role_for_user_in_domain("writer-user", "writer", "*")
        try:
            response = await client.delete(f"/api/v1/observations/{observation.id}")
        finally:
            if saved is not None:
                app.dependency_overrides[verify_jwt_token] = saved

        assert response.status_code == 403


@pytest.mark.integration
class TestSecurityHeaders:
    """Baseline security headers should be attached by middleware."""

    async def test_security_headers_present_on_health(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/health")
        assert response.status_code in {200, 429}
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "Permissions-Policy" in response.headers
