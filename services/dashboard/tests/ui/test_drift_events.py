"""Tests for the drift events panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.drift_events import render_drift_events


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


class TestDriftEvents:
    def test_renders_header(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        dashboard_api.sources.list = lambda **kwargs: []
        render_drift_events(ui, auth)
        assert "Drift Events" in ui.headers

    def test_shows_info_when_no_events(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.sources.list = lambda **kwargs: []
        render_drift_events(ui, auth)
        assert any("No drift events" in str(m) for m in ui.infos)

    def test_renders_event_rows(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        from libs.contracts.schemas_dashboard import (
            DriftEventResponse,
            SourceProfileResponse,
        )

        src = SourceProfileResponse(
            id=1,
            name="src-a",
            base_url="https://a.example.com",
            health_check_path="/health",
            probe_interval_seconds=60,
            is_active=True,
            tenant_id=None,
            latency_threshold_ms=None,
            incident_failure_threshold=3,
            incident_cooldown_seconds=300,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        evt = DriftEventResponse(
            id=1,
            source_id=1,
            previous_snapshot_id=0,
            current_snapshot_id=1,
            event_type="field_removed",
            severity="high",
            added_fields=[],
            removed_fields=["x"],
            type_changed_fields={},
            compatibility_score=0.8,
            summary="field x removed",
            created_at="2024-01-01T00:00:00Z",
        )
        dashboard_api.sources.list = lambda **kwargs: [src]
        dashboard_api.drift.list = lambda **kwargs: [evt]
        render_drift_events(ui, auth)
        assert len(ui.writes) == 1
        assert any("src-a" in str(row.get("Source", "")) for row in ui.writes[0])
