"""Panel: Observations list with pagination and detail view (read-only MVP)."""

from __future__ import annotations

import streamlit as st
from services.dashboard.core.api_client import (
    DashboardApiError,
    fetch_observation,
    fetch_observations,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


def render_observations_panel(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the observations list with pagination, filtering, and detail view."""
    ui.subheader("Observations")

    # Pagination and filter state
    if "obs_page" not in st.session_state:
        st.session_state.obs_page = 1
    if "obs_source_filter" not in st.session_state:
        st.session_state.obs_source_filter = ""
    if "obs_detail_id" not in st.session_state:
        st.session_state.obs_detail_id = None

    # Filter widget
    source_filter = ui.text_input(
        "Filter by source (optional)",
        value=st.session_state.obs_source_filter,
        placeholder="e.g., sensor.prod",
    )
    st.session_state.obs_source_filter = source_filter

    # Pagination controls
    col_prev, col_page, col_next = ui.columns(3)
    with col_prev:
        if ui.button("← Previous", key="obs_prev") and st.session_state.obs_page > 1:
            st.session_state.obs_page -= 1
            st.rerun()
    with col_page:
        ui.write(f"Page {st.session_state.obs_page}")
    with col_next:
        if ui.button("Next →", key="obs_next"):
            st.session_state.obs_page += 1
            st.rerun()

    # Fetch and display observations
    try:
        list_resp = fetch_observations(
            auth=auth,
            page=st.session_state.obs_page,
            page_size=25,
            source_filter=source_filter if source_filter else None,
        )
        observations = list_resp.observations
        pagination = list_resp.pagination

        if not observations:
            ui.show_info("No observations found matching your filters.")
            return

        # Display list as table
        rows = []
        for obs in observations:
            tags_str = ", ".join(obs.tags) if obs.tags else "—"
            processed_badge = "✓ Yes" if obs.processed else "✗ No"
            rows.append(
                {
                    "ID": obs.id,
                    "Source": obs.source,
                    "Timestamp": obs.timestamp.isoformat() if obs.timestamp else "—",
                    "Tags": tags_str,
                    "Processed": processed_badge,
                }
            )

        ui.render_dataframe(rows, width="stretch")

        # Pagination info
        ui.caption(
            f"Total: {pagination.total} | "
            f"Showing {len(observations)} on page {st.session_state.obs_page} | "
            f"Has more: {'Yes' if pagination.has_more else 'No'}"
        )

        # Detail view toggle (optional: expand single observation JSON)
        st.divider()
        ui.subheader("Detail View")
        detail_id_input = ui.number_input(
            "Enter observation ID to view details",
            min_value=1,
            value=st.session_state.obs_detail_id or 1,
            step=1,
        )

        if ui.button("Load Details", key="obs_detail_load"):
            st.session_state.obs_detail_id = detail_id_input
            st.rerun()

        if st.session_state.obs_detail_id:
            try:
                detail_obs = fetch_observation(
                    observation_id=st.session_state.obs_detail_id, auth=auth
                )
                ui.show_success(
                    f"Observation #{detail_obs.id} from {detail_obs.source}"
                )
                detail_cols = ui.columns(2)
                with detail_cols[0]:
                    ui.write("**Metadata**")
                    ui.write(
                        f"- Source: {detail_obs.source}\n"
                        f"- Timestamp: {detail_obs.timestamp}\n"
                        f"- Processed: {'Yes' if detail_obs.processed else 'No'}\n"
                        f"- Created: {detail_obs.created_at}\n"
                        f"- Updated: {detail_obs.updated_at or 'Never'}"
                    )
                with detail_cols[1]:
                    ui.write("**Tags**")
                    if detail_obs.tags:
                        for tag in detail_obs.tags:
                            ui.write(f"- {tag}")
                    else:
                        ui.write("(none)")
                ui.write("**Data Payload**")
                ui.json(detail_obs.raw_data)
            except DashboardApiError as e:
                if e.status_code == 401:
                    ui.show_warning("You are not authorized to view this observation.")
                elif e.status_code == 404:
                    ui.show_warning(
                        f"Observation #{st.session_state.obs_detail_id} not found."
                    )
                else:
                    ui.show_error(f"Could not fetch observation details: {e}")
            except Exception as exc:  # noqa: BLE001
                ui.show_error(f"Error loading observation detail: {exc}")

    except DashboardApiError as e:
        if e.status_code == 401:
            ui.show_warning("Log in from the sidebar to view observations.")
        else:
            ui.show_error(f"Could not reach ingestor: {e}")
    except Exception as exc:  # noqa: BLE001
        ui.show_error(f"Error loading observations: {exc}")
