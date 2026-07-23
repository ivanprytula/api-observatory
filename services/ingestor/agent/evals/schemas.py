"""Versioned input and output contracts for offline agent evaluation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from services.ingestor.agent.schemas import DraftAnalysis, SeverityClassification


class AgentEvalExpected(BaseModel):
    """Deterministic expectations for one recorded incident output.

    Required terms are intentionally small, human-reviewed acceptance anchors;
    they are not a substitute for a future semantic or LLM-as-judge evaluation.
    """

    severity: Literal["low", "medium", "high", "critical"]
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    required_hypothesis_terms: list[str] = Field(min_length=1)
    required_action_terms: list[str] = Field(min_length=1)


class AgentEvalActual(BaseModel):
    """Recorded structured outputs produced by an agent run."""

    severity: SeverityClassification
    analysis: DraftAnalysis


class AgentEvalCase(BaseModel):
    """One golden incident and its reviewed structured output."""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    incident_summary: str = Field(min_length=1)
    expected: AgentEvalExpected
    actual: AgentEvalActual


class AgentEvalDataset(BaseModel):
    """Versioned collection of golden incident cases."""

    version: int = Field(ge=1)
    cases: list[AgentEvalCase] = Field(min_length=1)


class AgentEvalCaseResult(BaseModel):
    """Deterministic evaluation outcome for a single golden case."""

    case_id: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    checks: dict[str, bool]
    failures: list[str]


class AgentEvalReport(BaseModel):
    """Serializable aggregate result for local use and CI artifacts."""

    dataset_version: int
    total_cases: int
    passed_cases: int
    pass_rate: float = Field(ge=0.0, le=1.0)
    passed: bool
    cases: list[AgentEvalCaseResult]
