"""Pydantic v2 schemas for the Source Registry resource."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.ingestor.constants import (
    SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS,
    SOURCE_PROFILE_DESCRIPTION_MAX,
    SOURCE_PROFILE_NAME_MAX,
    SOURCE_PROFILE_OWNER_MAX,
    SOURCE_PROFILE_SCHEMA_VERSION_MAX,
    SOURCE_PROFILE_URL_MAX,
)


SourceType = Literal["rest", "webhook", "file", "graphql", "grpc"]


class SourceProfileCreate(BaseModel):
    """Request schema for registering a new source profile."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "openweather-current",
                    "url": "https://api.openweathermap.org/data/2.5/weather",
                    "source_type": "rest",
                    "description": "Current weather from OpenWeatherMap free tier.",
                    "auth_policy": {"type": "apikey", "header": "X-Api-Key"},
                    "quota_per_minute": 60,
                    "cost_per_call_usd": 0.0,
                    "expected_schema_version": "2.5",
                    "sla_ms": 800,
                    "tags": ["weather", "free-tier"],
                    "owner_team": "data-platform",
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
    url: str = Field(
        ...,
        min_length=1,
        max_length=SOURCE_PROFILE_URL_MAX,
        description="Base URL or endpoint of the source.",
        examples=["https://api.openweathermap.org/data/2.5/weather"],
    )
    source_type: SourceType = Field(
        ...,
        description="Protocol/transport type.",
        examples=["rest"],
    )
    description: str | None = Field(
        None,
        max_length=SOURCE_PROFILE_DESCRIPTION_MAX,
        description="Human-readable description of what this source provides.",
        examples=["Current weather from OpenWeatherMap free tier."],
    )
    auth_policy: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Authentication metadata. "
            "Shape: {type: bearer|apikey|none, header: str}. "
            "Secrets are NOT stored here."
        ),
        examples=[{"type": "apikey", "header": "X-Api-Key"}],
    )
    quota_per_minute: int | None = Field(
        None,
        ge=1,
        description="Maximum allowed requests per minute for this source.",
        examples=[60],
    )
    cost_per_call_usd: float | None = Field(
        None,
        ge=0.0,
        description="Estimated monetary cost per API call in USD.",
        examples=[0.0],
    )
    expected_schema_version: str | None = Field(
        None,
        max_length=SOURCE_PROFILE_SCHEMA_VERSION_MAX,
        description="The schema/API version this profile targets (used for drift detection).",
        examples=["2.5"],
    )
    sla_ms: int | None = Field(
        None,
        ge=1,
        description="Target SLA in milliseconds. Responses above this threshold are flagged.",
        examples=[800],
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form labels for grouping and filtering.",
        examples=[["weather", "free-tier"]],
    )
    owner_team: str | None = Field(
        None,
        max_length=SOURCE_PROFILE_OWNER_MAX,
        description="Team responsible for this source.",
        examples=["data-platform"],
    )

    @field_validator("tags")
    @classmethod
    def lowercase_tags(cls, v: list[str]) -> list[str]:
        """Normalise tags to lowercase for consistent filtering."""
        return [t.lower().strip() for t in v]


class SourceProfileUpdate(BaseModel):
    """Partial update schema — all fields optional."""

    url: str | None = Field(
        None,
        min_length=1,
        max_length=SOURCE_PROFILE_URL_MAX,
        description="Updated base URL.",
    )
    source_type: SourceType | None = Field(None, description="Updated source type.")
    description: str | None = Field(
        None,
        max_length=SOURCE_PROFILE_DESCRIPTION_MAX,
        description="Updated description.",
    )
    auth_policy: dict[str, Any] | None = Field(
        None,
        description="Replacement auth policy.",
    )
    quota_per_minute: int | None = Field(
        None, ge=1, description="Updated quota per minute."
    )
    cost_per_call_usd: float | None = Field(
        None, ge=0.0, description="Updated cost per call."
    )
    expected_schema_version: str | None = Field(
        None,
        max_length=SOURCE_PROFILE_SCHEMA_VERSION_MAX,
        description="Updated schema version target.",
    )
    sla_ms: int | None = Field(None, ge=1, description="Updated SLA target in ms.")
    tags: list[str] | None = Field(None, description="Replacement tag list.")
    owner_team: str | None = Field(
        None,
        max_length=SOURCE_PROFILE_OWNER_MAX,
        description="Updated owner team.",
    )
    is_active: bool | None = Field(None, description="Enable or disable this source.")

    @field_validator("tags")
    @classmethod
    def lowercase_tags(cls, v: list[str] | None) -> list[str] | None:
        """Normalise tags to lowercase."""
        if v is None:
            return v
        return [t.lower().strip() for t in v]


class SourceProfileResponse(BaseModel):
    """Response schema for a single source profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Auto-assigned primary key.")
    name: str = Field(..., description="Unique source identifier.")
    url: str = Field(..., description="Base URL of the source.")
    source_type: str = Field(..., description="Protocol/transport type.")
    description: str | None = Field(None, description="Human-readable description.")
    auth_policy: dict[str, Any] = Field(..., description="Auth metadata (no secrets).")
    quota_per_minute: int | None = Field(None, description="Max requests per minute.")
    cost_per_call_usd: float | None = Field(
        None, description="Estimated cost per call (USD)."
    )
    expected_schema_version: str | None = Field(
        None, description="Target API/schema version."
    )
    sla_ms: int | None = Field(None, description="Target SLA in ms.")
    tags: list[str] = Field(..., description="Labels for grouping.")
    is_active: bool = Field(..., description="Whether the source is enabled.")
    owner_team: str | None = Field(None, description="Owning team.")
    created_at: datetime = Field(..., description="Registration timestamp (UTC).")
    updated_at: datetime | None = Field(None, description="Last modification (UTC).")


class SourceProfileListResponse(BaseModel):
    """Paginated list of source profiles."""

    items: list[SourceProfileResponse] = Field(
        ..., description="Page of source profiles."
    )
    total: int = Field(..., description="Total matching records (unpaged).")
    offset: int = Field(..., description="Current page offset.")
    limit: int = Field(..., description="Page size used.")


class SourceHealthResponse(BaseModel):
    """Result of a live health probe against a source URL."""

    source_id: int = Field(..., description="ID of the probed source profile.")
    url: str = Field(..., description="URL that was probed.")
    reachable: bool = Field(
        ..., description="True if the source responded within the timeout."
    )
    status_code: int | None = Field(
        None, description="HTTP status code returned by the source."
    )
    latency_ms: float | None = Field(
        None, description="Round-trip latency in milliseconds."
    )
    sla_ms: int | None = Field(None, description="Configured SLA target in ms.")
    sla_breach: bool = Field(
        False,
        description=(
            f"True when latency_ms exceeds sla_ms "
            f"(or {SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS} ms default)."
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
    sources_by_type: dict[str, int] = Field(
        ..., description="Count of sources grouped by source_type."
    )
    avg_sla_ms: float | None = Field(
        None, description="Average SLA target across sources that have one set."
    )
    total_estimated_cost_per_minute_usd: float = Field(
        ...,
        description=(
            "Sum of (cost_per_call_usd * quota_per_minute) across all active sources."
        ),
    )
