"""Shared domain event contracts.

Contains event envelope and canonical event/topic names used across services.
"""

from __future__ import annotations

from typing import Any, TypedDict


EVENT_OBSERVATION_CREATED = "observation.created"
EVENT_DOC_SCRAPED = "doc.scraped"

TOPIC_OBSERVATION_CREATED = "observations.events"
TOPIC_SCRAPED = "scraped.events"


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
    "EventPayload",
    "ObservationCreatedPayload",
    "DocScrapedPayload",
    "EVENT_OBSERVATION_CREATED",
    "EVENT_DOC_SCRAPED",
    "TOPIC_OBSERVATION_CREATED",
    "TOPIC_SCRAPED",
]
