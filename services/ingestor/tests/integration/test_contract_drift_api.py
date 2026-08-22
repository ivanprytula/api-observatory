"""Integration tests for Contract Snapshot and Drift Detection endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.auth import get_casbin_enforcer, verify_jwt_token
from services.ingestor.main import app
from services.ingestor.models import (
    AgentRun,
    ContractBaseline,
    DependencyIncident,
    DriftEvent,
    Observation,
    SourceProfile,
)


pytestmark = [pytest.mark.integration, pytest.mark.core]


_SCHEMA_V1: dict[str, Any] = {
    "id": 123,
    "status": "ok",
    "payload": {"temperature": 20.5, "region": "eu"},
}

_SCHEMA_V2_NON_BREAKING: dict[str, Any] = {
    "id": 123,
    "status": "ok",
    "payload": {"temperature": 20.5, "region": "eu", "humidity": 55},
}

_SCHEMA_V3_BREAKING: dict[str, Any] = {
    "id": 123,
    "status": {"code": "ok"},
    "payload": {"region": "eu"},
}


async def _create_source(
    client: AsyncClient, name: str = "contract-test-source"
) -> int:
    response = await client.post(
        "/api/v1/sources",
        json={
            "name": name,
            "base_url": "https://1.1.1.1",
            "health_check_path": "/contracts",
            "probe_interval_seconds": 60,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def _confirm_candidate(
    client: AsyncClient,
    source_id: int,
    payload_schema: dict[str, Any],
    *,
    schema_version: str,
):
    response = None
    for attempt in range(3):
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": schema_version,
                "payload_schema": payload_schema,
            },
        )
        assert response.status_code == 201, response.text
        if attempt < 2:
            assert response.json()["drift_event"] is None
    assert response is not None
    return response


class TestIngestContractSnapshot:
    """POST /api/v1/contracts/snapshots behavior."""

    async def test_first_snapshot_returns_no_drift_event(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client)

        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["snapshot"]["source_id"] == source_id
        assert body["snapshot"]["compatibility_score"] == 100.0
        assert body["drift_event"] is None

    async def test_non_breaking_additive_change_creates_non_breaking_event(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(
            client, name="contract-test-source-non-breaking"
        )

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        response = await _confirm_candidate(
            client,
            source_id,
            _SCHEMA_V2_NON_BREAKING,
            schema_version="v2",
        )

        assert response.status_code == 201
        drift_event = response.json()["drift_event"]
        assert drift_event is not None
        assert drift_event["event_type"] == "non_breaking"
        assert "payload.humidity" in drift_event["added_fields"]

    async def test_breaking_change_creates_breaking_event(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-test-source-breaking")

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        response = await _confirm_candidate(
            client,
            source_id,
            _SCHEMA_V3_BREAKING,
            schema_version="v3",
        )

        assert response.status_code == 201
        drift_event = response.json()["drift_event"]
        assert drift_event is not None
        assert drift_event["event_type"] == "breaking"
        assert "payload.temperature" in drift_event["removed_fields"]
        assert "status" in drift_event["type_changed_fields"]

    async def test_snapshot_ingest_source_not_found_returns_404(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": 999999, "payload_schema": _SCHEMA_V1},
        )
        assert response.status_code == 404

    async def test_identical_schema_produces_no_drift_event(
        self, client: AsyncClient
    ) -> None:
        """Fingerprint short-circuit: second snapshot with identical payload produces
        no drift event and compatibility_score == 100."""
        source_id = await _create_source(client, name="contract-test-source-identical")

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["drift_event"] is None
        assert body["snapshot"]["compatibility_score"] == 100.0

    async def test_integer_to_fractional_value_is_same_json_number_type(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-number-normalization")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": {"amount": 1}},
        )

        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": {"amount": 1.5}},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["drift_event"] is None
        assert body["snapshot"]["compatibility_score"] == 100.0

    async def test_concrete_value_to_null_is_confirmed_type_change(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-null-type-change")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": {"comment": "ready"}},
        )

        response = await _confirm_candidate(
            client,
            source_id,
            {"comment": None},
            schema_version="nullable",
        )

        drift_event = response.json()["drift_event"]
        assert drift_event is not None
        assert drift_event["event_type"] == "breaking"
        assert drift_event["type_changed_fields"]["comment"] == {
            "from_type": "string",
            "to_type": "null",
        }

    async def test_null_field_to_missing_is_confirmed_removal(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-null-to-missing")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": {"comment": None}},
        )

        response = await _confirm_candidate(
            client,
            source_id,
            {},
            schema_version="missing-comment",
        )

        drift_event = response.json()["drift_event"]
        assert drift_event is not None
        assert drift_event["event_type"] == "breaking"
        assert drift_event["removed_fields"] == ["comment"]

    async def test_array_element_field_addition_is_confirmed_drift(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-array-addition")
        initial = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "payload_schema": {"items": [{"id": 1}, {"id": 2}]},
            },
        )
        assert initial.status_code == 201

        response = await _confirm_candidate(
            client,
            source_id,
            {"items": [{"id": 1}, {"id": 2, "price": 9.5}]},
            schema_version="array-price",
        )

        drift_event = response.json()["drift_event"]
        assert drift_event is not None
        assert drift_event["event_type"] == "non_breaking"
        assert drift_event["added_fields"] == ["items[].price"]

    async def test_empty_array_does_not_imply_element_removal(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-array-empty")
        initial = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "payload_schema": {"items": [{"id": 1, "price": 9.5}]},
            },
        )
        assert initial.status_code == 201

        for _ in range(3):
            response = await client.post(
                "/api/v1/contracts/snapshots",
                json={"source_id": source_id, "payload_schema": {"items": []}},
            )
            assert response.status_code == 201
            assert response.json()["drift_event"] is None
            assert response.json()["snapshot"]["compatibility_score"] == 100.0

    async def test_return_to_baseline_clears_candidate_without_inverse_event(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        source_id = await _create_source(client, name="contract-candidate-recovery")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V1},
        )
        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "payload_schema": _SCHEMA_V3_BREAKING,
            },
        )

        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V1},
        )

        assert response.status_code == 201
        assert response.json()["drift_event"] is None
        baseline = (
            await db.execute(
                select(ContractBaseline).where(
                    ContractBaseline.source_id == source_id,
                    ContractBaseline.status == "active",
                )
            )
        ).scalar_one()
        assert baseline.candidate_snapshot_id is None
        assert baseline.candidate_observation_count == 0
        events = (
            await db.execute(
                select(DriftEvent).where(DriftEvent.source_id == source_id)
            )
        ).scalars()
        assert list(events) == []

    async def test_confirmed_candidate_emits_only_one_event(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        source_id = await _create_source(client, name="contract-candidate-dedup")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V1},
        )
        confirmed = await _confirm_candidate(
            client,
            source_id,
            _SCHEMA_V2_NON_BREAKING,
            schema_version="v2",
        )
        duplicate = await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V2_NON_BREAKING},
        )

        assert confirmed.json()["drift_event"] is not None
        assert duplicate.json()["drift_event"] is None
        events = (
            await db.execute(
                select(DriftEvent).where(DriftEvent.source_id == source_id)
            )
        ).scalars()
        assert len(list(events)) == 1


class TestIncidentAutoCreationOnDrift:
    """Breaking/critical drift events auto-create an Observation + pending AgentRun."""

    async def test_breaking_change_creates_incident_observation_and_agent_run(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        source_name = "contract-test-source-incident-breaking"
        source_id = await _create_source(client, name=source_name)

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        response = await _confirm_candidate(
            client,
            source_id,
            _SCHEMA_V3_BREAKING,
            schema_version="v3",
        )

        assert response.status_code == 201
        drift_event = response.json()["drift_event"]
        assert drift_event["event_type"] == "breaking"

        incident = (
            await db.execute(
                select(Observation).where(Observation.source_id == source_id)
            )
        ).scalar_one()
        assert incident.tags == ["incident", drift_event["severity"]]
        assert incident.raw_data["drift_event_id"] == drift_event["id"]

        agent_run = (
            await db.execute(
                select(AgentRun).where(AgentRun.observation_id == incident.id)
            )
        ).scalar_one()
        assert agent_run.status == "pending"

        lifecycle_incident = (
            await db.execute(
                select(DependencyIncident).where(
                    DependencyIncident.source_id == source_id
                )
            )
        ).scalar_one()
        assert lifecycle_incident.trigger_type == "drift"
        assert lifecycle_incident.status == "open"

    async def test_non_breaking_change_does_not_create_incident(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        source_name = "contract-test-source-incident-non-breaking"
        source_id = await _create_source(client, name=source_name)

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        response = await _confirm_candidate(
            client,
            source_id,
            _SCHEMA_V2_NON_BREAKING,
            schema_version="v2",
        )

        assert response.status_code == 201
        assert response.json()["drift_event"]["event_type"] == "non_breaking"

        incident = (
            await db.execute(
                select(Observation).where(Observation.source_id == source_id)
            )
        ).scalar_one_or_none()
        assert incident is None


class TestContractDriftReadEndpoints:
    """Read-side endpoints for snapshots, events, and compatibility."""

    async def test_list_snapshots(self, client: AsyncClient) -> None:
        source_id = await _create_source(
            client, name="contract-test-source-list-snapshots"
        )

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v2",
                "payload_schema": _SCHEMA_V2_NON_BREAKING,
            },
        )

        response = await client.get(f"/api/v1/contracts/sources/{source_id}/snapshots")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    async def test_list_drift_events(self, client: AsyncClient) -> None:
        source_id = await _create_source(
            client, name="contract-test-source-list-events"
        )

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        await _confirm_candidate(
            client,
            source_id,
            _SCHEMA_V3_BREAKING,
            schema_version="v3",
        )

        response = await client.get(
            f"/api/v1/contracts/sources/{source_id}/drift-events"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["event_type"] == "breaking"

    async def test_compatibility_report_without_snapshots(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(
            client, name="contract-test-source-empty-compat"
        )

        response = await client.get(
            f"/api/v1/contracts/sources/{source_id}/compatibility"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["latest_snapshot_id"] is None
        assert body["compatibility_score"] == 100.0
        assert body["drift_detected"] is False

    async def test_compatibility_report_with_breaking_change(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-test-source-compat")

        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v1",
                "payload_schema": _SCHEMA_V1,
            },
        )
        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v3",
                "payload_schema": _SCHEMA_V3_BREAKING,
            },
        )

        response = await client.get(
            f"/api/v1/contracts/sources/{source_id}/compatibility"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["drift_detected"] is True
        assert body["event_type"] == "breaking"
        assert "payload.temperature" in body["removed_fields"]
        assert "status" in body["type_changed_fields"]


class TestContractBaselineLifecycle:
    async def test_accept_candidate_creates_audited_version(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        source_id = await _create_source(client, name="contract-baseline-accept")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V1},
        )
        candidate = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "payload_schema": _SCHEMA_V2_NON_BREAKING,
            },
        )
        candidate_snapshot_id = candidate.json()["snapshot"]["id"]

        response = await client.post(
            f"/api/v1/contracts/sources/{source_id}/baseline/accept",
            json={
                "candidate_snapshot_id": candidate_snapshot_id,
                "acceptance_note": "Reviewed vendor v2 rollout.",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["version"] == 2
        assert body["baseline_snapshot_id"] == candidate_snapshot_id
        assert body["accepted_by"] == "testuser"
        assert body["candidate_snapshot_id"] is None

        history = list(
            (
                await db.execute(
                    select(ContractBaseline)
                    .where(ContractBaseline.source_id == source_id)
                    .order_by(ContractBaseline.version)
                )
            )
            .scalars()
            .all()
        )
        assert [baseline.status for baseline in history] == [
            "superseded",
            "active",
        ]

    async def test_accept_without_candidate_returns_conflict(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, name="contract-baseline-no-candidate")
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V1},
        )

        response = await client.post(
            f"/api/v1/contracts/sources/{source_id}/baseline/accept",
            json={},
        )

        assert response.status_code == 409

    async def test_baseline_access_is_tenant_scoped(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        source_id = await _create_source(client, name="contract-baseline-tenant")
        source = await db.get(SourceProfile, source_id)
        assert source is not None
        source.tenant_id = 41
        await db.commit()
        await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": _SCHEMA_V1},
        )

        original_override = app.dependency_overrides[verify_jwt_token]

        async def _other_tenant() -> dict[str, Any]:
            return {
                "sub": "other-tenant-manager",
                "tenant_id": 99,
            }

        app.dependency_overrides[verify_jwt_token] = _other_tenant
        get_casbin_enforcer().add_role_for_user_in_domain(
            "other-tenant-manager", "manager", "99"
        )
        try:
            response = await client.get(
                f"/api/v1/contracts/sources/{source_id}/baseline"
            )
        finally:
            app.dependency_overrides[verify_jwt_token] = original_override

        assert response.status_code == 404
