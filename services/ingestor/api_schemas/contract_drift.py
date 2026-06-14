"""Pydantic schemas for Contract Snapshot and Drift Detection APIs.

Re-exports shared response models from libs.contracts.schemas_dashboard so
that both ingestor and dashboard use the same single source of truth.

Ingestor-only request models (ContractSnapshotCreate) and the combine
response (ContractSnapshotIngestResponse) remain defined here because they
are not consumed by the dashboard.
"""

from __future__ import annotations

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


class ContractSnapshotIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot: ContractSnapshotResponse
    drift_event: DriftEventResponse | None


__all__ = [
    "CompatibilityReportResponse",
    "ContractSnapshotCreate",
    "ContractSnapshotIngestResponse",
    "ContractSnapshotListResponse",
    "ContractSnapshotResponse",
    "DriftEventListResponse",
    "DriftEventResponse",
    "DriftTypeChange",
]
