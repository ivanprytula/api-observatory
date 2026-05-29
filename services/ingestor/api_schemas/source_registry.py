"""Pydantic v2 schemas for the Source Registry resource."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from services.ingestor.constants import (
    SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS,
    SOURCE_PROFILE_NAME_MAX,
    SOURCE_PROFILE_URL_MAX,
)


class SourceProfileCreate(BaseModel):
    """Request schema for registering a source profile."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "openweather-current",
                    "base_url": "https://api.openweathermap.org",
                    "health_check_path": "/data/2.5/weather",
                    "probe_interval_seconds": 60,
                    "is_active": True,
                }
            ]
        }
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=SOURCE_PROFILE_NAME_MAX,
        description="Unique human-readable identifier for this source (slug-style).",
        examples=["openweather-current"],
    )
    base_url: AnyHttpUrl = Field(
        ...,
        max_length=SOURCE_PROFILE_URL_MAX,
        description="Base URL used by server-side probes.",
        examples=["https://api.openweathermap.org"],
    )
    health_check_path: str = Field(
        "/health",
        min_length=1,
        max_length=255,
        description="Path appended to base_url for health probes.",
        examples=["/data/2.5/weather"],
    )
    probe_interval_seconds: int = Field(
        60,
        ge=1,
        description="How often this source should be probed by schedulers.",
        examples=[60],
    )
    is_active: bool = Field(
        True,
        description="Whether this source should be included in probe scheduling.",
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
    probe_interval_seconds: Annotated[int | None, Field(ge=1)] = None
    is_active: bool | None = Field(None, description="Enable or disable this source.")

    @field_validator("health_check_path")
    @classmethod
    def validate_health_check_path(cls, v: str | None) -> str | None:
        """Require an absolute path for safe URL joining."""
        if v is None:
            return v
        if not v.startswith("/"):
            raise ValueError("health_check_path must start with '/'.")
        return v


class SourceProfileResponse(BaseModel):
    """Response schema for a single source profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Auto-assigned primary key.")
    name: str = Field(..., description="Unique source identifier.")
    base_url: str = Field(..., description="Base URL of the source.")
    health_check_path: str = Field(..., description="Path used for health checks.")
    probe_interval_seconds: int = Field(..., description="Probe cadence in seconds.")
    is_active: bool = Field(..., description="Whether the source is enabled.")
    created_at: datetime = Field(..., description="Registration timestamp (UTC).")
    updated_at: datetime | None = Field(None, description="Last modification (UTC).")


class SourceProfileListResponse(BaseModel):
    """Paginated list of source profiles."""

    items: list[SourceProfileResponse] = Field(
        ..., description="Page of source profiles."
    )
    total: int = Field(..., description="Total matching observations (unpaged).")
    offset: int = Field(..., description="Current page offset.")
    limit: int = Field(..., description="Page size used.")


class SourceHealthResponse(BaseModel):
    """Result of a live health probe against a source URL."""

    source_id: int = Field(..., description="ID of the probed source profile.")
    target_url: str = Field(..., description="Resolved URL that was probed.")
    reachable: bool = Field(
        ..., description="True if the source responded within the timeout."
    )
    status_code: int | None = Field(
        None, description="HTTP status code returned by the source."
    )
    latency_ms: float | None = Field(
        None, description="Round-trip latency in milliseconds."
    )
    sla_breach: bool = Field(
        False,
        description=(
            f"True when latency_ms exceeds "
            f"{SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS} ms threshold."
        ),
    )
    error: str | None = Field(
        None, description="Error description if the source was unreachable."
    )


class SourceSummaryResponse(BaseModel):
    """Aggregate statistics over all registered source profiles."""

    total_sources: int = Field(..., description="Total registered source profiles.")
    active_sources: int = Field(..., description="Currently active source profiles.")
    inactive_sources: int = Field(..., description="Deactivated source profiles.")
    avg_probe_interval_seconds: float | None = Field(
        None, description="Average probe interval across all source profiles."
    )
