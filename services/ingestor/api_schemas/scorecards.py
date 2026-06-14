"""Pydantic schemas for Provider Scorecard endpoints.

Re-exports shared models from libs.contracts.schemas_dashboard so that
both ingestor and dashboard use the same single source of truth.

Request-only schema HealthSampleCreate and the non-shared
HealthSampleResponse both remain defined here because they are internal to
the ingestor.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from libs.contracts.constants import (
    HEALTH_SAMPLE_ERROR_MSG_MAX,
    HEALTH_SAMPLE_REGION_MAX,
)
from libs.contracts.schemas_dashboard import (
    ProviderScorecard,
    ScorecardListResponse,
)


class HealthSampleCreate(BaseModel):
    """Request body for observing one provider health probe."""

    source_id: int = Field(..., ge=1, description="Source profile ID being probed.")
    sampled_at: datetime = Field(..., description="UTC timestamp when the probe ran.")
    latency_ms: float = Field(
        ..., ge=0.0, description="End-to-end probe latency in milliseconds."
    )
    is_success: bool = Field(..., description="True if the probe succeeded.")
    http_status: int | None = Field(
        None,
        ge=100,
        le=599,
        description="HTTP status code returned by the provider.",
    )
    response_body_hash: str | None = Field(
        None,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the probe response body.",
    )
    error_message: str | None = Field(
        None,
        max_length=HEALTH_SAMPLE_ERROR_MSG_MAX,
        description="Error detail when the probe fails.",
    )
    region: str | None = Field(
        None,
        max_length=HEALTH_SAMPLE_REGION_MAX,
        description="Optional probe region label, e.g. eu-west-1.",
    )
    tenant_id: int | None = Field(
        None,
        ge=1,
        description="Tenant scope for multi-tenant deployments.",
    )


class HealthSampleResponse(BaseModel):
    """Single health probe observation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    sampled_at: datetime
    latency_ms: float
    is_success: bool
    http_status: int | None
    response_body_hash: str | None
    error_message: str | None
    region: str | None
    tenant_id: int | None
    created_at: datetime


__all__ = [
    "HealthSampleCreate",
    "HealthSampleResponse",
    "ProviderScorecard",
    "ScorecardListResponse",
]
