"""Tests for the auth sidebar component.

`auth_sidebar.py` imports Streamlit directly, so we patch it at collection time.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = MagicMock()

import pytest

from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.components.auth_sidebar import render_auth_sidebar


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


class _Ctx:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def __enter__(self) -> _Ctx:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class TestAuthSidebar:
    def test_logged_out_shows_login_form(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        auth.logout()
        st = sys.modules["streamlit"]
        st.sidebar = MagicMock()
        st.header = MagicMock()
        st.tabs = MagicMock(return_value=[MagicMock(), MagicMock()])
        st.form = MagicMock(return_value=_Ctx([]))
        st.text_input = MagicMock(return_value="user")
        st.form_submit_button = MagicMock(return_value=False)
        st.button = MagicMock(return_value=False)
        st.success = MagicMock()
        render_auth_sidebar(ui, auth)
        st.header.assert_called()

    def test_logged_in_shows_username(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        st = sys.modules["streamlit"]
        st.sidebar = MagicMock()
        st.header = MagicMock()
        st.success = MagicMock()
        st.button = MagicMock(return_value=False)
        render_auth_sidebar(ui, auth)
        st.success.assert_called_with("Logged in as **testuser**")

    def test_login_form_calls_manager(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        auth.logout()
        st = sys.modules["streamlit"]
        st.sidebar = MagicMock()
        st.header = MagicMock()
        st.tabs = MagicMock(return_value=[MagicMock(), MagicMock()])
        form_ctx = _Ctx([])
        st.form = MagicMock(return_value=form_ctx)
        st.text_input = MagicMock(return_value="user")
        st.form_submit_button = MagicMock(return_value=True)
        st.button = MagicMock(return_value=False)
        st.success = MagicMock()

        with patch.object(auth, "do_login", return_value=None) as mock_login:
            render_auth_sidebar(ui, auth)
            mock_login.assert_called_with("user", "user")
