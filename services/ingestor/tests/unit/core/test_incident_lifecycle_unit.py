"""Mock-based unit tests for incident lifecycle helpers.

Covers _aware_utc, _notification_message_id, enqueue_incident_notification_requests,
_dispatch_transitions, and dispatch_incident_transitions — all paths that do
not require a live database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.core.incident_notifications import (
    _aware_utc,
    _dispatch_transitions,
    _notification_message_id,
    dispatch_incident_transitions,
    enqueue_incident_notification_requests,
)
from services.ingestor.repositories.incidents import IncidentTransition


def _fake_incident(
    id: int = 10,
    source_id: int = 5,
    tenant_id: int | None = 42,
    severity: str = "critical",
    summary: str = "host down",
    trigger_type: str = "availability",
    occurrence_count: int = 1,
    last_seen_at: datetime | None = None,
    last_notification_at: datetime | None = None,
) -> MagicMock:
    inc = MagicMock()
    inc.id = id
    inc.source_id = source_id
    inc.tenant_id = tenant_id
    inc.severity = severity
    inc.summary = summary
    inc.trigger_type = trigger_type
    inc.occurrence_count = occurrence_count
    inc.guidance = "check traces"
    inc.last_seen_at = last_seen_at or datetime(2025, 1, 1, tzinfo=UTC)
    inc.last_notification_at = last_notification_at
    return inc


def _transition(
    incident: MagicMock | None = None,
    transition: str = "opened",
    should_notify: bool = True,
) -> IncidentTransition:
    return IncidentTransition(
        incident=incident or _fake_incident(),
        transition=transition,
        should_notify=should_notify,
    )


# ---------------------------------------------------------------------------
# _aware_utc
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAwareUtc:
    def test_naive_datetime_gets_utc_tzinfo(self) -> None:
        naive = datetime(2025, 1, 1, 12, 0, 0)
        result = _aware_utc(naive)
        assert result.tzinfo is not None
        assert result == datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    def test_aware_datetime_converted_to_utc(self) -> None:
        from datetime import timezone

        aware = datetime(2025, 1, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
        result = _aware_utc(aware)
        assert result.utcoffset() == timedelta(0)
        assert result.hour == 12


# ---------------------------------------------------------------------------
# _notification_message_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotificationMessageId:
    def test_formats_with_incident_id_and_count(self) -> None:
        inc = _fake_incident(id=42, occurrence_count=3)
        transition = _transition(incident=inc)
        assert _notification_message_id(transition) == "incident:42:notification:3"


# ---------------------------------------------------------------------------
# enqueue_incident_notification_requests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnqueueNotificationRequests:
    async def test_returns_early_when_not_broker_mode(self) -> None:
        mock_db = MagicMock()
        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch("services.ingestor.core.incident_notifications.add_outbox_event") as mock_add,
        ):
            mock_settings.notification_delivery_mode = "direct"
            mock_settings.notifications_enabled = True

            await enqueue_incident_notification_requests(mock_db, [_transition()])

        mock_add.assert_not_called()

    async def test_returns_early_when_notifications_disabled(self) -> None:
        mock_db = MagicMock()
        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch("services.ingestor.core.incident_notifications.add_outbox_event") as mock_add,
        ):
            mock_settings.notification_delivery_mode = "broker"
            mock_settings.notifications_enabled = False

            await enqueue_incident_notification_requests(mock_db, [_transition()])

        mock_add.assert_not_called()

    async def test_raises_when_no_channels(self) -> None:
        mock_db = MagicMock()
        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch(
                "services.ingestor.core.incident_notifications.configured_notification_channels",
                return_value=[],
            ),
        ):
            mock_settings.notification_delivery_mode = "broker"
            mock_settings.notifications_enabled = True

            with pytest.raises(ValueError, match="at least one valid default channel"):
                await enqueue_incident_notification_requests(mock_db, [_transition()])

    async def test_skips_transitions_with_should_notify_false(self) -> None:
        mock_db = MagicMock()
        no_notify = _transition(should_notify=False)

        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch(
                "services.ingestor.core.incident_notifications.configured_notification_channels",
                return_value=["slack"],
            ),
            patch(
                "services.ingestor.core.incident_notifications.add_outbox_event",
                new=AsyncMock(),
            ) as mock_add,
        ):
            mock_settings.notification_delivery_mode = "broker"
            mock_settings.notifications_enabled = True

            await enqueue_incident_notification_requests(mock_db, [no_notify])

        mock_add.assert_not_called()

    async def test_enqueues_outbox_for_should_notify_transition(self) -> None:
        mock_db = MagicMock()
        inc = _fake_incident(id=7, occurrence_count=1)
        transition = _transition(incident=inc, should_notify=True)

        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch(
                "services.ingestor.core.incident_notifications.configured_notification_channels",
                return_value=["slack", "email"],
            ),
            patch(
                "services.ingestor.core.incident_notifications.add_outbox_event",
                new=AsyncMock(),
            ) as mock_add,
        ):
            mock_settings.notification_delivery_mode = "broker"
            mock_settings.notifications_enabled = True

            await enqueue_incident_notification_requests(mock_db, [transition])

        mock_add.assert_awaited_once()
        _, kwargs = mock_add.call_args
        assert kwargs["aggregate_type"] == "dependency_incident"
        assert kwargs["aggregate_id"] == "7"
        assert (
            kwargs["idempotency_key"]
            == "notification-request:incident:7:notification:1"
        )
        assert inc.last_notification_at == inc.last_seen_at


# ---------------------------------------------------------------------------
# _dispatch_transitions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchTransitions:
    async def test_metrics_incremented_for_all_transitions(self) -> None:
        t1 = _transition(should_notify=False)
        t2 = _transition(should_notify=True)

        with (
            patch("services.ingestor.core.incident_notifications.settings"),
            patch(
                "services.ingestor.core.incident_notifications.dispatch_notification_event",
                new=AsyncMock(),
            ),
            patch(
                "services.ingestor.core.incident_notifications.mark_notification_attempted",
                new=AsyncMock(),
            ) as mock_mark,
            patch(
                "services.ingestor.core.incident_notifications.dependency_incident_transitions_total"
            ) as mock_metrics,
        ):
            mock_metrics.labels.return_value.inc = MagicMock()
            await _dispatch_transitions(MagicMock(), [t1, t2])

        assert mock_metrics.labels.call_count == 2
        mock_mark.assert_awaited()

    async def test_skips_dispatch_when_not_should_notify(self) -> None:
        t = _transition(should_notify=False)
        with (
            patch("services.ingestor.core.incident_notifications.settings"),
            patch(
                "services.ingestor.core.incident_notifications.dispatch_notification_event",
                new=AsyncMock(),
            ) as mock_dispatch,
            patch(
                "services.ingestor.core.incident_notifications.mark_notification_attempted",
                new=AsyncMock(),
            ),
            patch(
                "services.ingestor.core.incident_notifications.dependency_incident_transitions_total"
            ) as mock_metrics,
        ):
            mock_metrics.labels.return_value.inc = MagicMock()
            await _dispatch_transitions(MagicMock(), [t])

        mock_dispatch.assert_not_awaited()

    async def test_skips_dispatch_in_broker_mode(self) -> None:
        t = _transition(should_notify=True)
        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch(
                "services.ingestor.core.incident_notifications.dispatch_notification_event",
                new=AsyncMock(),
            ) as mock_dispatch,
            patch(
                "services.ingestor.core.incident_notifications.mark_notification_attempted",
                new=AsyncMock(),
            ) as mock_mark,
            patch(
                "services.ingestor.core.incident_notifications.dependency_incident_transitions_total"
            ) as mock_metrics,
        ):
            mock_settings.notification_delivery_mode = "broker"
            mock_metrics.labels.return_value.inc = MagicMock()
            await _dispatch_transitions(MagicMock(), [t])

        mock_dispatch.assert_not_awaited()
        mock_mark.assert_not_awaited()

    async def test_dispatches_direct_when_should_notify(self) -> None:
        t = _transition(should_notify=True)
        mock_db = MagicMock()
        with (
            patch("services.ingestor.core.incident_notifications.settings") as mock_settings,
            patch(
                "services.ingestor.core.incident_notifications.dispatch_notification_event",
                new=AsyncMock(),
            ) as mock_dispatch,
            patch(
                "services.ingestor.core.incident_notifications.mark_notification_attempted",
                new=AsyncMock(),
            ) as mock_mark,
            patch(
                "services.ingestor.core.incident_notifications.dependency_incident_transitions_total"
            ) as mock_metrics,
        ):
            mock_settings.notification_delivery_mode = "direct"
            mock_metrics.labels.return_value.inc = MagicMock()
            await _dispatch_transitions(mock_db, [t])

        mock_dispatch.assert_awaited_once()
        mock_mark.assert_awaited_once_with(mock_db, t.incident)


# ---------------------------------------------------------------------------
# dispatch_incident_transitions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchIncidentTransitions:
    async def test_delegates_to_dispatch_transitions(self) -> None:
        t = _transition(should_notify=True)
        mock_db = MagicMock()
        with (
            patch(
                "services.ingestor.core.incident_notifications._dispatch_transitions",
                new=AsyncMock(),
            ) as mock_inner,
        ):
            await dispatch_incident_transitions(mock_db, [t])

        mock_inner.assert_awaited_once_with(mock_db, [t])


# ---------------------------------------------------------------------------
# record_health_sample — source not found
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordHealthSampleNotFound:
    async def test_raises_when_source_not_found(self) -> None:
        from services.ingestor.api_schemas.scorecards import HealthSampleCreate
        from services.ingestor.incident_lifecycle import record_health_sample

        mock_db = MagicMock()
        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Source not found"):
            await record_health_sample(
                mock_db,
                HealthSampleCreate(
                    source_id=1,
                    sampled_at=datetime(2025, 1, 1, tzinfo=UTC),
                    latency_ms=100.0,
                    is_success=True,
                ),
            )
