import json

import pytest

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    TOPIC_NOTIFICATION_DELIVERY_DLQ_V1,
    TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1,
)
from services.ingestor.notification_outbox_publisher import (
    notification_outbox_topic,
    outbox_retry_delay_seconds,
    serialize_outbox_payload,
)


pytestmark = pytest.mark.unit


def test_notification_event_topics_are_explicit_and_versioned() -> None:
    assert (
        notification_outbox_topic(EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1)
        == TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1
    )
    assert (
        notification_outbox_topic(EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1)
        == TOPIC_NOTIFICATION_DELIVERY_DLQ_V1
    )


def test_unknown_outbox_event_is_not_routed() -> None:
    with pytest.raises(ValueError, match="Unsupported notification outbox event"):
        notification_outbox_topic("observation.created")


def test_serialization_is_deterministic_compact_json() -> None:
    serialized = serialize_outbox_payload({"payload": {"b": 2, "a": 1}, "v": 1})
    assert serialized == b'{"payload":{"a":1,"b":2},"v":1}'
    assert json.loads(serialized) == {"payload": {"a": 1, "b": 2}, "v": 1}


def test_retry_backoff_is_exponential_and_capped() -> None:
    assert [outbox_retry_delay_seconds(attempt) for attempt in range(1, 5)] == [
        5,
        10,
        20,
        40,
    ]
    assert outbox_retry_delay_seconds(20) == 300
    with pytest.raises(ValueError, match="at least one"):
        outbox_retry_delay_seconds(0)
