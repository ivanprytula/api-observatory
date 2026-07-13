"""Pydantic schemas for the incident-triage agent API (Phase 3)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    observation_id: int
    status: str
    root_cause_hypothesis: str | None
    severity_assessment: str | None
    recommended_action: str | None
    confidence_score: float | None
    reviewer_user_id: int | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime | None


class AgentRunResumeRequest(BaseModel):
    approve: bool
    # No reviewer_user_id field here on purpose: it's derived server-side from
    # the caller's authenticated JWT (`sub` -> User.id lookup in the router),
    # never taken from the request body — a client-supplied reviewer id would
    # let any writer/admin token attribute an approval to an arbitrary user.
