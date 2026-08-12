from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.models import (
    DependencyIncident,
    ProviderHealthSample,
    SourceProfile,
)
from services.ingestor.repositories.incidents import (
    IncidentTransition,
    _fingerprint,
    _guidance,
    _notification_due,
    acknowledge_incident,
    get_incident,
    list_incidents,
    open_or_update_incident,
    reconcile_health_incidents,
    resolve_active_incident,
    resolve_incident,
)


# ---------------------------------------------------------------------------
# _fingerprint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFingerprint:
    """Fingerprint includes tenant scope for isolation."""

    def test_fingerprint_with_tenant(self) -> None:
        source = MagicMock(spec=SourceProfile)
        source.tenant_id = "tenant-1"
        source.id = 42

        fp = _fingerprint(source, "availability")
        assert fp == "tenant-1:42:availability"

    def test_fingerprint_global(self) -> None:
        source = MagicMock(spec=SourceProfile)
        source.tenant_id = None
        source.id = 42

        fp = _fingerprint(source, "latency")
        assert fp == "global:42:latency"


# ---------------------------------------------------------------------------
# _guidance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGuidance:
    """Guidance text varies by trigger type."""

    def test_availability_guidance(self) -> None:
        result = _guidance("availability")
        assert "independent request" in result

    def test_latency_guidance(self) -> None:
        result = _guidance("latency")
        assert "latency with application" in result

    def test_contract_guidance(self) -> None:
        result = _guidance("contract")
        assert "compatibility or rollback" in result

    def test_unknown_guidance(self) -> None:
        result = _guidance("unknown_type")
        assert "compatibility or rollback" in result


# ---------------------------------------------------------------------------
# _notification_due
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotificationDue:
    """Notification cooldown prevents spam."""

    def test_notification_due_when_none(self) -> None:
        incident = MagicMock(spec=DependencyIncident)
        incident.last_notification_at = None  # type: ignore[assignment]

        assert _notification_due(incident, cooldown_seconds=60) is True

    @patch("services.ingestor.repositories.incidents._utcnow")
    def test_notification_due_when_expired(self, mock_now: MagicMock) -> None:
        now = datetime(2025, 1, 1, 12, 0, 0)
        mock_now.return_value = now

        class FakeIncident:
            last_notification_at = now - timedelta(seconds=120)

        assert _notification_due(FakeIncident(), cooldown_seconds=60) is True

    @patch("services.ingestor.repositories.incidents._utcnow")
    def test_notification_not_due_when_recent(self, mock_now: MagicMock) -> None:
        now = datetime(2025, 1, 1, 12, 0, 0)
        mock_now.return_value = now

        class FakeIncident:
            last_notification_at = now - timedelta(seconds=30)

        assert _notification_due(FakeIncident(), cooldown_seconds=60) is False


# ---------------------------------------------------------------------------
# open_or_update_incident
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenOrUpdateIncident:
    """open_or_update_incident deduplicates by fingerprint."""

    async def test_opens_new_incident(self) -> None:
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = "tenant-1"
        source.incident_cooldown_seconds = 60
        source.latency_threshold_ms = None

        result = await open_or_update_incident(
            mock_db,
            source=source,
            trigger_type="availability",
            severity="critical",
            summary="3 probes failed",
            details={"http_status": 503},
        )

        assert isinstance(result, IncidentTransition)
        assert result.transition == "opened"
        assert result.should_notify is True
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_deduplicates_existing_incident(self) -> None:
        mock_db = AsyncMock()
        existing = MagicMock(spec=DependencyIncident)
        existing.last_notification_at = None  # type: ignore[assignment]
        mock_db.scalar = AsyncMock(return_value=existing)

        source = MagicMock(spec=SourceProfile)
        source.incident_cooldown_seconds = 60
        source.latency_threshold_ms = None

        result = await open_or_update_incident(
            mock_db,
            source=source,
            trigger_type="availability",
            severity="critical",
            summary="3 probes failed",
            details={},
        )

        assert result.transition == "deduplicated"
        mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# resolve_active_incident
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveActiveIncident:
    """resolve_active_incident closes the active incident."""

    async def test_resolves_existing_incident(self) -> None:
        mock_db = AsyncMock()
        existing = MagicMock(spec=DependencyIncident)
        existing.status = "open"
        mock_db.scalar = AsyncMock(return_value=existing)

        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = "tenant-1"
        source.latency_threshold_ms = None

        result = await resolve_active_incident(
            mock_db,
            source=source,
            trigger_type="availability",
            actor="health-probe-recovery",
        )

        assert result is not None
        assert result.transition == "resolved"
        assert existing.status == "resolved"
        assert existing.active_key is None

    async def test_returns_none_when_no_incident(self) -> None:
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)

        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.latency_threshold_ms = None

        result = await resolve_active_incident(
            mock_db,
            source=source,
            trigger_type="availability",
            actor="health-probe-recovery",
        )

        assert result is None


# ---------------------------------------------------------------------------
# acknowledge_incident
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAcknowledgeIncident:
    """acknowledge_incident transitions open -> acknowledged."""

    async def test_acknowledge_open_incident(self) -> None:
        incident = MagicMock(spec=DependencyIncident)
        incident.status = "open"

        await acknowledge_incident(incident, actor="admin-user")

        assert incident.status == "acknowledged"
        assert incident.acknowledged_by == "admin-user"
        assert incident.acknowledged_at is not None

    async def test_acknowledge_non_open_raises(self) -> None:
        incident = MagicMock(spec=DependencyIncident)
        incident.status = "acknowledged"

        with pytest.raises(ValueError, match="Only an open incident"):
            await acknowledge_incident(incident, actor="admin-user")


