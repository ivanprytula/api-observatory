"""Integration-style test for the full graph pause -> resume cycle.

Uses LangGraph's in-memory checkpointer (not Postgres — this is testing
graph *wiring*, not the Postgres checkpointer itself, which was verified
live against a real instance). LLM/RAG/notification calls are mocked so
this runs with no network dependency and no API cost.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.agent.schemas import DraftAnalysis, SeverityClassification


pytest.importorskip("langgraph", reason="langgraph is not in active MVP scope")

pytestmark = pytest.mark.unit


def _initial_state() -> dict:
    return {
        "agent_run_id": 42,
        "observation_id": 42,
        "source": "payments-api",
        "incident_summary": "source=payments-api, event_type=breaking, severity=critical",
        "rule_based_severity": "critical",
        "event_type": "breaking",
        "raw_data": {"severity": "critical", "event_type": "breaking"},
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


def _fake_chat_model(*, deep: bool):
    model = MagicMock()
    if deep:
        model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_structured_response(
                DraftAnalysis(
                    root_cause_hypothesis="Upstream schema change.",
                    recommended_action="Roll back the deploy.",
                    confidence_score=0.75,
                )
            )
        )
    else:
        model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=_structured_response(
                SeverityClassification(
                    severity="critical",
                    reasoning="Field removed and type changed.",
                    agrees_with_rule_based=True,
                )
            )
        )
    return model


def _structured_response(
    parsed: SeverityClassification | DraftAnalysis,
) -> dict[str, object]:
    """Mirror LangChain's include_raw=True structured-output response."""
    return {
        "raw": SimpleNamespace(usage_metadata=None),
        "parsed": parsed,
        "parsing_error": None,
    }


class TestGraphPauseResume:
    async def test_pauses_at_human_review_then_resumes_on_approval(self) -> None:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command

        from services.ingestor.agent.graph import build_graph

        with (
            patch(
                "services.ingestor.agent.nodes.get_chat_model",
                side_effect=lambda deep=False: _fake_chat_model(deep=deep),
            ),
            patch(
                "services.ingestor.agent.nodes.vs_bridge.search_observation_documents",
                new=AsyncMock(return_value={"results": []}),
            ),
            patch(
                "services.ingestor.agent.nodes._index_this_incident", new=AsyncMock()
            ),
            patch(
                "services.ingestor.agent.nodes.notifications.dispatch_notification_event",
                new=AsyncMock(),
            ) as dispatch,
        ):
            graph = build_graph(MemorySaver())
            config = {"configurable": {"thread_id": "42"}}

            paused = await graph.ainvoke(_initial_state(), config=config)
            assert paused.get("__interrupt__")
            assert paused["llm_severity"] == "critical"
            assert paused["root_cause_hypothesis"] == "Upstream schema change."
            assert paused["review_decision"] is None
            dispatch.assert_not_awaited()  # hasn't reached notify yet

            final = await graph.ainvoke(
                Command(resume={"approve": True, "reviewer_user_id": 7}),
                config=config,
            )
            assert not final.get("__interrupt__")
            assert final["review_decision"] is True
            assert final["reviewer_user_id"] == 7
            dispatch.assert_awaited_once()

    async def test_rejection_skips_notification(self) -> None:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command

        from services.ingestor.agent.graph import build_graph

        with (
            patch(
                "services.ingestor.agent.nodes.get_chat_model",
                side_effect=lambda deep=False: _fake_chat_model(deep=deep),
            ),
            patch(
                "services.ingestor.agent.nodes.vs_bridge.search_observation_documents",
                new=AsyncMock(return_value={"results": []}),
            ),
            patch(
                "services.ingestor.agent.nodes._index_this_incident", new=AsyncMock()
            ),
            patch(
                "services.ingestor.agent.nodes.notifications.dispatch_notification_event",
                new=AsyncMock(),
            ) as dispatch,
        ):
            graph = build_graph(MemorySaver())
            config = {"configurable": {"thread_id": "43"}}

            await graph.ainvoke(_initial_state(), config=config)
            final = await graph.ainvoke(
                Command(resume={"approve": False, "reviewer_user_id": 7}),
                config=config,
            )

        assert final["review_decision"] is False
        dispatch.assert_not_awaited()
