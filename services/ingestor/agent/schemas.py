"""Structured LLM output schemas for the incident-triage agent.

Domain-specific — replaces the generic sentiment-oriented
`ObservationClassification` (services/ingestor/api_schemas/observations.py)
for incidents raised from drift events.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SeverityClassification(BaseModel):
    """classify_severity node output — the LLM's independent read, compared
    against the rule-based `DriftEvent.severity` for a trust-calibration
    signal (does the AI agree with the deterministic classifier)."""

    severity: Literal["low", "medium", "high", "critical"] = Field(
        description="The LLM's own severity assessment of the incident."
    )
    reasoning: str = Field(description="Brief justification for the severity.")
    agrees_with_rule_based: bool = Field(
        description="Whether this matches the rule-based classifier's severity."
    )


class DraftAnalysis(BaseModel):
    """draft_analysis node output — becomes AgentRun.root_cause_hypothesis /
    recommended_action / confidence_score once the run completes."""

    root_cause_hypothesis: str = Field(
        description="Most likely root cause of the drift/incident."
    )
    recommended_action: str = Field(
        description="Concrete next step for an on-call engineer."
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence in this analysis, 0.0-1.0."
    )
