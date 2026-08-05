"""Unit tests for reporting repository read models.

Pure helpers and mock-DB coverage for BI/reporting read models —
no real database required.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.api_schemas.reporting import (
    CohortReport,
    CostValueResponse,
    ExportJobRequest,
    FreshnessSLAResponse,
)
from services.ingestor.constants import REPORTING_DEFAULT_EXPORT_FORMAT
from services.ingestor.models import ContractSnapshot, DriftEvent, SourceProfile
from services.ingestor.repositories.reporting import (
    _cutoff_utc_naive,
    _freshness_status,
    _now_utc_naive,
    create_export_job,
    get_cost_value_chart,
    get_drift_heatmap,
    get_executive_summary,
    get_freshness_sla,
    list_cohort_reports,
    list_dashboard_presets,
    list_metric_series,
)


def _make_result(scalars_all=None, all_rows=None):
    result = MagicMock()
    if scalars_all is not None:
        result.scalars.return_value.all.return_value = scalars_all
    if all_rows is not None:
        result.all.return_value = all_rows
    return result


def _src(id=1, name="src", tenant_id=42, latency_threshold_ms=None, created_at=None):
    s = MagicMock(spec=SourceProfile)
    s.id = id
    s.name = name
    s.tenant_id = tenant_id
    s.latency_threshold_ms = latency_threshold_ms
    s.created_at = created_at
    return s


def _drift_event(
    source_id=1, severity="breaking", compatibility_score=70.0, event_type="breaking"
):
    e = MagicMock(spec=DriftEvent)
    e.source_id = source_id
    e.severity = severity
    e.event_type = event_type
    e.compatibility_score = compatibility_score
    return e


def _snapshot(id=10, source_id=1, created_at=None):
    s = MagicMock(spec=ContractSnapshot)
    s.id = id
    s.source_id = source_id
    s.created_at = created_at
    return s


# ---------------------------------------------------------------------------
# _freshness_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFreshnessStatus:
    def test_no_data_when_age_none(self) -> None:
        assert _freshness_status(None, 3600) == "no_data"

    def test_breached_when_age_exceeds_threshold(self) -> None:
        assert _freshness_status(7200, 3600) == "breached"

    def test_warning_when_age_above_75pct(self) -> None:
        assert _freshness_status(3000, 3600) == "warning"

    def test_ok_when_age_within_threshold(self) -> None:
        assert _freshness_status(100, 3600) == "ok"

    def test_boundary_exactly_at_threshold_is_warning(self) -> None:
        assert _freshness_status(3600, 3600) == "warning"

    def test_boundary_at_75pct_is_ok(self) -> None:
        assert _freshness_status(2700, 3600) == "ok"


# ---------------------------------------------------------------------------
# list_dashboard_presets
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDashboardPresets:
    def test_returns_two_presets(self) -> None:
        presets = list_dashboard_presets()
        assert len(presets) == 2

    def test_presets_have_ids_and_widgets(self) -> None:
        presets = list_dashboard_presets()
        ids = {p.preset_id for p in presets}
        assert ids == {"ops-scorecard", "exec-weekly-summary"}
        for p in presets:
            assert len(p.widgets) > 0


# ---------------------------------------------------------------------------
# create_export_job
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateExportJob:
    def test_uses_default_format_when_empty(self) -> None:
        payload = ExportJobRequest(preset_id="ops-scorecard", export_format="")
        job = create_export_job(payload)
        assert job.export_format == REPORTING_DEFAULT_EXPORT_FORMAT
        assert job.status == "completed"
        assert job.preset_id == "ops-scorecard"

    def test_uses_custom_format(self) -> None:
        payload = ExportJobRequest(preset_id="ops-scorecard", export_format="csv")
        job = create_export_job(payload)
        assert job.export_format == "csv"

    def test_export_id_is_deterministic_from_timestamp(self) -> None:
        payload = ExportJobRequest(preset_id="p1", export_format="json")
        job = create_export_job(payload)
        assert job.export_id.startswith("export-")


# ---------------------------------------------------------------------------
# _now_utc_naive / _cutoff_utc_naive
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTimeHelpers:
    def test_now_is_naive_utc(self) -> None:
        now = _now_utc_naive()
        assert now.tzinfo is None

    def test_cutoff_subtracts_days(self) -> None:
        cutoff = _cutoff_utc_naive(7)
        now = _now_utc_naive()
        delta = (now - cutoff).total_seconds()
        assert 6 * 86400 <= delta <= 7 * 86400 + 1


# ---------------------------------------------------------------------------
# list_metric_series
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListMetricSeries:
    async def test_empty_sources_returns_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        result = await list_metric_series(mock_db, days=7, source_id=None, limit=10)
        assert result == []

    async def test_sources_with_events_build_series(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="api", created_at=datetime(2025, 1, 1))
        event = _drift_event(source_id=1, compatibility_score=95.5)
        event.created_at = datetime(2025, 1, 1)

        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[source])
            return _make_result(scalars_all=[event])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        series = await list_metric_series(mock_db, days=7, source_id=None, limit=10)

        assert len(series) == 1
        assert series[0].source_id == 1
        assert series[0].metric == "compatibility_score"
        assert len(series[0].points) == 1
        assert series[0].points[0].value == 95.5


# ---------------------------------------------------------------------------
# list_cohort_reports
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListCohortReports:
    async def test_empty_sources_returns_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        result = await list_cohort_reports(mock_db, days=7, limit=10)
        assert result == []

    async def test_cohort_with_no_events_defaults_to_full_score(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="src", created_at=datetime(2025, 1, 1))
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            return _make_result(scalars_all=[source] if calls["n"] == 1 else [])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        rows = await list_cohort_reports(mock_db, days=7, limit=10)
        assert len(rows) == 1
        assert rows[0].avg_compatibility_score == 100.0
        assert rows[0].breaking_rate_pct == 0.0
        assert rows[0].sample_size == 0

    async def test_cohort_with_mixed_events(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="src", created_at=datetime(2025, 1, 1))
        source.latency_threshold_ms = 500.0
        e1 = _drift_event(source_id=1, event_type="breaking", compatibility_score=70.0)
        e2 = _drift_event(
            source_id=1, event_type="non_breaking", compatibility_score=90.0
        )
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[source])
            return _make_result(scalars_all=[e1, e2])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        rows = await list_cohort_reports(mock_db, days=7, limit=10)
        assert len(rows) == 1
        assert rows[0].sample_size == 2
        assert rows[0].breaking_rate_pct == 50.0
        assert rows[0].avg_sla_gap_ms == round(500.0 * (1.0 - 80.0 / 100.0), 2)

    async def test_cohorts_sorted_by_compatibility_desc(self) -> None:
        mock_db = MagicMock()
        s1 = _src(id=1, name="a", created_at=datetime(2025, 1, 1))
        s2 = _src(id=2, name="b", created_at=datetime(2025, 1, 1))
        e1 = _drift_event(
            source_id=1, event_type="non_breaking", compatibility_score=95.0
        )
        e2 = _drift_event(
            source_id=2, event_type="non_breaking", compatibility_score=80.0
        )
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[s1, s2])
            return _make_result(scalars_all=[e1, e2])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        rows = await list_cohort_reports(mock_db, days=7, limit=10)
        assert rows[0].source_id == 1
        assert rows[1].source_id == 2


# ---------------------------------------------------------------------------
# get_drift_heatmap
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDriftHeatmap:
    async def test_no_sources_returns_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        result = await get_drift_heatmap(mock_db, days=7, source_ids=None, limit=10)
        assert result.sources == []
        assert result.cells == []
        assert result.total_events == 0

    async def test_events_with_no_counts_returns_empty(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="api", created_at=datetime(2025, 1, 1))
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[source])
            return _make_result(scalars_all=[])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        result = await get_drift_heatmap(mock_db, days=7, source_ids=None, limit=10)
        assert result.total_events == 0
        assert result.cells == []

    async def test_heatmap_normalizes_against_max(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="api", created_at=datetime(2025, 1, 1))
        e1 = _drift_event(source_id=1, severity="critical")
        e2 = _drift_event(source_id=1, severity="critical")
        e3 = _drift_event(source_id=1, severity="high")
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[source])
            return _make_result(scalars_all=[e1, e2, e3])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        result = await get_drift_heatmap(mock_db, days=7, source_ids=None, limit=10)
        assert result.total_events == 3
        assert result.severities == ["critical", "high"]
        crit = next(c for c in result.cells if c.severity == "critical")
        assert crit.count == 2
        assert crit.heat_value == 1.0
        high = next(c for c in result.cells if c.severity == "high")
        assert high.count == 1
        assert high.heat_value == 0.5


# ---------------------------------------------------------------------------
# get_cost_value_chart
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCostValueChart:
    async def test_no_sources_returns_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        result = await get_cost_value_chart(mock_db, days=7, source_ids=None, limit=10)
        assert result.rows == []
        assert result.team_summaries == []
        assert result.total_cost_usd == 0.0

    async def test_sources_with_snapshots_and_events(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="api", created_at=datetime(2025, 1, 1))
        snap1 = _snapshot(id=10, source_id=1)
        snap2 = _snapshot(id=20, source_id=1)
        event = _drift_event(source_id=1, event_type="breaking")
        event.current_snapshot_id = 10
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[source])
            if calls["n"] == 2:
                return _make_result(scalars_all=[snap1, snap2])
            return _make_result(scalars_all=[event])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        result = await get_cost_value_chart(mock_db, days=7, source_ids=None, limit=10)
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.total_calls == 2
        assert row.successful_observations == 1
        assert row.insights_generated == 1
        assert row.cost_per_observation_usd is None
        assert row.cost_per_insight_usd is None


# ---------------------------------------------------------------------------
# get_freshness_sla
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFreshnessSla:
    async def test_no_sources_returns_empty(self) -> None:
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_result(scalars_all=[]))
        result = await get_freshness_sla(
            mock_db, days=7, source_ids=None, limit=10, sla_threshold_hours=24
        )
        assert result.sources == []
        assert result.total_breached == 0

    async def test_source_with_no_snapshots_is_no_data(self) -> None:
        mock_db = MagicMock()
        source = _src(id=1, name="api", created_at=datetime(2025, 1, 1))
        calls = {"n": 0}

        async def execute_side_effect(stmt):
            calls["n"] += 1
            if calls["n"] == 1:
                return _make_result(scalars_all=[source])
            return _make_result(all_rows=[])

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        result = await get_freshness_sla(
            mock_db, days=7, source_ids=None, limit=10, sla_threshold_hours=24
        )
        assert result.sources[0].status == "no_data"
        assert result.sources[0].total_snapshots == 0
        assert result.total_no_data == 1


# ---------------------------------------------------------------------------
# get_executive_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecutiveSummary:
    async def test_synthesises_from_sub_reports(self) -> None:
        cohort = CohortReport(
            cohort_id="c1",
            cohort_name="src reliability cohort",
            source_id=1,
            sample_size=2,
            avg_compatibility_score=85.0,
            breaking_rate_pct=50.0,
            avg_sla_gap_ms=75.0,
            rank=1,
        )
        freshness = FreshnessSLAResponse(
            sources=[],
            incidents=[],
            total_breached=0,
            total_ok=0,
            total_no_data=1,
            window_days=7,
            sla_threshold_hours=24,
        )
        cost = CostValueResponse(
            rows=[], team_summaries=[], total_cost_usd=0.0, window_days=7
        )

        with (
            patch(
                "services.ingestor.repositories.reporting.list_cohort_reports",
                new=AsyncMock(return_value=[cohort]),
            ),
            patch(
                "services.ingestor.repositories.reporting.get_freshness_sla",
                new=AsyncMock(return_value=freshness),
            ),
            patch(
                "services.ingestor.repositories.reporting.get_cost_value_chart",
                new=AsyncMock(return_value=cost),
            ),
        ):
            result = await get_executive_summary(
                MagicMock(), days=7, limit=10, sla_threshold_hours=24, max_actions=5
            )

        assert result.window_days == 7
        assert result.drift.total_sources_with_drift == 1
        assert result.drift.total_events == 2
        assert result.freshness.no_data == 1
        assert len(result.action_items) >= 1
