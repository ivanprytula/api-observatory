from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.ingestor.constants import (
    ABUSE_ACTION_LOGGED,
    ABUSE_ACTOR_ID_MAX_LEN,
    ABUSE_NOTES_MAX_LEN,
    ABUSE_SEVERITY_MEDIUM,
    ABUSE_SIGNAL_SUSPICIOUS_KEY,
)


# ---------------------------------------------------------------------------
# Shared validators / config
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


# ---------------------------------------------------------------------------
# Create (manual signal injection)
# ---------------------------------------------------------------------------


class AbuseSignalCreate(_Base):
    """Payload for manually raising an abuse signal (admin only)."""

    signal_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        examples=[ABUSE_SIGNAL_SUSPICIOUS_KEY],
        description=(
            "noisy_source | suspicious_key | burst_abuse | "
            "credential_stuffing | ip_rotation"
        ),
    )
    actor_type: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="api_key | source_id | ip_address | tenant_id",
    )
    actor_id: str = Field(..., min_length=1, max_length=ABUSE_ACTOR_ID_MAX_LEN)
    severity: str = Field(
        default=ABUSE_SEVERITY_MEDIUM,
        min_length=1,
        max_length=16,
        description="low | medium | high | critical",
    )
    detection_rule: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "quota_exceeded | auth_failure_spike | multi_ip_key | "
            "error_rate_spike | rapid_enumeration"
        ),
    )
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Machine-readable evidence bag (counts, thresholds, window).",
    )
    action_taken: str = Field(
        default=ABUSE_ACTION_LOGGED,
        min_length=1,
        max_length=32,
        description="logged | rate_limited | blocked | alerted",
    )
    tenant_id: int | None = Field(default=None, ge=1)
    ip_address: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=ABUSE_NOTES_MAX_LEN)


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------


class AbuseSignalResolve(_Base):
    """Payload for marking a signal as resolved."""

    resolved_by: str = Field(..., min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=ABUSE_NOTES_MAX_LEN)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class AbuseSignalResponse(_Base):
    """Full signal representation returned by GET / POST endpoints."""

    id: int
    signal_type: str
    actor_type: str
    actor_id: str
    severity: str
    detection_rule: str
    evidence: dict[str, Any]
    action_taken: str
    tenant_id: int | None
    ip_address: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None


class AbuseSignalListResponse(_Base):
    """Paginated list of abuse signals."""

    items: list[AbuseSignalResponse]
    total: int
    page: int
    page_size: int


class AbuseSeverityCount(_Base):
    severity: str
    count: int


class AbuseTopActor(_Base):
    actor_type: str
    actor_id: str
    signal_count: int
    latest_severity: str


class AbuseSummaryResponse(_Base):
    """Aggregate stats for the abuse dashboard."""

    open_count: int
    resolved_count: int
    by_severity: list[AbuseSeverityCount]
    top_actors: list[AbuseTopActor]
