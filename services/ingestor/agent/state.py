"""LangGraph state for the incident-triage agent.

One run per `AgentRun` row (Phase 1). The graph carries enough of the
triggering `Observation`/`DriftEvent` payload to reason about the incident
without re-querying the DB from every node — nodes are pure functions of
state in, state-update out.
"""

from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict):
    agent_run_id: int
    observation_id: int
    source: str
    incident_summary: str
    rule_based_severity: str
    event_type: str
    raw_data: dict

    # classify_severity output
    llm_severity: str | None
    llm_severity_reasoning: str | None
    llm_agrees_with_rule: bool | None

    # retrieve_similar_incidents output
    retrieved_context: list[dict]

    # draft_analysis output
    root_cause_hypothesis: str | None
    recommended_action: str | None
    confidence_score: float | None

    # human_review output (set on resume)
    review_decision: bool | None
    reviewer_user_id: int | None
