"""Tests for the live stream panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.live_stream import render_live_stream


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


class TestLiveStream:
    def test_renders_header(self, ui: MockUIAdapter, auth: AuthManager) -> None:
        ui.ws_connected = False
        render_live_stream(ui, auth)
        assert "Live Stream" in ui.headers

    def test_disconnect_button_toggles_ws(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        ui.ws_connected = True
        ui.button_return_values["ws_toggle"] = True
        render_live_stream(ui, auth)
        assert ui.ws_connected is False

    def test_connect_button_toggles_ws(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        ui.ws_connected = False
        ui.button_return_values["ws_toggle"] = True
        render_live_stream(ui, auth)
        assert ui.ws_connected is True

    def test_clear_button_clears_messages(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        ui.ws_messages = [{"type": "ping"}]
        ui.button_return_values["ws_clear"] = True
        render_live_stream(ui, auth)
        assert ui.ws_messages == []

    def test_shows_no_messages_placeholder(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        ui.ws_connected = False
        render_live_stream(ui, auth)
        assert any("No messages yet" in str(m) for m in ui.infos)
