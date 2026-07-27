"""API schemas for tenant-scoped dependency incidents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from libs.contracts.schemas_dashboard import (
    DependencyIncidentListResponse,
    DependencyIncidentResponse,
)


class IncidentTransitionRequest(BaseModel):
    note: str | None = Field(None, max_length=1024)


__all__ = [
    "DependencyIncidentListResponse",
    "DependencyIncidentResponse",
    "IncidentTransitionRequest",
]
