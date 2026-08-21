"""Integration tests for the Abuse Detection API endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.auth import get_casbin_enforcer, verify_jwt_token
from services.ingestor.main import app


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Auth helper: override verify_jwt_token to supply test role claims
# ---------------------------------------------------------------------------


def _make_jwt_claims(sub: str, tenant_id: int | None = None) -> dict[str, Any]:
    return {
        "sub": sub,
        "tenant_id": tenant_id,
    }


async def _user_claims() -> dict[str, Any]:
    return _make_jwt_claims("abuse-user", tenant_id=1)


async def _admin_claims() -> dict[str, Any]:
    return _make_jwt_claims("abuse-admin", tenant_id=1)


async def _no_role_claims() -> dict[str, Any]:
    return _make_jwt_claims("abuse-user", tenant_id=1)


# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------

_SIGNAL_PAYLOAD: dict[str, Any] = {
    "signal_type": "noisy_source",
    "actor_type": "source_id",
    "actor_id": "src-001",
    "severity": "medium",
    "detection_rule": "quota_exceeded",
    "evidence": {"calls": 200, "quota": 60},
    "action_taken": "logged",
}


# ---------------------------------------------------------------------------
# POST /api/v1/abuse/signals
# ---------------------------------------------------------------------------
class TestCreateSignal:
    """POST /api/v1/abuse/signals — create a new abuse signal."""

    async def test_create_returns_201(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            response = await client.post("/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD)
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 201
        body = response.json()
        assert body["signal_type"] == "noisy_source"
        assert body["actor_id"] == "src-001"
        assert body["severity"] == "medium"
        assert isinstance(body["id"], int)
        assert body["resolved_at"] is None

    async def test_create_missing_required_field_returns_422(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            payload = {k: v for k, v in _SIGNAL_PAYLOAD.items() if k != "signal_type"}
            response = await client.post("/api/v1/abuse/signals", json=payload)
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 422

    async def test_create_denies_no_role(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _no_role_claims
        enforcer = get_casbin_enforcer()
        print(f"\nDEBUG deny: adapter={type(enforcer.adapter).__name__}")
        print(
            f"DEBUG deny: roles={enforcer.get_roles_for_user_in_domain('abuse-user', '1')}"
        )
        print(
            f"DEBUG deny: enforce={enforcer.enforce('abuse-user', '1', 'user', 'access')}"
        )
        try:
            response = await client.post("/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD)
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        print(f"DEBUG deny: response={response.status_code}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/abuse/signals
# ---------------------------------------------------------------------------
class TestListSignals:
    """GET /api/v1/abuse/signals — list with optional filters."""

    async def test_empty_list(self, client: AsyncClient, db: AsyncSession) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            response = await client.get("/api/v1/abuse/signals")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_list_returns_created_signal(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            await client.post("/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD)
            response = await client.get("/api/v1/abuse/signals")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["actor_id"] == "src-001"

    async def test_filter_by_signal_type(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            await client.post("/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD)
            await client.post(
                "/api/v1/abuse/signals",
                json={
                    **_SIGNAL_PAYLOAD,
                    "signal_type": "suspicious_key",
                    "actor_id": "key-001",
                },
            )
            response = await client.get(
                "/api/v1/abuse/signals?signal_type=noisy_source"
            )
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["signal_type"] == "noisy_source"

    async def test_pagination(self, client: AsyncClient, db: AsyncSession) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            for i in range(5):
                await client.post(
                    "/api/v1/abuse/signals",
                    json={**_SIGNAL_PAYLOAD, "actor_id": f"src-{i:03d}"},
                )
            response = await client.get("/api/v1/abuse/signals?limit=2&offset=0")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2

    async def test_list_denies_unauthenticated(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _no_role_claims
        enforcer = get_casbin_enforcer()
        for role in list(enforcer.get_roles_for_user_in_domain("abuse-user", "1")):
            enforcer.delete_roles_for_user_in_domain("abuse-user", role, "1")
        try:
            response = await client.get("/api/v1/abuse/signals")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/abuse/signals/{signal_id}
# ---------------------------------------------------------------------------
class TestGetSignal:
    """GET /api/v1/abuse/signals/{signal_id} — get a single signal."""

    async def test_get_existing_returns_200(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            create_resp = await client.post(
                "/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD
            )
            signal_id = create_resp.json()["id"]
            response = await client.get(f"/api/v1/abuse/signals/{signal_id}")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == signal_id
        assert body["actor_id"] == "src-001"

    async def test_get_nonexistent_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            response = await client.get("/api/v1/abuse/signals/999999")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/abuse/signals/{signal_id}/resolve
# ---------------------------------------------------------------------------
class TestResolveSignal:
    """PATCH /api/v1/abuse/signals/{signal_id}/resolve — resolve a signal."""

    async def test_resolve_open_signal_returns_200(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            create_resp = await client.post(
                "/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD
            )
            signal_id = create_resp.json()["id"]
            response = await client.patch(
                f"/api/v1/abuse/signals/{signal_id}/resolve",
                json={"resolved_by": "admin", "notes": "False positive."},
            )
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == signal_id
        assert body["resolved_at"] is not None
        assert body["resolved_by"] == "admin"
        assert body["notes"] == "False positive."

    async def test_resolve_nonexistent_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            response = await client.patch(
                "/api/v1/abuse/signals/999999/resolve",
                json={"resolved_by": "admin"},
            )
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 404

    async def test_resolve_already_resolved_returns_404(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            create_resp = await client.post(
                "/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD
            )
            signal_id = create_resp.json()["id"]
            await client.patch(
                f"/api/v1/abuse/signals/{signal_id}/resolve",
                json={"resolved_by": "admin"},
            )
            # Second resolve should 404
            response = await client.patch(
                f"/api/v1/abuse/signals/{signal_id}/resolve",
                json={"resolved_by": "admin"},
            )
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 404

    async def test_resolve_denies_no_role(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            create_resp = await client.post(
                "/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD
            )
            signal_id = create_resp.json()["id"]
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        app.dependency_overrides[verify_jwt_token] = _no_role_claims
        enforcer = get_casbin_enforcer()
        for role in list(enforcer.get_roles_for_user_in_domain("abuse-user", "1")):
            enforcer.delete_roles_for_user_in_domain("abuse-user", role, "1")
        try:
            response = await client.patch(
                f"/api/v1/abuse/signals/{signal_id}/resolve",
                json={"resolved_by": "admin"},
            )
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/abuse/summary
# ---------------------------------------------------------------------------
class TestAbuseSummary:
    """GET /api/v1/abuse/summary — aggregate statistics."""

    async def test_empty_summary(self, client: AsyncClient, db: AsyncSession) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            response = await client.get("/api/v1/abuse/summary")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["open_count"] == 0
        assert body["resolved_count"] == 0
        assert body["by_severity"] == []
        assert body["top_actors"] == []

    async def test_summary_counts_open_signals(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            await client.post("/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD)
            await client.post(
                "/api/v1/abuse/signals",
                json={**_SIGNAL_PAYLOAD, "actor_id": "src-002", "severity": "high"},
            )
            response = await client.get("/api/v1/abuse/summary")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["open_count"] == 2
        assert body["resolved_count"] == 0
        severities = {s["severity"]: s["count"] for s in body["by_severity"]}
        assert severities.get("medium") == 1
        assert severities.get("high") == 1

    async def test_summary_counts_resolved_signals(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _user_claims
        get_casbin_enforcer().add_role_for_user_in_domain("abuse-user", "user", "1")
        try:
            create_resp = await client.post(
                "/api/v1/abuse/signals", json=_SIGNAL_PAYLOAD
            )
            signal_id = create_resp.json()["id"]
            await client.patch(
                f"/api/v1/abuse/signals/{signal_id}/resolve",
                json={"resolved_by": "admin"},
            )
            response = await client.get("/api/v1/abuse/summary")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 200
        body = response.json()
        assert body["open_count"] == 0
        assert body["resolved_count"] == 1

    async def test_summary_denies_unauthenticated(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        app.dependency_overrides[verify_jwt_token] = _no_role_claims
        enforcer = get_casbin_enforcer()
        for role in list(enforcer.get_roles_for_user_in_domain("abuse-user", "1")):
            enforcer.delete_roles_for_user_in_domain("abuse-user", role, "1")
        try:
            response = await client.get("/api/v1/abuse/summary")
        finally:
            app.dependency_overrides.pop(verify_jwt_token, None)

        assert response.status_code == 403
