"""Streamlit auth sidebar component with login and sign-up tabs."""

from __future__ import annotations

import streamlit as st
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


def _render_login_tab(ui: UIAdapter, manager: AuthManager) -> None:
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


def _render_register_tab(ui: UIAdapter, manager: AuthManager) -> None:
    with st.form("register_form"):
        uname = st.text_input("Username")
        email = st.text_input("Email")
        pwd = st.text_input("Password", type="password")
        pwd_confirm = st.text_input("Confirm password", type="password")
        if st.form_submit_button("Create Account"):
            if not uname or not email or not pwd:
                ui.show_error("All fields are required.")
                return
            if pwd != pwd_confirm:
                ui.show_error("Passwords do not match.")
                return
            if len(pwd) < 8:
                ui.show_error("Password must be at least 8 characters.")
                return
            error = manager.do_register(uname, email, pwd)
            if error:
                ui.show_error(error)
            else:
                ui.show_success("Account created! Log in with your credentials.")


def render_auth_sidebar(ui: UIAdapter, manager: AuthManager) -> None:
    """Render the login/sign-up sidebar for Streamlit."""
    with st.sidebar:
        st.header("Authentication")
        if not manager.state.logged_in:
            login_tab, register_tab = st.tabs(["Login", "Sign Up"])
            with login_tab:
                _render_login_tab(ui, manager)
            with register_tab:
                _render_register_tab(ui, manager)
        else:
            st.success(f"Logged in as **{manager.state.username}**")
            if st.button("Logout"):
                manager.logout()
                ui.clear_cache()
                ui.rerun()
