"""Tests for the observations panel."""

from __future__ import annotations

import pytest

from services.dashboard.core.api_client import api as dashboard_api
from services.dashboard.core.auth import AuthManager
from services.dashboard.tests.ui.test_mock_adapter import MockUIAdapter
from services.dashboard.ui.streamlit.panels.observations import (
    render_observations_panel,
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


class TestObservationsPanel:
    def test_renders_header_and_caption(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.observations.list = lambda **kwargs: type(
            "R", (), {"observations": [], "pagination": type("P", (), {"total": 0})()}
        )()
        render_observations_panel(ui, auth)
        assert "Observations" in ui.subheaders

    def test_shows_info_when_no_observations(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        dashboard_api.observations.list = lambda **kwargs: type(
            "R", (), {"observations": [], "pagination": type("P", (), {"total": 0})()}
        )()
        render_observations_panel(ui, auth)
        assert any("No observations" in str(m) for m in ui.infos)

    def test_renders_observation_rows(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        from libs.contracts.schemas_dashboard import (
            ObservationListResponse,
            ObservationResponse,
            PaginationMeta,
        )

        obs = ObservationResponse(
            id=1,
            source="test-src",
            timestamp="2024-01-01T00:00:00Z",
            tags=["a"],
            processed=True,
            created_at="2024-01-01T00:00:00Z",
            updated_at=None,
            raw_data={},
        )
        dashboard_api.observations.list = lambda **kwargs: ObservationListResponse(
            observations=[obs],
            pagination=PaginationMeta(total=1, skip=0, limit=25, has_more=False),
        )
        render_observations_panel(ui, auth)
        assert len(ui.writes) > 0

    def test_detail_load_shows_401_warning(
        self, ui: MockUIAdapter, auth: AuthManager
    ) -> None:
        from libs.contracts.schemas_dashboard import (
            ObservationListResponse,
            ObservationResponse,
            PaginationMeta,
        )
        from services.dashboard.core.api_client import DashboardApiError

        obs = ObservationResponse(
            id=1,
            source="test-src",
            timestamp="2024-01-01T00:00:00Z",
            tags=["a"],
            processed=True,
            created_at="2024-01-01T00:00:00Z",
            updated_at=None,
            raw_data={},
        )

        def failing_get(*args, **kwargs):
            raise DashboardApiError("Unauthorized", status_code=401)

        dashboard_api.observations.list = lambda **kwargs: ObservationListResponse(
            observations=[obs],
            pagination=PaginationMeta(total=1, skip=0, limit=25, has_more=False),
        )
        dashboard_api.observations.get = failing_get

        ui.set("obs_detail_id", 1)
        ui.button_return_values["obs_detail_load"] = True

        render_observations_panel(ui, auth)

        assert any("not authorized" in str(m).lower() for m in ui.warnings)
