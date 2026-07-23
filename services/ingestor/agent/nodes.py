"""LangGraph node functions for the incident-triage agent.

Each node is `async def node(state: AgentState) -> dict` — LangGraph merges
the returned dict into state. Nodes are thin: LLM calls go through
`agent.llm.get_chat_model`, RAG through the existing
`services.ingestor.vector_search` bridge (Phase 2), notifications through
the existing `services.ingestor.notifications` module — no new mechanisms.
"""

from __future__ import annotations

import logging
from typing import Any


try:
    from langgraph.types import interrupt
except ModuleNotFoundError:
    interrupt = None

from libs.platform.llm_metrics import record_llm_usage
from services.ingestor import notifications
from services.ingestor import vector_search as vs_bridge
from services.ingestor.agent.llm import get_chat_model
from services.ingestor.agent.schemas import DraftAnalysis, SeverityClassification
from services.ingestor.agent.state import AgentState
from services.ingestor.config import settings
from services.ingestor.constants import NOTIFICATION_SEVERITY_WARNING


logger = logging.getLogger(__name__)

_INCIDENT_COLLECTION = "incidents"


async def classify_severity(state: AgentState) -> dict:
    """The LLM's independent severity read — a trust-calibration signal
    against the rule-based `DriftEvent.severity` that triggered this run."""
    result = await _invoke_structured_model(
        model=get_chat_model(deep=False),
        schema=SeverityClassification,
        model_name=settings.anthropic_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SRE triaging an API contract-drift incident. "
                    "Assess its severity independently, then note whether you "
                    "agree with the rule-based classifier's severity."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Incident: {state['incident_summary']}\n"
                    f"Rule-based severity: {state['rule_based_severity']}\n"
                    f"Event type: {state['event_type']}"
                ),
            },
        ],
    )
    return {
        "llm_severity": result.severity,
        "llm_severity_reasoning": result.reasoning,
        "llm_agrees_with_rule": result.agrees_with_rule_based,
    }


async def _invoke_structured_model(
    *,
    model: Any,
    schema: type[SeverityClassification] | type[DraftAnalysis],
    model_name: str,
    messages: list[dict[str, str]],
) -> SeverityClassification | DraftAnalysis:
    """Invoke a structured model while retaining raw provider metadata."""
    structured_model = model.with_structured_output(schema, include_raw=True)
    response = await structured_model.ainvoke(messages)
    parsing_error = response["parsing_error"]
    if parsing_error is not None:
        raise parsing_error

    record_llm_usage(model=model_name, response=response["raw"])
    result = response["parsed"]
    if result is None:
        raise RuntimeError("LLM structured output was empty.")
    return result


async def retrieve_similar_incidents(state: AgentState) -> dict:
    """RAG via the Phase 2 inference service: find prior similar incidents,
    then index this one so future runs can find it in turn."""
    retrieved: list[dict] = []
    try:
        results = await vs_bridge.search_observation_documents(
            query=state["incident_summary"],
            top_k=3,
            collection=_INCIDENT_COLLECTION,
        )
        retrieved = results.get("results", [])
    except Exception as exc:
        logger.warning("agent_rag_retrieval_failed", extra={"error": str(exc)})

    try:
        await _index_this_incident(state["observation_id"])
    except Exception as exc:
        logger.warning("agent_rag_indexing_failed", extra={"error": str(exc)})

    return {"retrieved_context": retrieved}


async def _index_this_incident(observation_id: int) -> None:
    """Index the triggering Observation so future runs' RAG search can find
    it as a prior similar incident. Own DB session — nodes run out-of-band,
    not on a request-scoped session."""
    from services.ingestor.database import AsyncSessionLocal
    from services.ingestor.repositories.observations import get_observation

    async with AsyncSessionLocal() as session:
        observation = await get_observation(session, observation_id)
        if observation is not None:
            await vs_bridge.index_observation_documents(
                [observation], collection=_INCIDENT_COLLECTION
            )


async def draft_analysis(state: AgentState) -> dict:
    """Root cause / recommended action / confidence, informed by the
    classify_severity read and any retrieved similar incidents."""
    context_text = (
        "\n---\n".join(item.get("text", "") for item in state["retrieved_context"])
        or "No similar prior incidents found."
    )
    result = await _invoke_structured_model(
        model=get_chat_model(deep=True),
        schema=DraftAnalysis,
        model_name=settings.anthropic_model_deep,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior SRE writing an incident analysis for a "
                    "human reviewer. Use the LLM severity read and similar "
                    "prior incidents if relevant. Be concrete and actionable."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Incident: {state['incident_summary']}\n"
                    f"LLM severity: {state['llm_severity']} "
                    f"({state['llm_severity_reasoning']})\n"
                    f"Similar prior incidents:\n{context_text}"
                ),
            },
        ],
    )
    return {
        "root_cause_hypothesis": result.root_cause_hypothesis,
        "recommended_action": result.recommended_action,
        "confidence_score": result.confidence_score,
    }


async def human_review(state: AgentState) -> dict:
    """Pause for human approval — LangGraph `interrupt()`, checkpointed to
    Postgres. Resumes with `{"approve": bool, "reviewer_user_id": int | None}`
    via `POST /api/v1/agent/runs/{run_id}/resume`."""
    if interrupt is None:
        raise RuntimeError("LangGraph is not installed; human review is unavailable.")
    decision = interrupt(
        {
            "agent_run_id": state["agent_run_id"],
            "root_cause_hypothesis": state["root_cause_hypothesis"],
            "recommended_action": state["recommended_action"],
            "confidence_score": state["confidence_score"],
            "llm_severity": state["llm_severity"],
            "message": "Approve or reject this incident analysis.",
        }
    )
    return {
        "review_decision": bool(decision.get("approve", False)),
        "reviewer_user_id": decision.get("reviewer_user_id"),
    }


async def notify(state: AgentState) -> dict:
    """On approval, dispatch through the existing notification channels.
    Rejections are logged, not notified — nothing to alert on-call about."""
    if not state["review_decision"]:
        logger.info(
            "agent_run_rejected",
            extra={"agent_run_id": state["agent_run_id"]},
        )
        return {}

    await notifications.dispatch_notification_event(
        event="incident_analysis_approved",
        message=(
            f"Incident on {state['source']}: {state['root_cause_hypothesis']}\n"
            f"Recommended action: {state['recommended_action']}"
        ),
        severity=NOTIFICATION_SEVERITY_WARNING,
        context={
            "agent_run_id": state["agent_run_id"],
            "observation_id": state["observation_id"],
            "confidence_score": state["confidence_score"],
        },
    )
    return {}
