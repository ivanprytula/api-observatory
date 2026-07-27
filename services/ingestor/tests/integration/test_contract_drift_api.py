"""Integration tests for Contract Snapshot and Drift Detection endpoints."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import AgentRun, DependencyIncident, Observation


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
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v2",
                "payload_schema": _SCHEMA_V2_NON_BREAKING,
            },
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
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v3",
                "payload_schema": _SCHEMA_V3_BREAKING,
            },
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
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v3",
                "payload_schema": _SCHEMA_V3_BREAKING,
            },
        )

        assert response.status_code == 201
        drift_event = response.json()["drift_event"]
        assert drift_event["event_type"] == "breaking"

        incident = (
            await db.execute(
                select(Observation).where(Observation.source == source_name)
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
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v2",
                "payload_schema": _SCHEMA_V2_NON_BREAKING,
            },
        )

        assert response.status_code == 201
        assert response.json()["drift_event"]["event_type"] == "non_breaking"

        incident = (
            await db.execute(
                select(Observation).where(Observation.source == source_name)
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
        await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v3",
                "payload_schema": _SCHEMA_V3_BREAKING,
            },
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
