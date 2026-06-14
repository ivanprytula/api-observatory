"""Dashboard data models — re-exported cross-service contracts.

This module is a thin adapter layer. It imports shared Pydantic models from
libs.contracts.schemas_dashboard so that the dashboard core layer depends only
on services.dashboard.core.models, not directly on libs.contracts.

Single-source-of-truth lives in:
    libs/contracts/schemas_dashboard.py
"""

from __future__ import annotations

from libs.contracts.schemas_dashboard import (
    CompatibilityReportResponse,
    ContractSnapshotResponse,
    DriftEventListResponse,
    DriftEventResponse,
    DriftTypeChange,
    ProviderScorecard,
    ScorecardListResponse,
    SourceHealthResponse,
    SourceProfileListResponse,
    SourceProfileResponse,
)


__all__ = [
    "CompatibilityReportResponse",
    "ContractSnapshotResponse",
    "DriftEventResponse",
    "DriftEventListResponse",
    "DriftTypeChange",
    "ProviderScorecard",
    "ScorecardListResponse",
    "SourceHealthResponse",
    "SourceProfileListResponse",
    "SourceProfileResponse",
]
