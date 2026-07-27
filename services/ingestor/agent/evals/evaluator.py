"""Pure deterministic checks for recorded incident-triage outputs."""

from __future__ import annotations

import json
from pathlib import Path

from services.ingestor.agent.evals.schemas import (
    AgentEvalCase,
    AgentEvalCaseResult,
    AgentEvalDataset,
    AgentEvalReport,
)


_MIN_REASONING_LENGTH = 20
_MIN_HYPOTHESIS_LENGTH = 20
_MIN_ACTION_LENGTH = 20


def load_cases(path: Path) -> AgentEvalDataset:
    """Load and validate a versioned golden incident dataset.

    Args:
        path: JSON file containing reviewed structured agent outputs.

    Returns:
        Validated dataset ready for deterministic evaluation.
    """
    return AgentEvalDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


def evaluate_case(case: AgentEvalCase) -> AgentEvalCaseResult:
    """Evaluate one recorded output against its explicit acceptance anchors.

    Args:
        case: Golden incident, expected quality anchors, and recorded outputs.

    Returns:
        Per-case checks, failure descriptions, and an equal-weighted score.
    """
    actual = case.actual
    expected = case.expected
    checks = {
        "severity_matches": actual.severity.severity == expected.severity,
        "severity_reasoning_present": (
            len(actual.severity.reasoning.strip()) >= _MIN_REASONING_LENGTH
        ),
        "confidence_meets_minimum": (
            actual.analysis.confidence_score >= expected.minimum_confidence
        ),
        "hypothesis_is_substantive": (
            len(actual.analysis.root_cause_hypothesis.strip()) >= _MIN_HYPOTHESIS_LENGTH
        ),
        "hypothesis_terms_present": _contains_all_terms(
            actual.analysis.root_cause_hypothesis,
            expected.required_hypothesis_terms,
        ),
        "action_is_substantive": (
            len(actual.analysis.recommended_action.strip()) >= _MIN_ACTION_LENGTH
        ),
        "action_terms_present": _contains_all_terms(
            actual.analysis.recommended_action,
            expected.required_action_terms,
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return AgentEvalCaseResult(
        case_id=case.id,
        passed=not failures,
        score=sum(checks.values()) / len(checks),
        checks=checks,
        failures=failures,
    )


def evaluate_cases(dataset: AgentEvalDataset) -> AgentEvalReport:
    """Evaluate every case in a golden dataset without calling an LLM.

    Args:
        dataset: Validated golden cases with recorded structured outputs.

    Returns:
        Aggregate report suitable for JSON output and CI artifacts.
    """
    results = [evaluate_case(case) for case in dataset.cases]
    passed_cases = sum(result.passed for result in results)
    return AgentEvalReport(
        dataset_version=dataset.version,
        total_cases=len(results),
        passed_cases=passed_cases,
        pass_rate=passed_cases / len(results),
        passed=passed_cases == len(results),
        cases=results,
    )


def _contains_all_terms(text: str, terms: list[str]) -> bool:
    """Return whether every reviewed acceptance term occurs in the text."""
    normalized = text.casefold()
    return all(term.casefold() in normalized for term in terms)
