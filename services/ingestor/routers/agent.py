"""Incident-triage agent router (Phase 3).

No auth yet — Phase 4 closes that gap (`docs/03-planning/audit-gaps.md`
gap 🟠#6), same as `observations.py`/`vector_search.py` today.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.agent import AgentRunResponse, AgentRunResumeRequest
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.database import get_db
from services.ingestor.models import AgentRun


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/agent", tags=["agent"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: int, db: DbDep) -> AgentRun:
    agent_run = await db.get(AgentRun, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    return agent_run


@router.post("/runs/{run_id}/resume", response_model=AgentRunResponse)
async def resume_agent_run_endpoint(
    run_id: int, body: AgentRunResumeRequest, db: DbDep
) -> AgentRun:
    agent_run = await db.get(AgentRun, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    if agent_run.status != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent run is '{agent_run.status}', not awaiting review",
        )

    from services.ingestor.agent.runner import resume_agent_run

    try:
        updated = await resume_agent_run(
            run_id,
            approve=body.approve,
            reviewer_user_id=body.reviewer_user_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent run resume failed — see server logs",
        )
    return updated
