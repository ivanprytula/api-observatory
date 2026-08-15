"""Tests for the probe scheduler panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.probe_scheduler import (
    render_probe_scheduler,
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


def _make_source(**kwargs):
    from libs.contracts.schemas_dashboard import SourceProfileResponse

    defaults = {
        "id": 1,
        "name": "test-api",
        "base_url": "https://api.example.com",
        "health_check_path": "/health",
        "probe_interval_seconds": 60,
        "is_active": True,
        "tenant_id": None,
        "latency_threshold_ms": None,
        "incident_failure_threshold": 3,
        "incident_cooldown_seconds": 300,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return SourceProfileResponse(**defaults)


class TestProbeScheduler:
    def test_returns_early_when_not_logged_in(self, ui: MockUIAdapter) -> None:
        manager = AuthManager()
        ui._session["_auth_manager"] = manager
        render_probe_scheduler(ui, manager)
        assert "Probe Scheduler" in ui.headers
        assert any("Log in" in str(m) for m in ui.warnings)

    def test_probe_stores_results(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        from libs.contracts.schemas_dashboard import SourceHealthResponse

        src = _make_source(id=1, name="test-api")
        health = SourceHealthResponse(
            source_id=1,
            target_url="https://api.example.com/health",
            reachable=True,
            latency_ms=42,
            status_code=200,
            sla_breach=False,
            checked_at="2024-01-01T00:00:00Z",
            error=None,
        )

        dashboard_api.sources.list = lambda **kwargs: [src]
        dashboard_api.sources.probe = lambda *args, **kwargs: health

        ui.button_return_values["probe_all"] = True

        render_probe_scheduler(ui, auth)

        assert 1 in ui.probe_results
        assert ui.probe_results[1]["reachable"] is True
