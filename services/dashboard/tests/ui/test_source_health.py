"""Tests for the source health panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.source_health import (
    render_freshness_heatmap,
    render_ingestion_throughput,
    render_source_health_table,
)


@pytest.fixture
def auth() -> AuthManager:
    manager = AuthManager()
    manager.login(
        access_token="fake-token", refresh_token="fake-refresh", username="testuser"
    )
    return manager


@pytest.fixture
def ui(auth: AuthManager) -> MockUIAdapter:
    adapter = MockUIAdapter()
    adapter._session["_auth_manager"] = auth
    return adapter


class TestSourceHealthTable:
    def test_shows_info_when_no_scorecards(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.scorecards.list = lambda **kwargs: type("R", (), {"items": []})()
        render_source_health_table(ui, auth)
        assert any("No scorecards" in str(m) for m in ui.infos)

    def test_renders_dataframe_rows(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        from libs.contracts.schemas_dashboard import (
            ProviderScorecard,
            ScorecardListResponse,
        )

        sc = ProviderScorecard(
            source_id=1,
            source_name="test-api",
            window_days=7,
            sample_count=100,
            error_count=0,
            uptime_pct=99.5,
            avg_latency_ms=100.0,
            p50_latency_ms=90.0,
            p95_latency_ms=120.0,
            slo_target_pct=99.0,
            error_budget_burn_rate=0.1,
            generated_at="2024-01-01T00:00:00Z",
        )
        dashboard_api.scorecards.list = lambda **kwargs: ScorecardListResponse(
            items=[sc], total=1
        )
        render_source_health_table(ui, auth)
        assert len(ui.writes) == 1
        assert len(ui.writes[0]) == 1


class TestFreshnessHeatmap:
    def test_shows_info_when_no_sources(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.sources.list = lambda **kwargs: []
        dashboard_api.health.scheduler_jobs = lambda **kwargs: {"jobs": {}}
        render_freshness_heatmap(ui, auth)
        assert any("No sources" in str(m) for m in ui.infos)


class TestIngestionThroughput:
    def test_renders_metrics(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        dashboard_api.metrics.raw = lambda **kwargs: ""
        render_ingestion_throughput(ui)
        assert len(ui.metrics) == 3
