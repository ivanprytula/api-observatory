"""libs.contracts — shared data contracts across service boundaries.

Intended contents (define in Phase 3, services adopt in Phase 4):
- events     : domain event envelopes (ObservationIngested, ObservationProcessed, …)
- schemas    : shared Pydantic v2 request/response DTOs used by >1 service
- types      : common type aliases and enumerations (ObservationStatus, SourceType, …)
- pagination : standard paginated response wrapper

Design constraints:
- Pydantic v2 only; no SQLAlchemy ORM types (those stay in each service)
- No imports from any service (ingestor, services/*)
- May import from libs.platform only for logging helpers
- Keep modules small and focused — one concept per file

Usage pattern (once populated):
    from libs.contracts.events import ObservationIngested
    from libs.contracts.schemas import PaginatedResponse
    from libs.contracts.types import ObservationStatus
"""

from libs.contracts.events import (
    EVENT_DOC_SCRAPED,
    EVENT_OBSERVATION_CREATED,
    TOPIC_OBSERVATION_CREATED,
    TOPIC_SCRAPED,
    DocScrapedPayload,
    EventPayload,
    ObservationCreatedPayload,
)
from libs.contracts.schemas import (
    BackgroundBatchSubmitResponse,
    BackgroundTaskStatusResponse,
    BatchCreateResponse,
    NotificationDispatchResult,
    NotificationTestRequest,
    NotificationTestResponse,
    PaginationMeta,
    ScrapeResponse,
    SessionResponse,
    VectorSearchHealthResponse,
    VectorSearchIndexResponse,
    VectorSearchQueryResponse,
    VectorSearchResult,
)


__all__ = [
    "EventPayload",
    "ObservationCreatedPayload",
    "DocScrapedPayload",
    "EVENT_OBSERVATION_CREATED",
    "EVENT_DOC_SCRAPED",
    "TOPIC_OBSERVATION_CREATED",
    "TOPIC_SCRAPED",
    "PaginationMeta",
    "NotificationDispatchResult",
    "BatchCreateResponse",
    "SessionResponse",
    "ScrapeResponse",
    "BackgroundBatchSubmitResponse",
    "BackgroundTaskStatusResponse",
    "NotificationTestRequest",
    "NotificationTestResponse",
    "VectorSearchResult",
    "VectorSearchQueryResponse",
    "VectorSearchIndexResponse",
    "VectorSearchHealthResponse",
]

# Expose the canonical contracts version from the sibling VERSION file.
from pathlib import Path


try:
    VERSION = (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip()
except Exception:
    VERSION = "0.0.0"

__all__.append("VERSION")
