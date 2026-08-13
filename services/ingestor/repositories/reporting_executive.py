"""Executive summary read model."""

import asyncio
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    ActionItem,
    CostSummarySection,
    DriftSummarySection,
    ExecutiveSummaryResponse,
    FreshnessSummarySection,
)
from services.ingestor.repositories.reporting_cost_value import get_cost_value_chart
from services.ingestor.repositories.reporting_freshness import get_freshness_sla
from services.ingestor.repositories.reporting_metrics import list_cohort_reports
from services.ingestor.repositories.reporting_utils import _now_utc_naive


_ACTION_PRIORITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


async def get_executive_summary(
    db: AsyncSession,
    *,
    days: int,
    limit: int,
    sla_threshold_hours: int,
    max_actions: int,
) -> ExecutiveSummaryResponse:
    """Build a weekly executive summary from drift, freshness, and cost signals."""
    cohorts, freshness, cost = await asyncio.gather(
        list_cohort_reports(db, days=days, limit=limit),
        get_freshness_sla(
            db,
            days=days,
            source_ids=None,
            limit=limit,
            sla_threshold_hours=sla_threshold_hours,
        ),
        get_cost_value_chart(db, days=days, source_ids=None, limit=limit),
    )

    sources_with_drift = [c for c in cohorts if c.sample_size > 0]
    total_events = sum(c.sample_size for c in sources_with_drift)
    avg_compat = (
        sum(c.avg_compatibility_score for c in sources_with_drift)
        / len(sources_with_drift)
        if sources_with_drift
        else 100.0
    )
    breaking_source_count = sum(1 for c in cohorts if c.breaking_rate_pct > 0.0)
    drift_summary = DriftSummarySection(
        total_sources_with_drift=len(sources_with_drift),
        total_events=total_events,
        avg_compatibility_score=round(avg_compat, 2),
        breaking_source_count=breaking_source_count,
    )

    open_incidents = sum(1 for inc in freshness.incidents if inc.is_open)
    freshness_summary = FreshnessSummarySection(
        total_sources=len(freshness.sources),
        breached=freshness.total_breached,
        warning=sum(1 for s in freshness.sources if s.status == "warning"),
        ok=freshness.total_ok,
        no_data=freshness.total_no_data,
        open_incidents=open_incidents,
    )

    rows_with_spend = [r for r in cost.rows if r.total_cost_usd > 0]
    avg_cost_per_insight: float | None = None
    if rows_with_spend:
        total_insights_with_spend = sum(r.insights_generated for r in rows_with_spend)
        total_spend = sum(r.total_cost_usd for r in rows_with_spend)
        if total_insights_with_spend > 0:
            avg_cost_per_insight = round(total_spend / total_insights_with_spend, 6)
    highest_cost_source = cost.rows[0].source_name if cost.rows else None
    cost_summary = CostSummarySection(
        total_cost_usd=cost.total_cost_usd,
        total_sources=len(cost.rows),
        avg_cost_per_insight_usd=avg_cost_per_insight,
        highest_cost_source_name=highest_cost_source,
    )

    actions: list[ActionItem] = []

    for cohort in cohorts:
        if cohort.breaking_rate_pct >= 30.0:
            actions.append(
                ActionItem(
                    priority="high",
                    category="drift",
                    title=f"High breaking drift rate: {cohort.cohort_name}",
                    description=(
                        f"{cohort.breaking_rate_pct:.1f}% of schema events were breaking "
                        f"(avg compatibility score: {cohort.avg_compatibility_score:.1f}). "
                        "Review schema evolution policy and add compatibility gates."
                    ),
                    source_id=cohort.source_id,
                    source_name=None,
                )
            )
        elif cohort.breaking_rate_pct > 0.0 and cohort.avg_compatibility_score < 70.0:
            actions.append(
                ActionItem(
                    priority="medium",
                    category="drift",
                    title=f"Schema drift detected: {cohort.cohort_name}",
                    description=(
                        f"Compatibility score is {cohort.avg_compatibility_score:.1f} with "
                        f"{cohort.breaking_rate_pct:.1f}% breaking rate. "
                        "Investigate upstream schema changes."
                    ),
                    source_id=cohort.source_id,
                    source_name=None,
                )
            )

    for src in freshness.sources:
        if src.status == "breached":
            hours_stale = (src.age_seconds or 0) // 3600
            actions.append(
                ActionItem(
                    priority="critical",
                    category="freshness",
                    title=f"SLA breach: {src.source_name}",
                    description=(
                        f"No fresh data received for {hours_stale}h "
                        f"(threshold: {sla_threshold_hours}h). "
                        "Check ingestion pipeline and upstream API availability."
                    ),
                    source_id=src.source_id,
                    source_name=src.source_name,
                )
            )
        elif src.status == "warning":
            hours_stale = (src.age_seconds or 0) // 3600
            actions.append(
                ActionItem(
                    priority="medium",
                    category="freshness",
                    title=f"Freshness warning: {src.source_name}",
                    description=(
                        f"Last snapshot is {hours_stale}h old, "
                        f"approaching the {sla_threshold_hours}h SLA threshold. "
                        "Monitor ingestion frequency."
                    ),
                    source_id=src.source_id,
                    source_name=src.source_name,
                )
            )

    cost_rows_with_insight = [
        r for r in cost.rows if r.cost_per_insight_usd is not None
    ]
    if cost_rows_with_insight:
        max_cpi = max(
            cast(float, r.cost_per_insight_usd) for r in cost_rows_with_insight
        )
        for row in cost_rows_with_insight:
            if (
                row.cost_per_insight_usd is not None
                and row.cost_per_insight_usd >= max_cpi * 0.8
            ):
                actions.append(
                    ActionItem(
                        priority="low",
                        category="cost",
                        title=f"High cost-per-insight: {row.source_name}",
                        description=(
                            f"${row.cost_per_insight_usd:.4f} per insight with "
                            f"${row.total_cost_usd:.4f} total spend in window. "
                            "Consider optimising polling frequency or schema validation logic."
                        ),
                        source_id=row.source_id,
                        source_name=row.source_name,
                    )
                )

    actions.sort(
        key=lambda a: (_ACTION_PRIORITY_ORDER.get(a.priority, 99), a.source_id or 0)
    )
    actions = actions[:max_actions]

    return ExecutiveSummaryResponse(
        generated_at=_now_utc_naive(),
        window_days=days,
        drift=drift_summary,
        freshness=freshness_summary,
        cost=cost_summary,
        action_items=actions,
        total_actions=len(actions),
    )
