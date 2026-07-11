"""Orchestrates the incident-triage agent.

Owns the Postgres checkpointer's lifecycle (started/stopped from
`main.py`'s lifespan, mirroring how the scheduler and worker pool are
managed), builds initial graph state from an `AgentRun`/`Observation` pair,
runs the graph out-of-band (own DB sessions — never the caller's
request-scoped session), and syncs graph output back onto the `AgentRun` row.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from services.ingestor.config import settings
from services.ingestor.database import AsyncSessionLocal
from services.ingestor.models import AgentRun


if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.graph.state import CompiledStateGraph
    from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_graph: CompiledStateGraph | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sync_db_url() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def is_enabled() -> bool:
    return _graph is not None


async def start_agent_checkpointer() -> None:
    """Open the Postgres pool + checkpointer, compile the graph.

    Fail-open: if Anthropic isn't configured, the agent stays disabled and
    `run_agent_for_observation` becomes a no-op — drift detection and every
    other ingestor feature works regardless.
    """
    global _pool, _checkpointer, _graph
    if not settings.anthropic_enabled or not settings.anthropic_api_key:
        logger.info(
            "agent_disabled", extra={"reason": "anthropic not enabled/configured"}
        )
        return

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        from services.ingestor.agent.graph import build_graph
    except ImportError as exc:
        logger.warning(
            "agent_disabled", extra={"reason": f"ai extra not installed: {exc}"}
        )
        return

    _pool = AsyncConnectionPool(
        conninfo=_sync_db_url(),
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()
    _graph = build_graph(_checkpointer)
    logger.info("agent_checkpointer_started")


async def stop_agent_checkpointer() -> None:
    global _pool, _checkpointer, _graph
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None
    _graph = None


async def run_agent_for_observation(agent_run_id: int) -> None:
    """Entry point for the fire-and-forget trigger in
    `repositories/contract_drift.py`: run the graph up to the human_review
    pause. Never raises — failures are logged and reflected in
    `AgentRun.status`."""
    if _graph is None:
        logger.info(
            "agent_run_skipped",
            extra={"agent_run_id": agent_run_id, "reason": "agent disabled"},
        )
        return

    try:
        initial_state = await _build_initial_state(agent_run_id)
        if initial_state is None:
            return

        await _set_status(agent_run_id, "running")
        config = {"configurable": {"thread_id": str(agent_run_id)}}
        result = await _graph.ainvoke(initial_state, config=config)
        await _sync_agent_run(agent_run_id, result)
    except Exception as exc:
        logger.error(
            "agent_run_failed", extra={"agent_run_id": agent_run_id, "error": str(exc)}
        )
        await _set_status(agent_run_id, "failed")


async def resume_agent_run(
    agent_run_id: int, *, approve: bool, reviewer_user_id: int | None
) -> AgentRun | None:
    """Resume a paused run with a human decision. Raises `RuntimeError` if
    the agent isn't enabled — unlike the fire-and-forget trigger, a resume
    call is a direct API request and the caller needs to know it failed."""
    if _graph is None:
        raise RuntimeError("Incident-triage agent is not enabled")

    from langgraph.types import Command

    config = {"configurable": {"thread_id": str(agent_run_id)}}
    try:
        result = await _graph.ainvoke(
            Command(resume={"approve": approve, "reviewer_user_id": reviewer_user_id}),
            config=config,
        )
    except Exception as exc:
        logger.error(
            "agent_resume_failed",
            extra={"agent_run_id": agent_run_id, "error": str(exc)},
        )
        await _set_status(agent_run_id, "failed")
        return None

    return await _sync_agent_run(agent_run_id, result, resumed=True)


async def _build_initial_state(agent_run_id: int) -> dict[str, Any] | None:
    from services.ingestor.agent.state import AgentState
    from services.ingestor.repositories.observations import get_observation

    async with AsyncSessionLocal() as session:
        agent_run = await session.get(AgentRun, agent_run_id)
        if agent_run is None:
            logger.warning("agent_run_not_found", extra={"agent_run_id": agent_run_id})
            return None
        observation = await get_observation(session, agent_run.observation_id)
        if observation is None:
            logger.warning(
                "agent_run_observation_missing",
                extra={"agent_run_id": agent_run_id},
            )
            return None

        raw_data = observation.raw_data or {}
        incident_summary = (
            f"source={observation.source}, event_type={raw_data.get('event_type')}, "
            f"severity={raw_data.get('severity')}, summary={raw_data.get('summary')}"
        )
        state: AgentState = {
            "agent_run_id": agent_run.id,
            "observation_id": observation.id,
            "source": observation.source,
            "incident_summary": incident_summary,
            "rule_based_severity": raw_data.get("severity", "unknown"),
            "event_type": raw_data.get("event_type", "unknown"),
            "raw_data": raw_data,
            "llm_severity": None,
            "llm_severity_reasoning": None,
            "llm_agrees_with_rule": None,
            "retrieved_context": [],
            "root_cause_hypothesis": None,
            "recommended_action": None,
            "confidence_score": None,
            "review_decision": None,
            "reviewer_user_id": None,
        }
        return dict(state)


async def _set_status(agent_run_id: int, status: str) -> None:
    async with AsyncSessionLocal() as session:
        agent_run = await session.get(AgentRun, agent_run_id)
        if agent_run is not None:
            agent_run.status = status
            await session.commit()


async def _sync_agent_run(
    agent_run_id: int, result: dict[str, Any], *, resumed: bool = False
) -> AgentRun | None:
    """Persist graph output onto the AgentRun row. `result` may reflect a
    paused (interrupted) or completed run — LangGraph exposes the pause via
    an `__interrupt__` key in the returned state."""
    async with AsyncSessionLocal() as session:
        agent_run = await session.get(AgentRun, agent_run_id)
        if agent_run is None:
            return None

        if result.get("llm_severity") is not None:
            agent_run.severity_assessment = result["llm_severity"]
        if result.get("root_cause_hypothesis") is not None:
            agent_run.root_cause_hypothesis = result["root_cause_hypothesis"]
        if result.get("recommended_action") is not None:
            agent_run.recommended_action = result["recommended_action"]
        if result.get("confidence_score") is not None:
            agent_run.confidence_score = result["confidence_score"]

        if result.get("__interrupt__"):
            agent_run.status = "awaiting_review"
        elif resumed:
            agent_run.status = (
                "approved" if result.get("review_decision") else "rejected"
            )
            agent_run.reviewer_user_id = result.get("reviewer_user_id")
            agent_run.reviewed_at = _utcnow()

        await session.commit()
        await session.refresh(agent_run)
        return agent_run
