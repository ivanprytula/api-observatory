"""Dashboard-specific Pydantic schemas.

These DTOs are shared across the ingestor ↔ dashboard boundary. They live in
libs.contracts (the approved cross-service namespace) so that the dashboard
can import them without violating the service-boundary guardrails enforced by
scripts/ci/check_service_boundaries.py.

Design rules
------------
- No imports from any service (services.ingestor, services.dashboard, …).
- May import from libs.contracts.constants for field bounds.
- Source of truth for models used across service boundaries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from libs.contracts.constants import (
    HEALTH_SAMPLE_ERROR_MSG_MAX,
    HEALTH_SAMPLE_REGION_MAX,
    SCORECARD_DEFAULT_SLO_TARGET_PCT,
)


# ---------------------------------------------------------------------------
# Contract Drift (cross-service)
# ---------------------------------------------------------------------------


class DriftTypeChange(BaseModel):
    from_type: str
    to_type: str


class DriftEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    previous_snapshot_id: int
    current_snapshot_id: int
    event_type: str
    severity: str
    added_fields: list[str]
    removed_fields: list[str]
    type_changed_fields: dict[str, DriftTypeChange]
    compatibility_score: float
    summary: str | None
    created_at: datetime


class DriftEventListResponse(BaseModel):
    items: list[DriftEventResponse]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Dependency incidents (cross-service)
# ---------------------------------------------------------------------------


class DependencyIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    tenant_id: int | None
    trigger_type: str
    status: str
    severity: str
    summary: str
    guidance: str
    trigger_details: dict
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    last_notification_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class DependencyIncidentListResponse(BaseModel):
    items: list[DependencyIncidentResponse]
    total: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)


# ---------------------------------------------------------------------------
# Source Registry (cross-service)
# ---------------------------------------------------------------------------


class SourceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Auto-assigned primary key.")
    name: str = Field(..., description="Unique source identifier.")
    base_url: str = Field(..., description="Base URL of the source.")
    health_check_path: str = Field(..., description="Path used for health checks.")
    probe_interval_seconds: int = Field(..., description="Probe cadence in seconds.")
    is_active: bool = Field(..., description="Whether the source is enabled.")
    tenant_id: int | None = Field(None, description="Owning tenant, when scoped.")
    latency_threshold_ms: float | None = Field(
        None, description="Configured sustained-latency incident threshold."
    )
    incident_failure_threshold: int = Field(
        ..., description="Consecutive unhealthy samples required to open an incident."
    )
    incident_cooldown_seconds: int = Field(
        ..., description="Notification cooldown for one active incident."
    )
    created_at: datetime = Field(..., description="Registration timestamp (UTC).")
    updated_at: datetime | None = Field(None, description="Last modification (UTC).")


class SourceProfileListResponse(BaseModel):
    items: list[SourceProfileResponse] = Field(
        ..., description="Page of source profiles."
    )
    total: int = Field(..., description="Total matching observations (unpaged).")
    offset: int = Field(..., description="Current page offset.")
    limit: int = Field(..., description="Page size used.")


class SourceHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
        description=("True when latency_ms exceeds the configured SLA threshold."),
    )
    error: str | None = Field(
        None, description="Error description if the source was unreachable."
    )


# ---------------------------------------------------------------------------
# Provider Scorecards (cross-service)
# ---------------------------------------------------------------------------


class ProviderScorecard(BaseModel):
    """Computed reliability scorecard for a single API provider."""

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
    items: list[ProviderScorecard]
    total: int


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


class HealthSampleResponse(BaseModel):
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
    created_at: datetime


# ---------------------------------------------------------------------------
# Contract Snapshot (cross-service, dashboard reads compatibility report)
# ---------------------------------------------------------------------------


class ContractSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    schema_version: str | None
    payload_schema: dict[str, Any]
    schema_fingerprint: str
    compatibility_score: float
    snapshot_note: str | None
    created_at: datetime
    updated_at: datetime | None


class ContractSnapshotListResponse(BaseModel):
    items: list[ContractSnapshotResponse]
    total: int
    offset: int
    limit: int


class CompatibilityReportResponse(BaseModel):
    source_id: int
    latest_snapshot_id: int | None
    previous_snapshot_id: int | None
    compatibility_score: float
    drift_detected: bool
    event_type: str | None
    severity: str | None
    added_fields: list[str]
    removed_fields: list[str]
    type_changed_fields: dict[str, DriftTypeChange]


# ---------------------------------------------------------------------------
# Observations (cross-service, read-only dashboard view)
# ---------------------------------------------------------------------------


class ObservationResponse(BaseModel):
    """Dashboard view of a single observation from the ingestor service."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Auto-incremented primary key.")
    source: str = Field(..., description="Origin identifier.")
    timestamp: datetime = Field(..., description="Observation timestamp (naive UTC).")
    raw_data: dict[str, Any] = Field(
        ..., description="The original data payload as stored."
    )
    tags: list[str] = Field(..., description="Labels applied to this observation.")
    processed: bool = Field(
        ..., description="True if the observation has been marked as processed."
    )
    created_at: datetime = Field(..., description="Row creation timestamp (UTC).")
    updated_at: datetime | None = Field(
        None, description="Last update timestamp (UTC), or null if never updated."
    )
    deleted_at: datetime | None = Field(
        None, description="Soft-delete timestamp (UTC), or null if not archived."
    )


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    total: int = Field(..., description="Total matching observations (unpaged).")
    skip: int = Field(..., description="Offset into result set.")
    limit: int = Field(..., description="Page size used in query.")
    has_more: bool = Field(
        ..., description="True if more results exist beyond current page."
    )


class ObservationListResponse(BaseModel):
    """Paginated list of observations from the ingestor service."""

    observations: list[ObservationResponse]
    pagination: PaginationMeta
