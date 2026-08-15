"""Mock UIAdapter for framework-agnostic dashboard tests.

Captures rendered output in plain Python lists/dicts so tests can assert
on UI behavior without importing Streamlit.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from services.dashboard.core.auth import AuthManager


class ColumnStub:
    """Lightweight stub that mimics a Streamlit column or container."""

    def __init__(self, mock: MockUIAdapter) -> None:
        self._mock = mock

    def __enter__(self) -> ColumnStub:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def write(self, text: Any) -> None:
        self._mock.writes.append(text)

    def markdown(self, text: str) -> None:
        self._mock.markdowns.append(text)

    def caption(self, text: str) -> None:
        self._mock.captions.append(text)

    def button(self, label: str, key: str | None = None, **kwargs: Any) -> bool:
        self._mock._record_button(label, key)
        if key is not None and key in self._mock.button_return_values:
            clicked = self._mock.button_return_values[key]
        elif key is None and label in self._mock.button_return_values:
            clicked = self._mock.button_return_values[label]
        else:
            clicked = False
        if clicked and "on_click" in kwargs:
            kwargs["on_click"]()
        return clicked

    def metric(
        self, label: str, value: str, delta: str | None = None, **kwargs: Any
    ) -> None:
        self._mock.metrics.append((label, value, delta))

    def info(self, text: str) -> None:
        self._mock.infos.append(text)

    def error(self, text: str) -> None:
        self._mock.errors.append(text)

    def success(self, text: str) -> None:
        self._mock.successes.append(text)

    def warning(self, text: str) -> None:
        self._mock.warnings.append(text)

    def json(self, data: Any, expanded: bool = True) -> None:
        self._mock.jsons.append(data)

    def header(self, text: str) -> None:
        self._mock.headers.append(text)

    def subheader(self, text: str) -> None:
        self._mock.subheaders.append(text)

    def divider(self) -> None:
        self._mock.dividers.append(None)

    def checkbox(self, label: str, value: bool = False, key: str | None = None) -> bool:
        if key is not None and key in self._mock.checkbox_values:
            return self._mock.checkbox_values[key]
        return value

    def text_input(
        self,
        label: str,
        value: str = "",
        placeholder: str = "",
        key: str | None = None,
    ) -> str:
        if key is not None and key in self._mock.text_input_values:
            return self._mock.text_input_values[key]
        if key is None and label in self._mock.text_input_values:
            return self._mock.text_input_values[label]
        return value

    def number_input(
        self,
        label: str,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        value: int | float = 0,
        step: int | float = 1,
        key: str | None = None,
    ) -> int | float:
        if key is not None and key in self._mock.number_input_values:
            return self._mock.number_input_values[key]
        if key is None and label in self._mock.number_input_values:
            return self._mock.number_input_values[label]
        return value

    def selectbox(
        self,
        label: str,
        options: Sequence[Any],
        index: int = 0,
        key: str | None = None,
    ) -> Any:
        if key is not None and key in self._mock.selectbox_values:
            return self._mock.selectbox_values[key]
        if key is None and label in self._mock.selectbox_values:
            return self._mock.selectbox_values[label]
        if 0 <= index < len(options):
            return options[index]
        return options[0] if options else None

    def toggle(
        self,
        label: str,
        value: bool = False,
        key: str | None = None,
    ) -> bool:
        if key is not None and key in self._mock.toggle_values:
            return self._mock.toggle_values[key]
        if key is None and label in self._mock.toggle_values:
            return self._mock.toggle_values[label]
        return value

    def form_submit_button(self, label: str, key: str | None = None) -> bool:
        self._mock._record_button(label, key)
        if key is not None and key in self._mock.button_return_values:
            return self._mock.button_return_values[key]
        if key is None and label in self._mock.button_return_values:
            return self._mock.button_return_values[label]
        return False

    def expander(self, label: str, expanded: bool = False) -> _ExpanderStub:
        return _ExpanderStub(self._mock, label, expanded)

    def form(self, key: str) -> _FormStub:
        return _FormStub(self._mock, key)

    def empty(self) -> ColumnStub:
        return ColumnStub(self._mock)

    def container(self) -> ColumnStub:
        return ColumnStub(self._mock)


class _ExpanderStub:
    """Context-manager stub for ui.expander()."""

    def __init__(self, mock: MockUIAdapter, label: str, expanded: bool) -> None:
        self._mock = mock
        self._label = label
        self._expanded = expanded
        self._stub = ColumnStub(mock)

    def __enter__(self) -> ColumnStub:
        return self._stub

    def __exit__(self, *args: Any) -> None:
        return None


class _FormStub:
    """Context-manager stub for ui.form()."""

    def __init__(self, mock: MockUIAdapter, key: str) -> None:
        self._mock = mock
        self._key = key
        self._stub = ColumnStub(mock)

    def __enter__(self) -> ColumnStub:
        return self._stub

    def __exit__(self, *args: Any) -> None:
        return None


class _TabStub:
    """Context-manager stub for ui.tabs() tab items."""

    def __init__(self, mock: MockUIAdapter, label: str) -> None:
        self._mock = mock
        self._label = label
        self._stub = ColumnStub(mock)

    def __enter__(self) -> ColumnStub:
        return self._stub

    def __exit__(self, *args: Any) -> None:
        return None


class MockUIAdapter:
    """In-memory UIAdapter for tests."""

    def __init__(self, session: dict[str, Any] | None = None) -> None:
        self._session = session if session is not None else {}
        self._session.setdefault("_auth_manager", None)
        self._session.setdefault("ws_messages", [])
        self._session.setdefault("ws_connected", False)
        self._session.setdefault("_ws_runtime", None)
        self._session.setdefault("probe_results", {})
        self._session.setdefault("last_refresh", 0.0)

        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []
        self.successes: list[str] = []
        self.markdowns: list[str] = []
        self.headers: list[str] = []
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.jsons: list[Any] = []
        self.writes: list[Any] = []
        self.metrics: list[tuple[str, str, str | None]] = []
        self.dividers: list[None] = []
        self._button_calls: list[tuple[str, str | None]] = []

        self.button_return_values: dict[str, bool] = {}
        self.checkbox_values: dict[str, bool] = {}
        self.text_input_values: dict[str, str] = {}
        self.number_input_values: dict[str, int | float] = {}
        self.selectbox_values: dict[str, Any] = {}
        self.toggle_values: dict[str, bool] = {}

        self._ws_stop_event = threading.Event()
        self._ws_buffer: queue.Queue[dict[str, Any]] = queue.Queue()
        self._ws_thread: threading.Thread | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self._session.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._session[key] = value

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._session.setdefault(key, default)

    def has(self, key: str) -> bool:
        return key in self._session

    def delete(self, key: str) -> None:
        self._session.pop(key, None)

    def clear(self) -> None:
        for k in list(self._session.keys()):
            if not k.startswith("_"):
                self._session.pop(k, None)

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> Callable:
        return lambda: None

    def auth_manager_from_session(self) -> AuthManager:
        return self._session["_auth_manager"] or AuthManager()

    def sync_auth_from_logged_in(self, manager: AuthManager) -> None:
        pass

    @property
    def ws_messages(self) -> list[dict[str, Any]]:
        return self._session.get("ws_messages", [])

    @ws_messages.setter
    def ws_messages(self, value: list[dict[str, Any]]) -> None:
        self._session["ws_messages"] = value

    @property
    def ws_connected(self) -> bool:
        return self._session.get("ws_connected", False)

    @ws_connected.setter
    def ws_connected(self, value: bool) -> None:
        self._session["ws_connected"] = value

    @property
    def ws_stop_event(self) -> threading.Event:
        return self._ws_stop_event

    @property
    def ws_buffer(self) -> queue.Queue[dict[str, Any]]:
        return self._ws_buffer

    @property
    def ws_thread(self) -> threading.Thread | None:
        return self._ws_thread

    def set_ws_thread(self, thread: threading.Thread | None) -> None:
        self._ws_thread = thread

    @property
    def probe_results(self) -> dict[int, dict[str, Any]]:
        return self._session.get("probe_results", {})

    @probe_results.setter
    def probe_results(self, value: dict[int, dict[str, Any]]) -> None:
        self._session["probe_results"] = value

    @property
    def last_refresh(self) -> float:
        return self._session.get("last_refresh", 0.0)

    @last_refresh.setter
    def last_refresh(self, value: float) -> None:
        self._session["last_refresh"] = value

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def show_warning(self, message: str) -> None:
        self.warnings.append(message)

    def show_info(self, message: str) -> None:
        self.infos.append(message)

    def show_success(self, message: str) -> None:
        self.successes.append(message)

    def metric(
        self, label: str, value: str, delta: str | None = None, **kwargs: Any
    ) -> None:
        self.metrics.append((label, value, delta))

    def render_dataframe(
        self,
        rows: Sequence[Mapping[str, Any]],
        width: int | str = "stretch",
    ) -> None:
        self.writes.append(list(rows))

    def rerun(self) -> None:
        pass

    def clear_cache(self) -> None:
        pass

    def fetch_stack_features(self) -> dict[str, object]:
        return self._session.get("_stack_features", {})

    def header(self, text: str) -> None:
        self.headers.append(text)

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def write(self, text: Any) -> None:
        self.writes.append(text)

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def text_input(
        self,
        label: str,
        value: str = "",
        placeholder: str = "",
        key: str | None = None,
    ) -> str:
        if key is not None and key in self.text_input_values:
            return self.text_input_values[key]
        if key is None and label in self.text_input_values:
            return self.text_input_values[label]
        return value

    def number_input(
        self,
        label: str,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        value: int | float = 0,
        step: int | float = 1,
        key: str | None = None,
    ) -> int | float:
        if key is not None and key in self.number_input_values:
            return self.number_input_values[key]
        if key is None and label in self.number_input_values:
            return self.number_input_values[label]
        return value

    def button(self, label: str, key: str | None = None, **kwargs: Any) -> bool:
        self._record_button(label, key)
        if key is not None and key in self.button_return_values:
            clicked = self.button_return_values[key]
        elif key is None and label in self.button_return_values:
            clicked = self.button_return_values[label]
        else:
            clicked = False
        if clicked and "on_click" in kwargs:
            kwargs["on_click"]()
        return clicked

    def toggle(
        self,
        label: str,
        value: bool = False,
        key: str | None = None,
    ) -> bool:
        if key is not None and key in self.toggle_values:
            return self.toggle_values[key]
        if key is None and label in self.toggle_values:
            return self.toggle_values[label]
        return value

    def selectbox(
        self,
        label: str,
        options: Sequence[Any],
        index: int = 0,
        key: str | None = None,
    ) -> Any:
        if key is not None and key in self.selectbox_values:
            return self.selectbox_values[key]
        if key is None and label in self.selectbox_values:
            return self.selectbox_values[label]
        if 0 <= index < len(options):
            return options[index]
        return options[0] if options else None

    def tabs(self, labels: list[str]) -> list[_TabStub]:
        return [_TabStub(self, label) for label in labels]

    def spinner(self, text: str = "Loading...") -> _ExpanderStub:
        return _ExpanderStub(self, text, expanded=False)

    def columns(self, spec: int | Sequence[int | float]) -> list[ColumnStub]:
        if isinstance(spec, int):
            return [ColumnStub(self) for _ in range(spec)]
        return [ColumnStub(self) for _ in spec]

    def json(self, data: Any, expanded: bool = True) -> None:
        self.jsons.append(data)

    def empty(self) -> ColumnStub:
        return ColumnStub(self)

    def expander(self, label: str, expanded: bool = False) -> _ExpanderStub:
        return _ExpanderStub(self, label, expanded)

    def divider(self) -> None:
        self.dividers.append(None)

    def checkbox(self, label: str, value: bool = False, key: str | None = None) -> bool:
        if key is not None and key in self.checkbox_values:
            return self.checkbox_values[key]
        return value

    def form(self, key: str) -> _FormStub:
        return _FormStub(self, key)

    def form_submit_button(self, label: str, key: str | None = None) -> bool:
        self._record_button(label, key)
        if key is not None and key in self.button_return_values:
            return self.button_return_values[key]
        if key is None and label in self.button_return_values:
            return self.button_return_values[label]
        return False

    def container(self) -> ColumnStub:
        return ColumnStub(self)

    def markdown(self, text: str) -> None:
        self.markdowns.append(text)

    def sleep(self, ms: float = 0.0) -> None:
        pass

    def _record_button(self, label: str, key: str | None) -> None:
        self._button_calls.append((label, key))

    def reset(self) -> None:
        self.errors.clear()
        self.warnings.clear()
        self.infos.clear()
        self.successes.clear()
        self.markdowns.clear()
        self.headers.clear()
        self.subheaders.clear()
        self.captions.clear()
        self.jsons.clear()
        self.writes.clear()
        self.metrics.clear()
        self.dividers.clear()
        self._button_calls.clear()
