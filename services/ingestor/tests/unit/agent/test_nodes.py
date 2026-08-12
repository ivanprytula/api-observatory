from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.agent import nodes
from services.ingestor.agent.schemas import DraftAnalysis, SeverityClassification


pytestmark = [pytest.mark.unit, pytest.mark.capability_ai]


def _base_state(**overrides) -> dict:
    state = {
        "agent_run_id": 1,
        "observation_id": 1,
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
    state.update(overrides)
    return state


class TestClassifySeverity:
    async def test_returns_llm_severity_fields(self) -> None:
        fake_model = MagicMock()
        fake_model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value={
                "raw": SimpleNamespace(
                    usage_metadata={"input_tokens": 100, "output_tokens": 25}
                ),
                "parsed": SeverityClassification(
                    severity="critical",
                    reasoning="Removed required field, breaking change.",
                    agrees_with_rule_based=True,
                ),
                "parsing_error": None,
            }
        )
        with (
            patch(
                "services.ingestor.agent.nodes.get_chat_model", return_value=fake_model
            ) as get_model,
            patch("services.ingestor.agent.nodes.record_llm_usage") as record_usage,
        ):
            result = await nodes.classify_severity(_base_state())

        get_model.assert_called_once_with(deep=False)
        record_usage.assert_called_once()
        assert result == {
            "llm_severity": "critical",
            "llm_severity_reasoning": "Removed required field, breaking change.",
            "llm_agrees_with_rule": True,
        }


class TestRetrieveSimilarIncidents:
    async def test_returns_search_results_and_indexes_self(self) -> None:
        with (
            patch(
                "services.ingestor.agent.nodes.vs_bridge.search_observation_documents",
                new=AsyncMock(
                    return_value={"results": [{"id": 1, "text": "prior incident"}]}
                ),
            ),
            patch(
                "services.ingestor.agent.nodes._index_this_incident", new=AsyncMock()
            ) as index_mock,
        ):
            result = await nodes.retrieve_similar_incidents(_base_state())

        assert result == {"retrieved_context": [{"id": 1, "text": "prior incident"}]}
        index_mock.assert_awaited_once_with(1)

    async def test_search_failure_returns_empty_context(self) -> None:
        with (
            patch(
                "services.ingestor.agent.nodes.vs_bridge.search_observation_documents",
                new=AsyncMock(side_effect=RuntimeError("inference unreachable")),
            ),
            patch(
                "services.ingestor.agent.nodes._index_this_incident", new=AsyncMock()
            ),
        ):
            result = await nodes.retrieve_similar_incidents(_base_state())

        assert result == {"retrieved_context": []}


class TestDraftAnalysis:
    async def test_returns_analysis_fields(self) -> None:
        fake_model = MagicMock()
        fake_model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value={
                "raw": SimpleNamespace(usage_metadata=None),
                "parsed": DraftAnalysis(
                    root_cause_hypothesis="Upstream schema change without coordination.",
                    recommended_action="Roll back and add a contract test.",
                    confidence_score=0.8,
                ),
                "parsing_error": None,
            }
        )
        state = _base_state(llm_severity="critical", retrieved_context=[])
        with (
            patch(
                "services.ingestor.agent.nodes.get_chat_model", return_value=fake_model
            ) as get_model,
            patch("services.ingestor.agent.nodes.record_llm_usage") as record_usage,
        ):
            result = await nodes.draft_analysis(state)

        get_model.assert_called_once_with(deep=True)
        record_usage.assert_called_once()
        assert result == {
            "root_cause_hypothesis": "Upstream schema change without coordination.",
            "recommended_action": "Roll back and add a contract test.",
            "confidence_score": 0.8,
        }


class TestNotify:
    async def test_approved_dispatches_notification(self) -> None:
        state = _base_state(
            review_decision=True,
            root_cause_hypothesis="root cause",
            recommended_action="do the thing",
            confidence_score=0.9,
        )
        with patch(
            "services.ingestor.agent.nodes.notifications.dispatch_notification_event",
            new=AsyncMock(),
        ) as dispatch:
            result = await nodes.notify(state)

        dispatch.assert_awaited_once()
        assert result == {}

    async def test_rejected_skips_notification(self) -> None:
        state = _base_state(review_decision=False)
        with patch(
            "services.ingestor.agent.nodes.notifications.dispatch_notification_event",
            new=AsyncMock(),
        ) as dispatch:
            result = await nodes.notify(state)

        dispatch.assert_not_awaited()
        assert result == {}
