"""Incident-triage agent router (Phase 3).

JWT-authenticated (Phase 4, `docs/03-planning/audit-gaps.md` gap 🟠#6) — same
jwt_role_guard pattern already used in contract_drift.py/source_registry.py.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.agent import AgentRunResponse, AgentRunResumeRequest
from services.ingestor.auth import jwt_role_guard, verify_jwt_token
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.database import get_db
from services.ingestor.models import AgentRun
from services.ingestor.repositories.observations import get_user_by_username


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/agent", tags=["agent"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]
# writer: can approve/reject a paused run; admin/tenant_admin: full access
ReviewerJwtDep = Annotated[
    dict[str, Any], Depends(jwt_role_guard("writer", "admin", "tenant_admin"))
]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: int, db: DbDep, _: JwtDep) -> AgentRun:
    agent_run = await db.get(AgentRun, run_id)
    if agent_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found"
        )
    return agent_run


@router.post("/runs/{run_id}/resume", response_model=AgentRunResponse)
async def resume_agent_run_endpoint(
    run_id: int, body: AgentRunResumeRequest, db: DbDep, claims: ReviewerJwtDep
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

    # Spoof-proofing: reviewer_user_id always comes from the authenticated
    # caller's JWT, never from the request body — resolve the `sub` username
    # claim to the User row it identifies. Unresolvable (e.g. a token whose
    # subject has no matching active user) degrades to an unattributed
    # review rather than trusting a client-supplied id.
    reviewer = await get_user_by_username(db, str(claims.get("sub", "")))
    reviewer_user_id = reviewer.id if reviewer is not None else None

    from services.ingestor.agent.runner import resume_agent_run

    try:
        updated = await resume_agent_run(
            run_id,
            approve=body.approve,
            reviewer_user_id=reviewer_user_id,
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
