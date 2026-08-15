"""End-to-end data flow test for the dashboard.

Imports Streamlit-dependent modules with Streamlit mocked to verify
the complete local user path without a real browser.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = MagicMock()

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.app import render_onboarding_guide
from services.dashboard.ui.streamlit.panels.observations import (
    render_observations_panel,
)
from services.dashboard.ui.streamlit.panels.probe_scheduler import (
    render_probe_scheduler,
)
from services.dashboard.ui.streamlit.panels.source_manager import render_source_manager


class _Ctx:
    def __init__(self, mock: MagicMock) -> None:
        self._mock = mock

    def __enter__(self) -> _Ctx:
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _configure_st() -> None:
    st = sys.modules["streamlit"]
    st.sidebar = MagicMock()
    st.set_page_config = MagicMock()
    st.title = MagicMock()
    st.button = MagicMock(return_value=False)
    st.cache_data = MagicMock()
    st.rerun = MagicMock()
    st.warning = MagicMock()
    st.info = MagicMock()
    st.subheader = MagicMock()
    st.expander = MagicMock(side_effect=lambda label, expanded=False: _Ctx(MagicMock()))
    st.markdown = MagicMock()
    st.success = MagicMock()


@pytest.fixture
def manager() -> AuthManager:
    return AuthManager()


@pytest.fixture
def ui(manager: AuthManager) -> MockUIAdapter:
    adapter = MockUIAdapter()
    adapter._session["_auth_manager"] = manager
    return adapter


class TestDataFlow:
    def test_onboarding_shows_login_pending(
        self, ui: MockUIAdapter, manager: AuthManager
    ) -> None:
        features = {"has_sources": False, "has_observations": False}
        st = sys.modules["streamlit"]
        render_onboarding_guide(ui, manager, features)
        markdown_calls = [str(c) for c in st.markdown.call_args_list]
        assert any("Log in" in c and "Enter credentials" in c for c in markdown_calls)

    def test_onboarding_updates_after_login(
        self, ui: MockUIAdapter, manager: AuthManager
    ) -> None:
        manager.login(access_token="t", refresh_token="r", username="u")
        features = {"has_sources": True, "has_observations": True}
        st = sys.modules["streamlit"]
        st.markdown.reset_mock()
        render_onboarding_guide(ui, manager, features)
        markdown_calls = [str(c) for c in st.markdown.call_args_list]
        assert any("Log in" in c and "Done" in c for c in markdown_calls)

    def test_create_source_flow(self, ui: MockUIAdapter, manager: AuthManager) -> None:
        manager.login(access_token="t", refresh_token="r", username="u")

        from libs.contracts.schemas_dashboard import SourceProfileResponse

        def fake_create(**kwargs):
            return SourceProfileResponse(
                id=1,
                name=kwargs["name"],
                base_url=kwargs["base_url"],
                health_check_path=kwargs.get("health_check_path", "/health"),
                probe_interval_seconds=kwargs.get("probe_interval_seconds", 60),
                is_active=kwargs.get("is_active", True),
                incident_failure_threshold=3,
                incident_cooldown_seconds=300,
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )

        dashboard_api.sources.list = lambda **kwargs: []
        dashboard_api.sources.create = fake_create

        ui.text_input_values["Name *"] = "new-source"
        ui.text_input_values["Base URL *"] = "https://new.example.com"
        ui.button_return_values["➕ Create"] = True

        render_source_manager(ui, manager)

        assert any("created" in str(m).lower() for m in ui.successes)

    def test_probe_flow(self, ui: MockUIAdapter, manager: AuthManager) -> None:
        manager.login(access_token="t", refresh_token="r", username="u")

        from libs.contracts.schemas_dashboard import (
            SourceHealthResponse,
            SourceProfileResponse,
        )

        src = SourceProfileResponse(
            id=1,
            name="probe-me",
            base_url="https://probe.example.com",
            health_check_path="/health",
            probe_interval_seconds=60,
            is_active=True,
            incident_failure_threshold=3,
            incident_cooldown_seconds=300,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        health = SourceHealthResponse(
            source_id=1,
            target_url="https://probe.example.com/health",
            reachable=True,
            latency_ms=30,
            status_code=200,
            sla_breach=False,
            checked_at="2024-01-01T00:00:00Z",
            error=None,
        )
        dashboard_api.sources.list = lambda **kwargs: [src]
        dashboard_api.sources.probe = lambda *args, **kwargs: health

        ui.button_return_values["probe_1"] = True

        render_probe_scheduler(ui, manager)

        assert 1 in ui.probe_results
        assert ui.probe_results[1]["reachable"] is True

    def test_observation_detail_flow(
        self, ui: MockUIAdapter, manager: AuthManager
    ) -> None:
        manager.login(access_token="t", refresh_token="r", username="u")

        from libs.contracts.schemas_dashboard import (
            ObservationListResponse,
            ObservationResponse,
            PaginationMeta,
        )
        from services.dashboard.core.api_client import DashboardApiError

        obs = ObservationResponse(
            id=42,
            source="test-src",
            timestamp="2024-01-01T00:00:00Z",
            tags=["x"],
            processed=True,
            created_at="2024-01-01T00:00:00Z",
            updated_at=None,
            raw_data={"key": "value"},
        )

        def failing_get(*args, **kwargs):
            raise DashboardApiError("Unauthorized", status_code=401)

        dashboard_api.observations.list = lambda **kwargs: ObservationListResponse(
            observations=[obs],
            pagination=PaginationMeta(total=1, skip=0, limit=25, has_more=False),
        )
        dashboard_api.observations.get = lambda *args, **kwargs: obs

        ui.set("obs_detail_id", 42)
        ui.button_return_values["obs_detail_load"] = True

        render_observations_panel(ui, manager)

        assert any("42" in str(m) for m in ui.successes)
