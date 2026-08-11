"""Cost-to-value read model."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    CostValueResponse,
    CostValueRow,
    TeamCostSummary,
)
from services.ingestor.models import ContractSnapshot, DriftEvent, SourceProfile
from services.ingestor.repositories.reporting_utils import _cutoff_utc_naive


async def get_cost_value_chart(
    db: AsyncSession,
    *,
    days: int,
    source_ids: list[int] | None,
    limit: int,
) -> CostValueResponse:
    """Build cost-to-value rows per source and team-level summaries."""
    cutoff = _cutoff_utc_naive(days)

    source_stmt = (
        select(SourceProfile)
        .where(SourceProfile.deleted_at.is_(None))
        .order_by(SourceProfile.created_at.desc())
        .limit(limit)
    )
    if source_ids:
        source_stmt = source_stmt.where(SourceProfile.id.in_(source_ids))

    sources = list((await db.execute(source_stmt)).scalars().all())
    if not sources:
        return CostValueResponse(
            rows=[],
            team_summaries=[],
            total_cost_usd=0.0,
            window_days=days,
        )

    queried_source_ids = [s.id for s in sources]

    snapshots = list(
        (
            await db.execute(
                select(ContractSnapshot)
                .where(ContractSnapshot.source_id.in_(queried_source_ids))
                .where(ContractSnapshot.created_at >= cutoff)
            )
        )
        .scalars()
        .all()
    )

    drift_events = list(
        (
            await db.execute(
                select(DriftEvent)
                .where(DriftEvent.source_id.in_(queried_source_ids))
                .where(DriftEvent.created_at >= cutoff)
            )
        )
        .scalars()
        .all()
    )

    breaking_snapshot_ids: set[int] = {
        event.current_snapshot_id
        for event in drift_events
        if event.event_type == "breaking"
    }

    snapshots_by_source: dict[int, list[ContractSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_source[snapshot.source_id].append(snapshot)

    insights_by_source: dict[int, int] = defaultdict(int)
    for event in drift_events:
        insights_by_source[event.source_id] += 1

    rows: list[CostValueRow] = []
    for source in sources:
        source_snapshots = snapshots_by_source.get(source.id, [])
        total_calls = len(source_snapshots)

        breaking_calls = sum(
            1 for s in source_snapshots if s.id in breaking_snapshot_ids
        )
        successful_observations = total_calls - breaking_calls
        insights = insights_by_source.get(source.id, 0)

        unit_cost = 0.0
        total_cost = round(unit_cost * total_calls, 6)

        cost_per_observation: float | None = None
        if successful_observations > 0 and total_cost > 0:
            cost_per_observation = round(total_cost / successful_observations, 6)

        cost_per_insight: float | None = None
        if insights > 0 and total_cost > 0:
            cost_per_insight = round(total_cost / insights, 6)

        rows.append(
            CostValueRow(
                source_id=source.id,
                source_name=source.name,
                owner_team=None,
                cost_per_call_usd=unit_cost,
                total_calls=total_calls,
                total_cost_usd=total_cost,
                successful_observations=successful_observations,
                insights_generated=insights,
                cost_per_observation_usd=cost_per_observation,
                cost_per_insight_usd=cost_per_insight,
            )
        )

    rows.sort(key=lambda r: (-r.total_cost_usd, r.source_id))

    team_totals: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"cost": 0.0, "calls": 0, "insights": 0}
    )
    for row in rows:
        team = row.owner_team or "unassigned"
        team_totals[team]["cost"] = round(
            float(team_totals[team]["cost"]) + row.total_cost_usd, 6
        )
        team_totals[team]["calls"] = int(team_totals[team]["calls"]) + row.total_calls
        team_totals[team]["insights"] = (
            int(team_totals[team]["insights"]) + row.insights_generated
        )

    team_summaries: list[TeamCostSummary] = []
    for team, totals in team_totals.items():
        t_cost = float(totals["cost"])
        t_insights = int(totals["insights"])
        team_summaries.append(
            TeamCostSummary(
                team=team,
                total_cost_usd=t_cost,
                total_calls=int(totals["calls"]),
                total_insights=t_insights,
                cost_per_insight_usd=(
                    round(t_cost / t_insights, 6)
                    if t_insights > 0 and t_cost > 0
                    else None
                ),
            )
        )
    team_summaries.sort(key=lambda ts: (-ts.total_cost_usd, ts.team))

    grand_total = round(sum(r.total_cost_usd for r in rows), 6)

    return CostValueResponse(
        rows=rows,
        team_summaries=team_summaries,
        total_cost_usd=grand_total,
        window_days=days,
    )
