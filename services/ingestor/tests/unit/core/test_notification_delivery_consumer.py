"""Unit proof for provider-neutral notification delivery orchestration."""

from datetime import timedelta

import pytest

from services.ingestor.notification_delivery_consumer import (
    NotificationProviderError,
    notification_retry_delay,
    validate_notification_request,
)


pytestmark = pytest.mark.unit


def test_request_validation_rejects_unknown_contract_fields() -> None:
    with pytest.raises(ValueError, match="Invalid notification delivery request"):
        validate_notification_request(
            {
                "message_id": "incident:1:notification:1",
                "occurred_at": "2026-07-29T12:00:00Z",
                "payload": {
                    "incident_id": 1,
                    "source_id": 2,
                    "severity": "critical",
                    "summary": "Dependency unavailable.",
                    "trigger_type": "availability",
                    "occurrence_count": 1,
                    "guidance": "Check the provider.",
                    "channels": ["webhook"],
                    "unexpected": "rejected",
                },
            }
        )


def test_retry_delay_is_bounded_and_only_defined_for_retryable_attempts() -> None:
    first = notification_retry_delay(1)
    second = notification_retry_delay(2)
    assert timedelta(seconds=25) <= first <= timedelta(seconds=35)
    assert timedelta(seconds=270) <= second <= timedelta(seconds=330)
    with pytest.raises(ValueError, match="first two attempts"):
        notification_retry_delay(3)


def test_provider_error_carries_a_safe_classification() -> None:
    error = NotificationProviderError("rate_limit", "429")
    assert error.category == "rate_limit"
    assert error.code == "429"
    assert error.retryable is True
