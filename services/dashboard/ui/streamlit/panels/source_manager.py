"""Panel: Source Management — CRUD for source profiles.

Split into:
  - ``use_*`` — data-fetching hooks (no UI imports)
  - ``render_*`` — pure display from pre-fetched data
"""

from __future__ import annotations

import httpx

from services.dashboard.core.api_client import (
    DashboardApiError,
    api,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def use_sources(token: str = "") -> dict:
    try:
        sources = api.sources.list(token=token)
        return {"sources": sources, "error": None}
    except (httpx.HTTPStatusError, DashboardApiError) as e:
        return {"sources": [], "error": e}


def use_source_by_id(token: str = "", source_id: int = 0) -> dict:
    try:
        sources = api.sources.list(token=token)
        for s in sources:
            if s.id == source_id:
                return {"source": s}
    except httpx.HTTPStatusError, DashboardApiError:
        pass
    return {"source": None}


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_source_manager(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the source management panel with list + create/edit/delete."""
    if not auth.state.logged_in:
        return

    ui.header("Source Manager")
    ui.caption("Register, update, and remove API sources for health probing.")

    ui.setdefault("src_edit_id", None)

    data = use_sources(token=auth.access_token)

    _render_source_form(ui, auth, data)
    _render_source_list(ui, auth, data)


def _render_source_form(ui: UIAdapter, auth: AuthManager, data: dict) -> None:
    """Collapsible form to add or edit a source."""
    edit_id = ui.get("src_edit_id")
    is_editing = edit_id is not None

    label = "✏️ Edit Source" if is_editing else "➕ Add Source"
    with ui.expander(label, expanded=is_editing):
        if is_editing:
            src_data = use_source_by_id(token=auth.access_token, source_id=edit_id)
            existing = src_data["source"]
            if existing is None:
                ui.show_error("Source not found — resetting form.")
                ui.set("src_edit_id", None)
                ui.rerun()
                return
            name_default = existing.name
            url_default = existing.base_url
            health_default = existing.health_check_path
            interval_default = existing.probe_interval_seconds
            active_default = existing.is_active
        else:
            name_default = ""
            url_default = ""
            health_default = "/health"
            interval_default = 60
            active_default = True

        with ui.form("source_form"):
            name = ui.text_input(
                "Name *", value=name_default, placeholder="e.g. my-api"
            )
            base_url = ui.text_input(
                "Base URL *",
                value=url_default,
                placeholder="https://api.example.com",
            )
            c1, c2 = ui.columns(2)
            health_path = c1.text_input("Health check path", value=health_default)
            interval = c2.number_input(
                "Probe interval (s)",
                min_value=1,
                value=interval_default,
            )
            is_active = ui.checkbox("Active", value=active_default)

            col_submit, col_cancel = ui.columns(2)
            submitted = col_submit.form_submit_button(
                "💾 Save" if is_editing else "➕ Create"
            )
            if col_cancel.form_submit_button("Cancel"):
                ui.set("src_edit_id", None)
                ui.rerun()

            if submitted:
                if not name.strip() or not base_url.strip():
                    ui.show_error("Name and Base URL are required.")
                    return
                try:
                    if is_editing:
                        update_kw: dict = {
                            "source_id": edit_id,
                            "token": auth.access_token,
                        }
                        if base_url.strip() != existing.base_url:
                            update_kw["base_url"] = base_url.strip()
                        if health_path.strip() != existing.health_check_path:
                            update_kw["health_check_path"] = health_path.strip()
                        if interval != existing.probe_interval_seconds:
                            update_kw["probe_interval_seconds"] = interval
                        if is_active != existing.is_active:
                            update_kw["is_active"] = is_active
                        api.sources.update(**update_kw)
                        ui.show_success(f"Source '{name}' updated.")
                    else:
                        api.sources.create(
                            token=auth.access_token,
                            name=name.strip(),
                            base_url=base_url.strip(),
                            health_check_path=health_path.strip(),
                            probe_interval_seconds=interval,
                            is_active=is_active,
                        )
                        ui.show_success(f"Source '{name}' created.")
                    ui.set("src_edit_id", None)
                    ui.clear_cache()
                    ui.rerun()
                except DashboardApiError as e:
                    if e.status_code == 403:
                        ui.show_error(
                            "Admin role required for this action. "
                            "Log in as an admin user from the sidebar."
                        )
                    else:
                        ui.show_error(str(e))


def _render_source_list(ui: UIAdapter, auth: AuthManager, data: dict) -> None:
    """Display all sources with edit/delete actions."""
    err = data.get("error")
    if err:
        if hasattr(err, "status_code") and err.status_code == 401:
            ui.show_warning("Log in from the sidebar to manage sources.")
        else:
            ui.show_error(f"Could not fetch sources: {err}")
        return

    sources = data["sources"]
    if not sources:
        ui.show_info("No sources registered yet — use the form above to add one.")
        return

    for src in sources:
        with ui.container():
            c1, c2, c3, c4, c5, c6 = ui.columns([2, 3, 1, 1, 1, 1])
            c1.markdown(f"**{src.name}**")
            c2.caption(f"`{src.base_url}{src.health_check_path}`")
            c3.caption(f"⏱ {src.probe_interval_seconds}s")
            c4.caption("🟢" if src.is_active else "🔴")

            if c5.button("✏️", key=f"src_edit_{src.id}", help="Edit source"):
                ui.set("src_edit_id", src.id)
                ui.rerun()

            if c6.button("🗑", key=f"src_del_{src.id}", help="Delete source"):
                try:
                    api.sources.delete(source_id=src.id, token=auth.access_token)
                    ui.show_success(f"Source '{src.name}' deleted.")
                    ui.clear_cache()
                    ui.rerun()
                except DashboardApiError as e:
                    if e.status_code == 403:
                        ui.show_error(
                            "Admin role required to delete sources. "
                            "Log in as an admin user from the sidebar."
                        )
                    else:
                        ui.show_error(str(e))

        ui.divider()
