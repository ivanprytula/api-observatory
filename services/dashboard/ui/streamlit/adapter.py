"""Streamlit UI adapter — bridges core logic to Streamlit primitives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st
from services.dashboard.core.auth import AuthManager


class StreamlitUIAdapter:
    """Implements UIAdapter using Streamlit API calls."""

    def __init__(self) -> None:
        self._session: dict[str, Any] = st.session_state
        if "ws_messages" not in self._session:
            self._session.ws_messages = []  # type: ignore[attr-defined]
        if "ws_connected" not in self._session:
            self._session.ws_connected = False  # type: ignore[attr-defined]
        if "_ws_stop" not in self._session:
            self._session._ws_stop = __import__("threading").Event()  # type: ignore[attr-defined]
        if "_ws_buf" not in self._session:
            self._session._ws_buf = __import__("queue").Queue()  # type: ignore[attr-defined]
        if "_ws_thread" not in self._session:
            self._session._ws_thread = None  # type: ignore[attr-defined]
        if "probe_results" not in self._session:
            self._session.probe_results = {}  # type: ignore[attr-defined]
        if "last_refresh" not in self._session:
            self._session.last_refresh = 0.0  # type: ignore[attr-defined]
        if "agent_run_id" not in self._session:
            self._session.agent_run_id = ""  # type: ignore[attr-defined]
        if "agent_result" not in self._session:
            self._session.agent_result = None  # type: ignore[attr-defined]
        if "agent_hitl_paused" not in self._session:
            self._session.agent_hitl_paused = False  # type: ignore[attr-defined]
        if "agent_stream_events" not in self._session:
            self._session.agent_stream_events = []  # type: ignore[attr-defined]

    # -- UIAdapter primitives --

    def show_error(self, message: str) -> None:
        st.error(message)

    def show_warning(self, message: str) -> None:
        st.warning(message)

    def show_info(self, message: str) -> None:
        st.info(message)

    def show_success(self, message: str) -> None:
        st.success(message)

    def metric(self, label: str, value: str, delta: str | None = None) -> None:
        st.metric(label, value, delta)

    def render_dataframe(
        self, rows: Sequence[Mapping[str, Any]], width: int | str = "stretch"
    ) -> None:
        st.dataframe(list(rows), width=width)

    def rerun(self) -> None:
        st.rerun()

    def clear_cache(self) -> None:
        st.cache_data.clear()

    # -- Auth helpers specific to Streamlit ----

    def auth_manager_from_session(self) -> AuthManager:
        if "_auth_manager" not in self._session:
            manager = AuthManager()
            manager.login(
                access_token=self._session.get("access_token", ""),
                refresh_token=self._session.get("refresh_token", ""),
                username=self._session.get("auth_username", ""),
            )
            self._session._auth_manager = manager
        return self._session._auth_manager

    def sync_auth_to_session(self, manager: AuthManager) -> None:
        self._session["access_token"] = manager.access_token
        self._session["refresh_token"] = manager.state.refresh_token
        self._session["logged_in"] = manager.state.logged_in
        self._session["auth_username"] = manager.state.username
        if "_auth_manager" in self._session:
            del self._session._auth_manager

    # -- WebSocket helpers ----

    @property
    def ws_messages(self) -> list[dict]:
        return self._session.get("ws_messages", [])

    @ws_messages.setter
    def ws_messages(self, value: list[dict]) -> None:
        self._session.ws_messages = value  # type: ignore[attr-defined]

    @property
    def ws_connected(self) -> bool:
        return self._session.get("ws_connected", False)

    @ws_connected.setter
    def ws_connected(self, value: bool) -> None:
        self._session.ws_connected = value  # type: ignore[attr-defined]

    @property
    def ws_stop_event(self) -> Any:
        return self._session.get("_ws_stop")

    @property
    def ws_buffer(self) -> Any:
        return self._session.get("_ws_buf")

    @property
    def ws_thread(self) -> Any:
        return self._session.get("_ws_thread")

    def set_ws_thread(self, thread: Any) -> None:
        self._session._ws_thread = thread  # type: ignore[attr-defined]

    # -- Agent state helpers ----

    @property
    def agent_run_id(self) -> str:
        return self._session.get("agent_run_id", "")

    @agent_run_id.setter
    def agent_run_id(self, value: str) -> None:
        self._session.agent_run_id = value  # type: ignore[attr-defined]

    @property
    def agent_result(self) -> Any:
        return self._session.get("agent_result")

    @agent_result.setter
    def agent_result(self, value: Any) -> None:
        self._session.agent_result = value  # type: ignore[attr-defined]

    @property
    def agent_hitl_paused(self) -> bool:
        return self._session.get("agent_hitl_paused", False)

    @agent_hitl_paused.setter
    def agent_hitl_paused(self, value: bool) -> None:
        self._session.agent_hitl_paused = value  # type: ignore[attr-defined]

    @property
    def agent_stream_events(self) -> list[dict]:
        return self._session.get("agent_stream_events", [])

    @agent_stream_events.setter
    def agent_stream_events(self, value: list[dict]) -> None:
        self._session.agent_stream_events = value  # type: ignore[attr-defined]

    @property
    def probe_results(self) -> dict:
        return self._session.get("probe_results", {})

    @probe_results.setter
    def probe_results(self, value: dict) -> None:
        self._session.probe_results = value  # type: ignore[attr-defined]

    @property
    def last_refresh(self) -> float:
        return self._session.get("last_refresh", 0.0)

    @last_refresh.setter
    def last_refresh(self, value: float) -> None:
        self._session.last_refresh = value  # type: ignore[attr-defined]

    # -- Additional rendering helpers ----

    def empty(self) -> Any:
        return st.empty()

    def columns(self, spec: list[int] | int) -> Any:
        return st.columns(spec)

    def form(self, key: str) -> Any:
        return st.form(key)

    def text_input(self, label: str, key: str | None = None) -> Any:
        return st.text_input(label, key=key)

    def number_input(
        self,
        label: str,
        min_value: int | None = None,
        value: int = 1,
        step: int = 1,
        key: str | None = None,
    ) -> Any:
        return st.number_input(
            label=label, min_value=min_value, value=value, step=step, key=key
        )

    def button(self, label: str, key: str | None = None, **kwargs: Any) -> Any:
        return st.button(label, key=key, **kwargs)

    def expander(self, label: str, expanded: bool = False) -> Any:
        return st.expander(label, expanded=expanded)

    def tabs(self, labels: list[str]) -> Any:
        return st.tabs(labels)

    def spinner(self, text: str = "Loading...") -> Any:
        return st.spinner(text)

    def caption(self, text: str) -> None:
        st.caption(text)

    def header(self, text: str) -> None:
        st.header(text)

    def markdown(self, text: str) -> None:
        st.markdown(text)

    def json(self, data: Any, expanded: bool = True) -> None:
        st.json(data, expanded=expanded)

    def write(self, data: Any) -> None:
        st.write(data)

    def divider(self) -> None:
        st.divider()

    def selectbox(
        self, label: str, options: Sequence[Any], key: str | None = None
    ) -> Any:
        return st.selectbox(label, options, key=key)
