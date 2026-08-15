"""Tests for the service health panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.service_health import render_service_health


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


class TestServiceHealth:
    def test_renders_header(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        dashboard_api.health.probes = lambda: {
            "liveness (/health)": {"status_code": 200, "body": {"status": "ok"}},
            "readiness (/readyz)": {"status_code": 200, "body": {"status": "ok"}},
        }
        render_service_health(ui, auth)
        assert "Service Health" in ui.headers

    def test_renders_200_metric(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        dashboard_api.health.probes = lambda: {
            "liveness (/health)": {"status_code": 200, "body": {"status": "ok"}},
        }
        render_service_health(ui, auth)
        assert len(ui.metrics) >= 1
        label, value, _ = ui.metrics[0]
        assert "200" in value

    def test_renders_degraded_metric(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.health.probes = lambda: {
            "readiness (/readyz)": {"status_code": 503, "body": {}},
        }
        render_service_health(ui, auth)
        degraded = [m for m in ui.metrics if "503" in m[1]]
        assert len(degraded) >= 1
