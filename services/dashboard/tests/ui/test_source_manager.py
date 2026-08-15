"""Tests for the source manager panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.source_manager import (
    render_source_manager,
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


class TestSourceManager:
    def test_returns_early_when_not_logged_in(self, ui: MockUIAdapter) -> None:
        manager = AuthManager()
        ui._session["_auth_manager"] = manager
        render_source_manager(ui, manager)
        assert ui.headers == []

    def test_empty_state_renders_header(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.sources.list = lambda **kwargs: []
        render_source_manager(ui, auth)
        assert "Source Manager" in ui.headers
        assert any("Register, update, and remove" in str(c) for c in ui.captions)

    def test_create_form_submits_successfully(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_source(
                id=1,
                name=kwargs["name"],
                base_url=kwargs["base_url"],
            )

        dashboard_api.sources.list = lambda **kwargs: []
        dashboard_api.sources.create = fake_create

        ui.text_input_values["Name *"] = "test-api"
        ui.text_input_values["Base URL *"] = "https://api.example.com"
        ui.button_return_values["➕ Create"] = True

        render_source_manager(ui, auth)

        assert captured["name"] == "test-api"
        assert captured["base_url"] == "https://api.example.com"
        assert any("created" in str(m).lower() for m in ui.successes)

    def test_delete_source_calls_api(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        captured: dict = {}

        def fake_delete(**kwargs):
            captured.update(kwargs)

        dashboard_api.sources.list = lambda **kwargs: [
            _make_source(id=1, name="to-delete")
        ]
        dashboard_api.sources.delete = fake_delete

        ui.button_return_values["src_del_1"] = True

        render_source_manager(ui, auth)

        assert captured.get("source_id") == 1
        assert any("deleted" in str(m).lower() for m in ui.successes)
