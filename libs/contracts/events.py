"""Shared domain event contracts.

Contains event envelope and canonical event/topic names used across services.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EVENT_OBSERVATION_CREATED = "observation.created"
EVENT_DOC_SCRAPED = "doc.scraped"
EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1 = "notification.delivery_requested.v1"
EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1 = "notification.delivery_dead_lettered.v1"

TOPIC_OBSERVATION_CREATED = "observations.events"
TOPIC_SCRAPED = "scraped.events"
TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1 = "notifications.delivery.requests.v1"
TOPIC_NOTIFICATION_DELIVERY_DLQ_V1 = "notifications.delivery.dlq.v1"

type NotificationChannel = Literal["slack", "telegram", "webhook", "email"]
type NotificationTriggerType = Literal["availability", "latency", "drift"]
type NotificationErrorCategory = Literal[
    "malformed",
    "configuration",
    "unsupported",
    "transport",
    "rate_limit",
    "provider",
    "unknown",
]


class ObservationCreatedPayload(TypedDict, total=False):
    """Payload contract for observation.created events."""

    observation_id: int
    source: str
    timestamp: str
    data: dict[str, Any]
    tags: list[str]


class DocScrapedPayload(TypedDict):
    """Payload contract for doc.scraped events."""

    source: str
    count: int


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(UTC)


class NotificationDeliveryRequestedPayloadV1(BaseModel):
    """Safe incident context required to dispatch configured channels."""

    model_config = ConfigDict(extra="forbid")

    incident_id: int = Field(..., ge=1)
    source_id: int = Field(..., ge=1)
    tenant_id: int | None = Field(default=None, ge=1)
    severity: str = Field(..., min_length=1, max_length=32)
    summary: str = Field(..., min_length=1, max_length=1024)
    trigger_type: NotificationTriggerType
    occurrence_count: int = Field(..., ge=1)
    guidance: str = Field(..., min_length=1, max_length=2048)
    channels: list[NotificationChannel] = Field(..., min_length=1, max_length=4)

    @field_validator("channels")
    @classmethod
    def channels_are_unique(
        cls, channels: list[NotificationChannel]
    ) -> list[NotificationChannel]:
        if len(channels) != len(set(channels)):
            raise ValueError("channels must be unique")
        return channels


class NotificationDeliveryRequestedV1(BaseModel):
    """Versioned request consumed by the notification-delivery worker."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["notification.delivery_requested.v1"] = (
        EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1
    )
    message_id: str = Field(..., min_length=1, max_length=255)
    occurred_at: datetime
    payload: NotificationDeliveryRequestedPayloadV1

    _normalize_occurred_at = field_validator("occurred_at")(_require_utc)


class NotificationDeliveryDeadLetteredPayloadV1(BaseModel):
    """Sanitized terminal delivery metadata safe for the DLQ topic."""

    model_config = ConfigDict(extra="forbid")

    delivery_id: int = Field(..., ge=1)
    request_message_id: str = Field(..., min_length=1, max_length=255)
    incident_id: int = Field(..., ge=1)
    source_id: int = Field(..., ge=1)
    tenant_id: int | None = Field(default=None, ge=1)
    channel: NotificationChannel
    attempt_count: int = Field(..., ge=1, le=3)
    error_category: NotificationErrorCategory
    error_code: str | None = Field(default=None, max_length=64)
    first_attempt_at: datetime
    last_attempt_at: datetime

    _normalize_first_attempt_at = field_validator("first_attempt_at")(_require_utc)
    _normalize_last_attempt_at = field_validator("last_attempt_at")(_require_utc)

    @model_validator(mode="after")
    def attempt_timestamps_are_ordered(self):
        if self.last_attempt_at < self.first_attempt_at:
            raise ValueError("last_attempt_at must not precede first_attempt_at")
        return self


class NotificationDeliveryDeadLetteredV1(BaseModel):
    """Versioned, sanitized terminal event published through the outbox."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["notification.delivery_dead_lettered.v1"] = (
        EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1
    )
    message_id: str = Field(..., min_length=1, max_length=255)
    occurred_at: datetime
    payload: NotificationDeliveryDeadLetteredPayloadV1

    _normalize_occurred_at = field_validator("occurred_at")(_require_utc)


class EventPayload[T]:
    """Typed event envelope.

    Generic over payload type to keep producers/consumers type-safe.
    """

    def __init__(self, event_type: str, payload: T) -> None:
        self.event_type = event_type
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-encodable dictionary."""
        return {"event_type": self.event_type, "payload": self.payload}


__all__ = [
    "DocScrapedPayload",
    "EVENT_DOC_SCRAPED",
    "EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1",
    "EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1",
    "EVENT_OBSERVATION_CREATED",
    "EventPayload",
    "NotificationChannel",
    "NotificationDeliveryDeadLetteredPayloadV1",
    "NotificationDeliveryDeadLetteredV1",
    "NotificationDeliveryRequestedPayloadV1",
    "NotificationDeliveryRequestedV1",
    "NotificationErrorCategory",
    "NotificationTriggerType",
    "ObservationCreatedPayload",
    "TOPIC_NOTIFICATION_DELIVERY_DLQ_V1",
    "TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1",
    "TOPIC_OBSERVATION_CREATED",
    "TOPIC_SCRAPED",
]
