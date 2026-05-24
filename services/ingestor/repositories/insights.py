"""Insight Engine repository logic derived from source and drift datasets."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.insights import (
    AnomalyInsight,
    RecommendationInsight,
    TrendInsight,
)
from services.ingestor.constants import (
    INSIGHT_CONFIDENCE_CRITICAL,
    INSIGHT_CONFIDENCE_HIGH,
    INSIGHT_CONFIDENCE_LOW,
    INSIGHT_CONFIDENCE_MEDIUM,
    INSIGHT_PRIORITY_P1,
    INSIGHT_PRIORITY_P2,
    INSIGHT_PRIORITY_P3,
)
from services.ingestor.models import ContractSnapshot, DriftEvent, SourceProfile


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _confidence_from_severity(severity: str) -> float:
    mapping = {
        "critical": INSIGHT_CONFIDENCE_CRITICAL,
        "high": INSIGHT_CONFIDENCE_HIGH,
        "medium": INSIGHT_CONFIDENCE_MEDIUM,
        "low": INSIGHT_CONFIDENCE_LOW,
    }
    return mapping.get(severity, INSIGHT_CONFIDENCE_LOW)


def _priority_from_severity(severity: str) -> str:
    if severity in {"critical", "high"}:
        return INSIGHT_PRIORITY_P1
    if severity == "medium":
        return INSIGHT_PRIORITY_P2
    return INSIGHT_PRIORITY_P3


async def get_anomaly_insights(
    db: AsyncSession,
    *,
    limit: int,
    source_id: int | None = None,
) -> list[AnomalyInsight]:
    """Build anomaly insights from recent drift events."""
    stmt = select(DriftEvent).order_by(DriftEvent.created_at.desc()).limit(limit)
    if source_id is not None:
        stmt = stmt.where(DriftEvent.source_id == source_id)

    events = list((await db.execute(stmt)).scalars().all())
    generated_at = _now_utc_naive()

    return [
        AnomalyInsight(
            insight_id=f"anomaly-drift-{event.id}",
            insight_type="anomaly",
            title=f"{event.event_type.replace('_', ' ').title()} schema drift detected",
            summary=event.summary
            or "Schema contract changed between consecutive snapshots.",
            source_id=event.source_id,
            severity=event.severity,
            confidence=_confidence_from_severity(event.severity),
            created_at=generated_at,
            metadata={
                "event_id": event.id,
                "compatibility_score": event.compatibility_score,
                "added_fields": event.added_fields,
                "removed_fields": event.removed_fields,
                "type_changed_fields": event.type_changed_fields,
            },
        )
        for event in events
    ]


async def get_trend_insights(
    db: AsyncSession,
    *,
    limit: int,
) -> list[TrendInsight]:
    """Build trend insights from source-level compatibility deltas."""
    sources = list(
        (
            await db.execute(
                select(SourceProfile)
                .where(SourceProfile.deleted_at.is_(None))
                .order_by(SourceProfile.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    generated_at = _now_utc_naive()
    insights: list[TrendInsight] = []

    for source in sources:
        snapshots = list(
            (
                await db.execute(
                    select(ContractSnapshot)
                    .where(ContractSnapshot.source_id == source.id)
                    .order_by(ContractSnapshot.created_at.desc())
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
        if len(snapshots) < 2:
            continue

        latest = snapshots[0]
        previous = snapshots[1]
        delta = latest.compatibility_score - previous.compatibility_score
        if delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"
        else:
            direction = "flat"

        denominator = (
            previous.compatibility_score if previous.compatibility_score else 1.0
        )
        change_pct = round((delta / denominator) * 100.0, 2)

        insights.append(
            TrendInsight(
                insight_id=f"trend-compat-{source.id}",
                insight_type="trend",
                title=f"Compatibility trend for {source.name}",
                summary=(
                    "Compatibility score moved "
                    f"{direction} from {previous.compatibility_score:.2f} to "
                    f"{latest.compatibility_score:.2f}."
                ),
                source_id=source.id,
                confidence=INSIGHT_CONFIDENCE_MEDIUM,
                created_at=generated_at,
                metric="compatibility_score",
                direction=direction,
                change_pct=change_pct,
                metadata={
                    "latest_snapshot_id": latest.id,
                    "previous_snapshot_id": previous.id,
                    "latest_score": latest.compatibility_score,
                    "previous_score": previous.compatibility_score,
                },
            )
        )

    return insights


async def get_recommendation_insights(
    db: AsyncSession,
    *,
    limit: int,
    source_id: int | None = None,
) -> list[RecommendationInsight]:
    """Build actionable recommendations from severe anomaly insights."""
    anomalies = await get_anomaly_insights(db, limit=limit, source_id=source_id)
    generated_at = _now_utc_naive()

    recommendations: list[RecommendationInsight] = []
    for anomaly in anomalies:
        severity = anomaly.severity
        event_type = str(anomaly.metadata.get("event_type", ""))
        removed = anomaly.metadata.get("removed_fields", [])
        type_changes = anomaly.metadata.get("type_changed_fields", {})

        if severity in {"critical", "high"} and (removed or type_changes):
            action = (
                "Deploy compatibility fallback parser and pin source contract version "
                "until producer change is validated."
            )
        elif event_type == "non_breaking":
            action = (
                "Regenerate client schema bindings and add contract snapshot checks "
                "to CI for additive fields."
            )
        else:
            action = (
                "Add tighter monitoring and update source owner playbook with "
                "contract-change response steps."
            )

        recommendations.append(
            RecommendationInsight(
                insight_id=f"recommendation-{anomaly.insight_id}",
                insight_type="recommendation",
                title=f"Action for source {anomaly.source_id}",
                summary=(
                    "Recommended remediation generated from recent drift signal "
                    f"({severity})."
                ),
                source_id=anomaly.source_id,
                confidence=anomaly.confidence,
                created_at=generated_at,
                priority=_priority_from_severity(severity),
                action=action,
                metadata={
                    "derived_from": anomaly.insight_id,
                    "severity": severity,
                },
            )
        )

    return recommendations
