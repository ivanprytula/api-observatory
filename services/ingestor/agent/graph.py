"""LangGraph incident-triage graph — five linear nodes with a human-in-the-loop
pause before notification.

    classify_severity -> retrieve_similar_incidents -> draft_analysis
        -> human_review -> notify

`human_review` calls `interrupt()`; the checkpointer (Postgres-backed, see
`services.ingestor.agent.runner`) persists state at that point so the run can
be resumed later via `POST /api/v1/agent/runs/{run_id}/resume` — potentially
in a different process than the one that started it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.ingestor.agent import nodes
from services.ingestor.agent.state import AgentState


if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


def build_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(AgentState)
    builder.add_node("classify_severity", nodes.classify_severity)
    builder.add_node("retrieve_similar_incidents", nodes.retrieve_similar_incidents)
    builder.add_node("draft_analysis", nodes.draft_analysis)
    builder.add_node("human_review", nodes.human_review)
    builder.add_node("notify", nodes.notify)

    builder.add_edge(START, "classify_severity")
    builder.add_edge("classify_severity", "retrieve_similar_incidents")
    builder.add_edge("retrieve_similar_incidents", "draft_analysis")
    builder.add_edge("draft_analysis", "human_review")
    builder.add_edge("human_review", "notify")
    builder.add_edge("notify", END)

    return builder.compile(checkpointer=checkpointer)
