"""Pydantic schemas for Source Registry endpoints.

Re-exports shared response models from libs.contracts.schemas_dashboard so
that both ingestor and dashboard use the same single source of truth.

Internal request/response models that are ingestor-only
(SourceProfileCreate, SourceProfileUpdate, SourceSummaryResponse) remain
defined here.
"""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from libs.contracts.constants import (
    SOURCE_PROFILE_NAME_MAX,
    SOURCE_PROFILE_URL_MAX,
)
from libs.contracts.schemas_dashboard import (
    SourceHealthResponse,
    SourceProfileListResponse,
    SourceProfileResponse,
)


# ---------------------------------------------------------------------------
# Ingestor-only request/response models
# ---------------------------------------------------------------------------


class SourceProfileCreate(BaseModel):
    """Request schema for registering a source profile."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=SOURCE_PROFILE_NAME_MAX,
        description="Unique human-readable identifier for this source (slug-style).",
    )
    base_url: AnyHttpUrl = Field(
        ...,
        max_length=SOURCE_PROFILE_URL_MAX,
        description="Base URL used by server-side probes.",
    )
    health_check_path: str = Field(
        "/health",
        min_length=1,
        max_length=255,
        description="Path appended to base_url for health probes.",
    )
    probe_interval_seconds: int = Field(
        60,
        ge=1,
        description="How often this source should be probed by schedulers.",
    )
    is_active: bool = Field(
        True,
        description="Whether this source should be included in probe scheduling.",
    )
    latency_threshold_ms: float | None = Field(
        None,
        gt=0,
        description="Optional sustained-latency threshold that opens an incident.",
    )
    incident_failure_threshold: int = Field(
        2,
        ge=1,
        le=20,
        description="Consecutive unhealthy samples required before opening an incident.",
    )
    incident_cooldown_seconds: int = Field(
        900,
        ge=0,
        le=86400,
        description="Minimum interval between notifications for one active incident.",
    )
    auth_type: str = Field(
        "none",
        description="Outbound auth mode: none, bearer, header, or basic.",
    )
    api_key: str | None = Field(
        None,
        max_length=2048,
        description="Secret value (API key, bearer token, or basic password).",
    )
    auth_header_name: str = Field(
        "Authorization",
        max_length=128,
        description="Header name when auth_type is header or bearer.",
    )
    auth_username: str | None = Field(
        None,
        max_length=255,
        description="Username for basic auth.",
    )

    @field_validator("health_check_path")
    @classmethod
    def validate_health_check_path(cls, v: str) -> str:
        """Require an absolute path for safe URL joining."""
        if not v.startswith("/"):
            raise ValueError("health_check_path must start with '/'.")
        return v


class SourceProfileUpdate(BaseModel):
    """Partial update schema — all fields optional."""

    base_url: AnyHttpUrl | None = Field(
        None,
        max_length=SOURCE_PROFILE_URL_MAX,
        description="Updated base URL.",
    )
    health_check_path: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Updated health check path.",
    )
    probe_interval_seconds: int | None = Field(
        None, ge=1, description="Updated probe cadence in seconds."
    )
    is_active: bool | None = Field(None, description="Enable or disable this source.")
    latency_threshold_ms: float | None = Field(
        None, gt=0, description="Updated sustained-latency incident threshold."
    )
    incident_failure_threshold: int | None = Field(
        None, ge=1, le=20, description="Updated consecutive-failure threshold."
    )
    incident_cooldown_seconds: int | None = Field(
        None, ge=0, le=86400, description="Updated notification cooldown."
    )
    auth_type: str | None = Field(None, description="Outbound auth mode.")
    api_key: str | None = Field(
        None, max_length=2048, description="Secret value (write-only)."
    )
    auth_header_name: str | None = Field(
        None, max_length=128, description="Header name for header or bearer auth."
    )
    auth_username: str | None = Field(
        None, max_length=255, description="Basic auth username (write-only)."
    )

    @field_validator("health_check_path")
    @classmethod
    def validate_health_check_path(cls, v: str | None) -> str | None:
        """Require an absolute path for safe URL joining."""
        if v is None:
            return v
        if not v.startswith("/"):
            raise ValueError("health_check_path must start with '/'.")
        return v


class SourceSummaryResponse(BaseModel):
    """Aggregate statistics over all registered source profiles."""

    total_sources: int = Field(..., description="Total registered source profiles.")
    active_sources: int = Field(..., description="Currently active source profiles.")
    inactive_sources: int = Field(..., description="Deactivated source profiles.")
    avg_probe_interval_seconds: float | None = Field(
        None, description="Average probe interval across all source profiles."
    )


__all__ = [
    "SourceProfileCreate",
    "SourceProfileUpdate",
    "SourceProfileResponse",
    "SourceProfileListResponse",
    "SourceHealthResponse",
    "SourceSummaryResponse",
]