# ---------------------------------------------------------------------------
# resolve_incident
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveIncident:
    """resolve_incident transitions active -> resolved."""

    async def test_resolve_open_incident(self) -> None:
        incident = MagicMock(spec=DependencyIncident)
        incident.status = "open"

        await resolve_incident(incident, actor="admin-user")

        assert incident.status == "resolved"
        assert incident.resolved_by == "admin-user"
        assert incident.resolved_at is not None
        assert incident.active_key is None

    async def test_resolve_acknowledged_incident(self) -> None:
        incident = MagicMock(spec=DependencyIncident)
        incident.status = "acknowledged"

        await resolve_incident(incident, actor="admin-user")

        assert incident.status == "resolved"

    async def test_resolve_non_active_raises(self) -> None:
        incident = MagicMock(spec=DependencyIncident)
        incident.status = "resolved"

        with pytest.raises(ValueError, match="Only an active incident"):
            await resolve_incident(incident, actor="admin-user")


# ---------------------------------------------------------------------------
# get_incident - tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetIncident:
    """get_incident enforces tenant isolation."""

    async def test_admin_sees_all_incidents(self) -> None:
        mock_db = AsyncMock()
        mock_incident = MagicMock(spec=DependencyIncident)
        mock_db.scalar = AsyncMock(return_value=mock_incident)

        result = await get_incident(mock_db, 1, tenant_id=None, admin=True)

        assert result is mock_incident

    async def test_non_admin_sees_only_tenant_incidents(self) -> None:
        mock_db = AsyncMock()
        mock_incident = MagicMock(spec=DependencyIncident)
        mock_db.scalar = AsyncMock(return_value=mock_incident)

        result = await get_incident(mock_db, 1, tenant_id="tenant-1", admin=False)

        assert result is mock_incident


# ---------------------------------------------------------------------------
# list_incidents - tenant isolation and filtering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListIncidents:
    """list_incidents supports tenant isolation and status filtering."""

    async def test_admin_lists_all_incidents(self) -> None:
        mock_db = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_rows_result = MagicMock()
        mock_rows_result.scalars.return_value.all.return_value = []

        async def side_effect(stmt):
            if "count" in str(stmt):
                return mock_count_result
            return mock_rows_result

        mock_db.execute = AsyncMock(side_effect=side_effect)

        rows, total = await list_incidents(
            mock_db,
            tenant_id=None,
            admin=True,
            status=None,
            source_id=None,
            offset=0,
            limit=10,
        )

        assert rows == []
        assert total == 0

    async def test_non_admin_filters_by_tenant(self) -> None:
        mock_db = AsyncMock()

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_rows_result = MagicMock()
        mock_rows_result.scalars.return_value.all.return_value = []

        async def side_effect(stmt):
            if "count" in str(stmt):
                return mock_count_result
            return mock_rows_result

        mock_db.execute = AsyncMock(side_effect=side_effect)

        rows, total = await list_incidents(
            mock_db,
            tenant_id="tenant-1",
            admin=False,
            status=None,
            source_id=None,
            offset=0,
            limit=10,
        )

        assert rows == []


# ---------------------------------------------------------------------------
# reconcile_health_incidents
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReconcileHealthIncidents:
    """reconcile_health_incidents opens/resolves based on probe results."""

    async def test_opens_incident_on_consecutive_failures(self) -> None:
        mock_db = AsyncMock()

        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = "tenant-1"
        source.name = "test-source"
        source.incident_failure_threshold = 3
        source.incident_cooldown_seconds = 60
        source.latency_threshold_ms = None

        sample = MagicMock(spec=ProviderHealthSample)
        sample.id = 100
        sample.source_id = 1
        sample.is_success = False
        sample.http_status = 503
        sample.error_message = "Connection refused"
        sample.latency_ms = 0.0
        sample.sampled_at = None

        recent = [sample] * 3

        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: recent))
        )
        mock_db.scalar = AsyncMock(return_value=None)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        transitions = await reconcile_health_incidents(
            mock_db, source=source, sample=sample
        )

        assert len(transitions) == 1
        assert transitions[0].transition == "opened"

    async def test_resolves_incident_on_recovery(self) -> None:
        mock_db = AsyncMock()

        source = MagicMock(spec=SourceProfile)
        source.id = 1
        source.tenant_id = "tenant-1"
        source.name = "test-source"
        source.incident_failure_threshold = 3
        source.latency_threshold_ms = None

        sample = MagicMock(spec=ProviderHealthSample)
        sample.id = 100
        sample.source_id = 1
        sample.is_success = True
        sample.latency_ms = 100.0
        sample.sampled_at = None

        recent = [sample] * 3

        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: recent))
        )

        existing = MagicMock(spec=DependencyIncident)
        existing.status = "open"
        mock_db.scalar = AsyncMock(return_value=existing)

        transitions = await reconcile_health_incidents(
            mock_db, source=source, sample=sample
        )

        assert len(transitions) == 1
        assert transitions[0].transition == "resolved"
