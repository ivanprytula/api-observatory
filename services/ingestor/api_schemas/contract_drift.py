"""Pydantic v2 schemas for Contract Snapshot and Drift Detection APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from services.ingestor.constants import (
    CONTRACT_SCHEMA_VERSION_MAX,
    CONTRACT_SNAPSHOT_NOTE_MAX,
)


class ContractSnapshotCreate(BaseModel):
    """Request schema for storing a new contract snapshot."""

    source_id: int = Field(
        ..., ge=1, description="Source profile ID this snapshot belongs to."
    )
    payload_schema: dict[str, Any] = Field(
        ...,
        description=(
            "Observed payload-schema sample. Nested objects are allowed and will be "
            "flattened internally for drift comparison."
        ),
    )
    schema_version: str | None = Field(
        None,
        max_length=CONTRACT_SCHEMA_VERSION_MAX,
        description="Optional producer schema version label.",
    )
    snapshot_note: str | None = Field(
        None,
        max_length=CONTRACT_SNAPSHOT_NOTE_MAX,
        description="Optional context note (deployment id, run id, etc.).",
    )


class ContractSnapshotResponse(BaseModel):
    """Response schema for a persisted contract snapshot."""

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


class ContractSnapshotIngestResponse(BaseModel):
    """Response payload returned when ingesting a snapshot."""

    snapshot: ContractSnapshotResponse
    drift_event: DriftEventResponse | None


class DriftTypeChange(BaseModel):
    """Type transition details for a changed field."""

    from_type: str
    to_type: str


class DriftEventResponse(BaseModel):
    """Response schema for a detected drift event."""

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


class ContractSnapshotListResponse(BaseModel):
    """Paginated list of snapshots for one source."""

    items: list[ContractSnapshotResponse]
    total: int
    offset: int
    limit: int


class DriftEventListResponse(BaseModel):
    """Paginated list of drift events for one source."""

    items: list[DriftEventResponse]
    total: int
    offset: int
    limit: int


class CompatibilityReportResponse(BaseModel):
    """Compatibility report computed from the latest snapshots."""

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
