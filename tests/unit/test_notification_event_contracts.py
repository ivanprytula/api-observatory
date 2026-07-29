"""Unit tests for versioned notification-delivery event contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    NotificationDeliveryDeadLetteredV1,
    NotificationDeliveryRequestedV1,
)


pytestmark = pytest.mark.unit


def _request_payload() -> dict:
    return {
        "event_type": EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
        "message_id": "incident:7:notification:2",
        "occurred_at": "2026-07-29T12:00:00Z",
        "payload": {
            "incident_id": 7,
            "source_id": 3,
            "tenant_id": 11,
            "severity": "critical",
            "summary": "Dependency unavailable.",
            "trigger_type": "availability",
            "occurrence_count": 2,
            "guidance": "Verify the dependency independently.",
            "channels": ["webhook", "email"],
        },
    }


def _dead_letter_payload() -> dict:
    return {
        "event_type": EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
        "message_id": "notification-delivery-dlq:41",
        "occurred_at": "2026-07-29T12:06:00Z",
        "payload": {
            "delivery_id": 41,
            "request_message_id": "incident:7:notification:2",
            "incident_id": 7,
            "source_id": 3,
            "tenant_id": 11,
            "channel": "webhook",
            "attempt_count": 3,
            "error_category": "transport",
            "error_code": "timeout",
            "first_attempt_at": "2026-07-29T12:00:00Z",
            "last_attempt_at": "2026-07-29T12:05:00Z",
        },
    }


def test_requested_event_is_strict_and_normalizes_utc() -> None:
    event = NotificationDeliveryRequestedV1.model_validate(_request_payload())

    assert event.occurred_at == datetime(2026, 7, 29, 12, tzinfo=UTC)
    assert event.payload.channels == ["webhook", "email"]
    assert event.model_dump(mode="json")["event_type"].endswith(".v1")


def test_requested_event_rejects_duplicate_channels() -> None:
    raw = _request_payload()
    raw["payload"]["channels"] = ["webhook", "webhook"]

    with pytest.raises(ValidationError, match="channels must be unique"):
        NotificationDeliveryRequestedV1.model_validate(raw)


def test_requested_event_rejects_naive_timestamp_and_extra_fields() -> None:
    raw = _request_payload()
    raw["occurred_at"] = "2026-07-29T12:00:00"
    raw["destination"] = "https://should-not-be-present.example"

    with pytest.raises(ValidationError):
        NotificationDeliveryRequestedV1.model_validate(raw)


def test_dead_letter_event_contains_only_sanitized_contract_fields() -> None:
    event = NotificationDeliveryDeadLetteredV1.model_validate(_dead_letter_payload())
    serialized = event.model_dump(mode="json")

    assert set(serialized["payload"]) == {
        "delivery_id",
        "request_message_id",
        "incident_id",
        "source_id",
        "tenant_id",
        "channel",
        "attempt_count",
        "error_category",
        "error_code",
        "first_attempt_at",
        "last_attempt_at",
    }
    assert not {
        "destination",
        "authorization",
        "provider_response",
        "original_payload",
    }.intersection(serialized["payload"])


def test_dead_letter_event_rejects_reversed_attempt_timestamps() -> None:
    raw = _dead_letter_payload()
    raw["payload"]["last_attempt_at"] = "2026-07-29T11:59:00Z"

    with pytest.raises(ValidationError, match="must not precede"):
        NotificationDeliveryDeadLetteredV1.model_validate(raw)
