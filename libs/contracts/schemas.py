"""Shared DTO contracts for cross-service API boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""

    total: int
    skip: int
    limit: int
    has_more: bool


class NotificationDispatchResult(BaseModel):
    """One channel dispatch result for notification deliveries."""

    channel: str
    status: str
    detail: str


class BatchCreateResponse(BaseModel):
    """Response from batch create endpoint."""

    created: int
    impl: str


class SessionResponse(BaseModel):
    """Session/login response payload."""

    session_id: str
    message: str


class ScrapeResponse(BaseModel):
    """Scraper endpoint response payload."""

    source: str
    scraped: int
    stored: int


class BackgroundBatchSubmitResponse(BaseModel):
    """Response from background batch ingestion submission endpoint."""

    task_id: str
    status: str
    batch_size: int
    queued_at: datetime


class BackgroundTaskStatusResponse(BaseModel):
    """Status response for a submitted background task."""

    task_id: str
    status: str
    batch_size: int
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class NotificationTestRequest(BaseModel):
    """Request payload for notification test endpoint."""

    message: str = Field(..., min_length=1, max_length=2000)
    severity: str = Field(default="info")
    event: str = Field(default="notification_test")
    channels: list[Literal["slack", "telegram", "webhook", "email"]] | None = None


class NotificationTestResponse(BaseModel):
    """Response payload for notification test endpoint."""

    event: str
    severity: str
    sent: int
    failed: int
    results: list[NotificationDispatchResult] = Field(default_factory=list)
    detail: str | None = None


class VectorSearchResult(BaseModel):
    """One semantic-search match returned by the AI gateway."""

    id: int
    score: float
    metadata: dict[str, Any]


class VectorSearchQueryResponse(BaseModel):
    """Semantic-search response for indexed records."""

    results: list[VectorSearchResult]
    count: int
    query: str
    collection: str


class VectorSearchIndexResponse(BaseModel):
    """Response from indexing records into the AI gateway."""

    requested_count: int
    indexed_count: int
    missing_record_ids: list[int] = Field(default_factory=list)
    collection: str


class VectorSearchHealthResponse(BaseModel):
    """Health status of the inference service bridge."""

    status: str
    inference_connected: bool
    collection: str


__all__ = [
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
