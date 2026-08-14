"""Panel: Observations list with pagination and detail view (read-only MVP).

Split into:
  - ``use_*`` — data-fetching hooks (no UI imports)
  - ``render_*`` — pure display from pre-fetched data
"""

from __future__ import annotations

from services.dashboard.core.api_client import (
    API_REQUEST_ERRORS,
    api,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


_OBS_SESSION_DEFAULTS: dict[str, object] = {
    "obs_page": 1,
    "obs_source_filter": "",
    "obs_detail_id": None,
}


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def use_observations_page(
    token: str = "", page: int = 1, page_size: int = 25, source_filter: str = ""
) -> dict:
    try:
        resp = api.observations.list(
            token=token,
            page=page,
            page_size=page_size,
            source_filter=source_filter or None,
        )
        return {
            "observations": resp.observations,
            "pagination": resp.pagination,
        }
    except API_REQUEST_ERRORS:
        return {"observations": [], "pagination": None}


def use_observation_detail(token: str = "", observation_id: int | None = None) -> dict:
    if observation_id is None:
        return {"observation": None}
    try:
        obs = api.observations.get(observation_id, token=token)
        return {"observation": obs}
    except API_REQUEST_ERRORS as e:
        return {"observation": None, "error": e}
    except Exception as exc:
        return {"observation": None, "error": exc}


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_observations_panel(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the observations list with pagination, filtering, and detail view."""
    ui.subheader("Observations")

    for key, default in _OBS_SESSION_DEFAULTS.items():
        ui.setdefault(key, default)

    source_filter = ui.text_input(
        "Filter by source (optional)",
        value=ui.get("obs_source_filter", ""),
        placeholder="e.g., sensor.prod",
    )
    ui.set("obs_source_filter", source_filter)

    col_size, col_prev, col_page, col_next = ui.columns([2, 1, 1, 1])
    with col_size:
        page_size = ui.selectbox(
            "Page size",
            options=[10, 25, 50, 100],
            index=[10, 25, 50, 100].index(ui.get("obs_page_size", 25)),
            key="obs_page_size",
        )

    page = ui.get("obs_page", 1)
    with col_prev:
        if ui.button("← Prev", key="obs_prev") and page > 1:
            ui.set("obs_page", page - 1)
            ui.rerun()
    with col_page:
        ui.write(f"Page {page}")
    with col_next:
        if ui.button("Next →", key="obs_next"):
            ui.set("obs_page", page + 1)
            ui.rerun()

    data = use_observations_page(
        token=auth.access_token,
        page=page,
        page_size=page_size,
        source_filter=source_filter,
    )
    observations = data["observations"]
    pagination = data["pagination"]

    if not observations:
        ui.show_info("No observations found matching your filters.")
        return

    for obs in observations:
        tags_str = ", ".join(obs.tags) if obs.tags else "—"
        processed_badge = "Yes" if obs.processed else "No"
        with ui.container():
            c1, c2, c3, c4, c5, c6 = ui.columns([1, 2, 2, 1, 1, 1])
            c1.write(f"**{obs.id}**")
            c2.caption(f"`{obs.source}`")
            c3.caption(obs.timestamp.isoformat()[:19] if obs.timestamp else "—")
            c4.caption(tags_str)
            c5.caption(processed_badge)
            if c6.button("View", key=f"obs_view_{obs.id}"):
                ui.set("obs_detail_id", obs.id)
                ui.rerun()
        ui.divider()

    start = (page - 1) * page_size + 1
    end = start + len(observations) - 1
    ui.caption(
        f"Showing {start}–{end} of {pagination.total} observations"
        + (f" | Page {page}" if page_size < pagination.total else "")
    )

    ui.divider()
    ui.subheader("Detail View")
    detail_id_input = ui.number_input(
        "Enter observation ID to view details",
        min_value=1,
        value=ui.get("obs_detail_id") or 1,
        step=1,
    )

    if ui.button("Load Details", key="obs_detail_load"):
        ui.set("obs_detail_id", detail_id_input)
        ui.rerun()

    if ui.get("obs_detail_id"):
        detail = use_observation_detail(
            token=auth.access_token,
            observation_id=ui.get("obs_detail_id"),
        )
        obs = detail.get("observation")
        err = detail.get("error")

        if err:
            if hasattr(err, "status_code") and err.status_code == 401:
                ui.show_warning("You are not authorized to view this observation.")
            elif hasattr(err, "status_code") and err.status_code == 404:
                ui.show_warning(f"Observation #{ui.get('obs_detail_id')} not found.")
            else:
                ui.show_error(f"Could not fetch observation details: {err}")
        elif obs:
            ui.show_success(f"Observation #{obs.id} from {obs.source}")
            detail_cols = ui.columns(2)
            with detail_cols[0]:
                ui.write("**Metadata**")
                ui.write(
                    f"- Source: {obs.source}\n"
                    f"- Timestamp: {obs.timestamp}\n"
                    f"- Processed: {'Yes' if obs.processed else 'No'}\n"
                    f"- Created: {obs.created_at}\n"
                    f"- Updated: {obs.updated_at or 'Never'}"
                )
            with detail_cols[1]:
                ui.write("**Tags**")
                if obs.tags:
                    for tag in obs.tags:
                        ui.write(f"- {tag}")
                else:
                    ui.write("(none)")

            with ui.expander("Raw payload", expanded=False):
                ui.json(obs.raw_data)
