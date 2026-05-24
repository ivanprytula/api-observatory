"""Pydantic schemas for Insight Engine feeds."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InsightBase(BaseModel):
    """Base insight payload shared by all insight feeds."""

    insight_id: str = Field(..., description="Stable identifier for this insight item.")
    insight_type: str = Field(
        ..., description="Insight category: anomaly, trend, recommendation."
    )
    title: str = Field(..., description="Short human-readable title.")
    summary: str = Field(..., description="Concise explanation of the observed signal.")
    source_id: int | None = Field(
        None, description="Associated source profile ID when applicable."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score in [0, 1]."
    )
    created_at: datetime = Field(..., description="Insight generation timestamp (UTC).")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Machine-readable details."
    )


class AnomalyInsight(InsightBase):
    """Anomaly signal derived from drift or reliability events."""

    severity: str = Field(..., description="Severity bucket for alerting and triage.")


class TrendInsight(InsightBase):
    """Trend insight describing directional metric movement."""

    metric: str = Field(..., description="Metric name used for the trend computation.")
    direction: str = Field(..., description="Trend direction: up, down, or flat.")
    change_pct: float = Field(
        ...,
        description="Relative percent change across the compared window.",
    )


class RecommendationInsight(InsightBase):
    """Actionable recommendation generated from anomalies or trends."""

    priority: str = Field(..., description="Execution priority (P1/P2/P3).")
    action: str = Field(..., description="Recommended remediation action.")


class AnomalyFeedResponse(BaseModel):
    """Response payload for anomaly feed endpoint."""

    items: list[AnomalyInsight]
    total: int


class TrendFeedResponse(BaseModel):
    """Response payload for trend feed endpoint."""

    items: list[TrendInsight]
    total: int


class RecommendationFeedResponse(BaseModel):
    """Response payload for recommendations endpoint."""

    items: list[RecommendationInsight]
    total: int
