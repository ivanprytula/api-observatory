"""Streamlit UI adapter — bridges core logic to Streamlit primitives."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import streamlit as st
from services.dashboard.core.auth import AuthManager


_SESSION_DEFAULTS: dict[str, Any] = {
    "_auth_manager": None,
    "ws_messages": [],
    "ws_connected": False,
    "_ws_runtime": None,
    "probe_results": {},
    "last_refresh": 0.0,
}


def _ensure_ws_runtime() -> dict:
    if st.session_state.get("_ws_runtime") is None:
        st.session_state._ws_runtime = {
            "stop": threading.Event(),
            "buf": queue.Queue(),
            "thread": None,
        }
    return st.session_state._ws_runtime


class StreamlitUIAdapter:
    """Implements UIAdapter using Streamlit API calls."""

    def __init__(self) -> None:
        self._session: Any = st.session_state
        for key, default in _SESSION_DEFAULTS.items():
            self._session.setdefault(key, default)

    # -- Store protocol (Layer 3) --

    def get(self, key: str, default: Any = None) -> Any:
        return self._session.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._session[key] = value

    def has(self, key: str) -> bool:
        return key in self._session

    def delete(self, key: str) -> None:
        self._session.pop(key, None)

    def clear(self) -> None:
        for k in list(self._session.keys()):
            if not k.startswith("_"):
                self._session.pop(k, None)

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._session.setdefault(key, default)

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> Callable:
        return lambda: None

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
        self,
        rows: Sequence[Mapping[str, Any]],
        width: int | Literal["stretch", "content"] = "stretch",
    ) -> None:
        st.dataframe(list(rows), width=width)

    def rerun(self) -> None:
        st.rerun()

    def clear_cache(self) -> None:
        st.cache_data.clear()

    def auth_manager_from_session(self) -> AuthManager:
        if self._session.get("_auth_manager") is None:
            self._session._auth_manager = AuthManager()
        return self._session._auth_manager

    def sync_auth_from_logged_in(self, manager: AuthManager) -> None:
        pass

    @property
    def ws_messages(self) -> list[dict[str, Any]]:
        return self._session.get("ws_messages", [])

    @ws_messages.setter
    def ws_messages(self, value: list[dict[str, Any]]) -> None:
        self._session.ws_messages = value

    @property
    def ws_connected(self) -> bool:
        return self._session.get("ws_connected", False)

    @ws_connected.setter
    def ws_connected(self, value: bool) -> None:
        self._session.ws_connected = value

    @property
    def ws_stop_event(self) -> threading.Event:
        return _ensure_ws_runtime()["stop"]

    @property
    def ws_buffer(self) -> queue.Queue[dict[str, Any]]:
        return _ensure_ws_runtime()["buf"]

    @property
    def ws_thread(self) -> threading.Thread | None:
        return _ensure_ws_runtime()["thread"]

    def set_ws_thread(self, thread: threading.Thread | None) -> None:
        _ensure_ws_runtime()["thread"] = thread

    @property
    def probe_results(self) -> dict[int, dict[str, Any]]:
        return self._session.get("probe_results", {})

    @probe_results.setter
    def probe_results(self, value: dict[int, dict[str, Any]]) -> None:
        self._session.probe_results = value

    @property
    def last_refresh(self) -> float:
        return self._session.get("last_refresh", 0.0)

    @last_refresh.setter
    def last_refresh(self, value: float) -> None:
        self._session.last_refresh = value

    def empty(self) -> Any:
        return st.empty()

    def columns(self, spec: int | Sequence[int | float]) -> Any:
        return st.columns(spec)

    def text_input(
        self,
        label: str,
        value: str = "",
        placeholder: str = "",
        key: str | None = None,
    ) -> Any:
        return st.text_input(label, value=value, placeholder=placeholder, key=key)

    def number_input(
        self,
        label: str,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        value: int | float = 0,
        step: int | float = 1,
        key: str | None = None,
    ) -> int | float:
        return st.number_input(
            label=label,
            min_value=min_value,
            max_value=max_value,
            value=value,
            step=step,
            key=key,
        )

    def button(self, label: str, key: str | None = None, **kwargs: Any) -> bool:
        return st.button(label, key=key, **kwargs)

    def expander(self, label: str, expanded: bool = False) -> Any:
        return st.expander(label, expanded=expanded)

    def divider(self) -> None:
        st.divider()

    def checkbox(self, label: str, value: bool = False, key: str | None = None) -> bool:
        return st.checkbox(label, value=value, key=key)

    def form(self, key: str) -> Any:
        return st.form(key)

    def form_submit_button(self, label: str, key: str | None = None) -> bool:
        return st.form_submit_button(label, key=key)

    def container(self) -> Any:
        return st.container()

    def tabs(self, labels: list[str]) -> Any:
        return st.tabs(labels)

    def spinner(self, text: str = "Loading...") -> Any:
        return st.spinner(text)

    def caption(self, text: str) -> None:
        st.caption(text)

    def header(self, text: str) -> None:
        st.header(text)

    def subheader(self, text: str) -> None:
        st.subheader(text)

    def markdown(self, text: str) -> None:
        st.markdown(text)

    def json(self, data: Any, expanded: bool = True) -> None:
        st.json(data, expanded=expanded)

    def write(self, text: Any) -> None:
        st.write(text)

    def selectbox(
        self, label: str, options: Sequence[Any], key: str | None = None
    ) -> Any:
        return st.selectbox(label, options, key=key)
