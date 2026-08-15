"""Tests for the incidents panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.incidents import render_incidents


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


def _make_incident(**kwargs):
    from libs.contracts.schemas_dashboard import DependencyIncidentResponse

    defaults = {
        "id": 1,
        "source_id": 1,
        "tenant_id": None,
        "trigger_type": "drift",
        "status": "open",
        "severity": "high",
        "summary": "Test incident",
        "guidance": "Fix it",
        "trigger_details": {},
        "occurrence_count": 3,
        "first_seen_at": "2024-01-01T00:00:00Z",
        "last_seen_at": "2024-01-01T00:00:00Z",
        "acknowledged_at": None,
        "acknowledged_by": None,
        "resolved_at": None,
        "resolved_by": None,
        "last_notification_at": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": None,
    }
    defaults.update(kwargs)
    return DependencyIncidentResponse(**defaults)


class TestIncidentsPanel:
    def test_renders_header(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        dashboard_api.incidents.list = lambda **kwargs: type("R", (), {"items": []})()
        render_incidents(ui, auth)
        assert "Dependency Incidents" in ui.headers

    def test_shows_info_when_no_incidents(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.incidents.list = lambda **kwargs: type("R", (), {"items": []})()
        render_incidents(ui, auth)
        assert any("No dependency incidents" in str(m) for m in ui.infos)

    def test_acknowledge_button_calls_api(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        incident = _make_incident(status="open")
        dashboard_api.incidents.list = lambda **kwargs: type(
            "R", (), {"items": [incident]}
        )()
        dashboard_api.incidents.acknowledge = lambda **kwargs: _make_incident(
            status="acknowledged", acknowledged_by="testuser"
        )

        ui.button_return_values["inc_ack_1"] = True

        render_incidents(ui, auth)

        assert any("acknowledged" in str(m).lower() for m in ui.successes)
