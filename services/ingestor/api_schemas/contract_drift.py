"""Pydantic schemas for Contract Snapshot and Drift Detection APIs.

Re-exports shared response models from libs.contracts.schemas_dashboard so
that both ingestor and dashboard use the same single source of truth.

Ingestor-only request models (ContractSnapshotCreate) and the combine
response (ContractSnapshotIngestResponse) remain defined here because they
are not consumed by the dashboard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from libs.contracts.constants import (
    CONTRACT_SCHEMA_VERSION_MAX,
    CONTRACT_SNAPSHOT_NOTE_MAX,
)
from libs.contracts.schemas_dashboard import (
    CompatibilityReportResponse,
    ContractSnapshotListResponse,
    ContractSnapshotResponse,
    DriftEventListResponse,
    DriftEventResponse,
    DriftTypeChange,
)


class ContractSnapshotCreate(BaseModel):
    """Request schema for storing a new contract snapshot."""

    source_id: int = Field(
        ...,
        ge=1,
        description="Source profile ID this snapshot belongs to.",
    )
    payload_schema: dict[str, Any] = Field(
        ...,
        description=(
            "Observed payload-schema sample. Nested objects and bounded array element "
            "shapes are flattened internally for drift comparison."
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


class ContractSnapshotIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot: ContractSnapshotResponse
    drift_event: DriftEventResponse | None


class ContractBaselineAcceptRequest(BaseModel):
    """Explicit operator acceptance of the source's current candidate contract."""

    candidate_snapshot_id: int | None = Field(
        None,
        ge=1,
        description="Current candidate snapshot to accept; defaults to the latest candidate.",
    )
    acceptance_note: str | None = Field(
        None,
        max_length=CONTRACT_SNAPSHOT_NOTE_MAX,
        description="Optional audit context for why this contract became accepted.",
    )


class ContractBaselineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    tenant_id: int | None
    baseline_snapshot_id: int
    promoted_from_baseline_id: int | None
    version: int
    status: str
    accepted_by: str
    accepted_at: datetime
    acceptance_note: str | None
    superseded_at: datetime | None
    candidate_snapshot_id: int | None
    candidate_observation_count: int
    candidate_drift_event_id: int | None
    candidate_first_seen_at: datetime | None
    candidate_last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


__all__ = [
    "CompatibilityReportResponse",
    "ContractBaselineAcceptRequest",
    "ContractBaselineResponse",
    "ContractSnapshotCreate",
    "ContractSnapshotIngestResponse",
    "ContractSnapshotListResponse",
    "ContractSnapshotResponse",
    "DriftEventListResponse",
    "DriftEventResponse",
    "DriftTypeChange",
]
