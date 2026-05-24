"""Pydantic schemas for Provider Scorecard endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from services.ingestor.constants import (
    HEALTH_SAMPLE_ERROR_MSG_MAX,
    HEALTH_SAMPLE_REGION_MAX,
    SCORECARD_DEFAULT_SLO_TARGET_PCT,
)


class HealthSampleCreate(BaseModel):
    """Request body for recording one provider health probe."""

    source_id: int = Field(..., ge=1, description="Source profile ID being probed.")
    sampled_at: datetime = Field(..., description="UTC timestamp when the probe ran.")
    latency_ms: float = Field(
        ..., ge=0.0, description="End-to-end probe latency in milliseconds."
    )
    is_success: bool = Field(..., description="True if the probe succeeded.")
    http_status: int | None = Field(
        None, ge=100, le=599, description="HTTP status code returned by the provider."
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
        None, ge=1, description="Tenant scope for multi-tenant deployments."
    )


class HealthSampleResponse(BaseModel):
    """Single health probe record returned by the API."""

    model_config = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: int
    source_id: int
    sampled_at: datetime
    latency_ms: float
    is_success: bool
    http_status: int | None
    error_message: str | None
    region: str | None
    tenant_id: int | None
    created_at: datetime


class ProviderScorecard(BaseModel):
    """Computed reliability scorecard for a single API provider.

    Aggregates health samples within a time window into the three headline
    BI metrics: uptime %, p95 latency, and error-budget burn rate.

    Error-budget burn rate measures how fast the provider consumes its
    allowed downtime.  A rate of 1.0 means consuming exactly at budget;
    >1.0 means burning faster (will exhaust the budget before the window
    closes); <1.0 means comfortable headroom.

    Formula:
        error_budget_burn_rate = error_rate / (1.0 - slo_target_pct / 100)
    where error_rate = 1.0 - uptime_pct / 100.
    """

    source_id: int = Field(..., description="Source profile ID.")
    source_name: str = Field(..., description="Human-readable source name.")
    window_days: int = Field(
        ..., description="Number of days covered by this scorecard."
    )
    sample_count: int = Field(..., ge=0, description="Total probes in the window.")
    error_count: int = Field(..., ge=0, description="Failed probes in the window.")
    uptime_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Uptime percentage (success / total * 100)."
    )
    avg_latency_ms: float = Field(..., ge=0.0, description="Mean latency in ms.")
    p50_latency_ms: float = Field(..., ge=0.0, description="Median latency in ms.")
    p95_latency_ms: float = Field(
        ..., ge=0.0, description="95th-percentile latency in ms."
    )
    slo_target_pct: float = Field(
        ...,
        ge=90.0,
        le=100.0,
        description=f"SLO uptime target %. Default {SCORECARD_DEFAULT_SLO_TARGET_PCT}.",
    )
    error_budget_burn_rate: float = Field(
        ...,
        ge=0.0,
        description=(
            "Error-budget consumption rate. "
            "1.0 = on-budget; >1.0 = burning faster than budget allows."
        ),
    )
    generated_at: datetime = Field(
        ..., description="UTC timestamp this scorecard was computed."
    )


class ScorecardListResponse(BaseModel):
    """Paginated list of provider scorecards."""

    items: list[ProviderScorecard]
    total: int
