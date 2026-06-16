"""Streamlit auth sidebar component."""

from __future__ import annotations

import streamlit as st
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


def render_auth_sidebar(ui: UIAdapter, manager: AuthManager) -> None:
    """Render the login/logout sidebar for Streamlit."""
    with st.sidebar:
        st.header("Authentication")
        if not manager.state.logged_in:
            with st.form("login_form"):
                uname = st.text_input("Username")
                pwd = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    error = manager.do_login(uname, pwd)
                    if error:
                        ui.show_error(error)
                    else:
                        ui.clear_cache()
                        ui.rerun()
        else:
            st.success(f"Logged in as **{manager.state.username}**")
            if st.button("Logout"):
                manager.logout()
                ui.clear_cache()
                ui.rerun()
