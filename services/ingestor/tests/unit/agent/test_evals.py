from __future__ import annotations

from pathlib import Path

import pytest

from services.ingestor.agent.evals.evaluator import (
    evaluate_case,
    evaluate_cases,
    load_cases,
)
from services.ingestor.agent.evals.schemas import (
    AgentEvalActual,
    AgentEvalCase,
    AgentEvalDataset,
    AgentEvalExpected,
)
from services.ingestor.agent.schemas import DraftAnalysis, SeverityClassification


pytestmark = pytest.mark.unit


def _passing_case() -> AgentEvalCase:
    """Build a representative reviewed case without a provider call."""
    return AgentEvalCase(
        id="test-incident",
        incident_summary="A breaking contract release disrupted clients.",
        expected=AgentEvalExpected(
            severity="high",
            minimum_confidence=0.7,
            required_hypothesis_terms=["contract", "breaking"],
            required_action_terms=["roll back", "compatibility"],
        ),
        actual=AgentEvalActual(
            severity=SeverityClassification(
                severity="high",
                reasoning=(
                    "The release is a breaking contract change that disrupts existing clients."
                ),
                agrees_with_rule_based=True,
            ),
            analysis=DraftAnalysis(
                root_cause_hypothesis=(
                    "A contract-breaking release changed a response shape without a "
                    "compatible migration."
                ),
                recommended_action=(
                    "Roll back the release, restore compatibility, and validate the "
                    "contract before redeploying."
                ),
                confidence_score=0.8,
            ),
        ),
    )


def test_evaluate_case_passes_reviewed_output() -> None:
    """All deterministic checks pass for a reviewed golden output."""
    result = evaluate_case(_passing_case())

    assert result.passed is True
    assert result.score == 1.0
    assert result.failures == []


def test_evaluate_case_reports_failed_acceptance_anchors() -> None:
    """Regression output identifies the failed quality dimensions."""
    case = _passing_case().model_copy(
        update={
            "actual": AgentEvalActual(
                severity=SeverityClassification(
                    severity="low",
                    reasoning="Too short",
                    agrees_with_rule_based=False,
                ),
                analysis=DraftAnalysis(
                    root_cause_hypothesis="Unknown",
                    recommended_action="Retry",
                    confidence_score=0.2,
                ),
            )
        }
    )

    result = evaluate_case(case)

    assert result.passed is False
    assert result.checks["severity_matches"] is False
    assert result.checks["confidence_meets_minimum"] is False
    assert result.checks["hypothesis_terms_present"] is False
    assert result.checks["action_terms_present"] is False


def test_evaluate_cases_aggregates_golden_dataset() -> None:
    """Aggregate output reports a complete passing baseline."""
    report = evaluate_cases(AgentEvalDataset(version=1, cases=[_passing_case()]))

    assert report.passed is True
    assert report.total_cases == 1
    assert report.passed_cases == 1
    assert report.pass_rate == 1.0


def test_load_cases_validates_versioned_fixture() -> None:
    """The committed fixture is parseable without an LLM provider."""
    fixture_path = (
        Path(__file__).parents[3] / "agent/evals/fixtures/incident-triage-v1.json"
    )

    dataset = load_cases(fixture_path)

    assert dataset.version == 1
    assert len(dataset.cases) == 2
