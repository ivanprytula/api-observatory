"""UI adapter protocols for framework-agnostic dashboard.

Each UI framework implements these protocols to bridge the core logic
to its respective rendering model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from services.dashboard.core.auth import AuthManager


# ---- Session / Auth ----


@runtime_checkable
class SessionStore(Protocol):
    """Persist and retrieve auth state outside the core layer."""

    def get_auth(self) -> AuthManager:
        """Return (or lazily create) the AuthManager for this session."""

    def set_auth(self, auth: AuthManager) -> None:
        """Persist the updated AuthManager."""

    def get(self, key: str, default: Any = None) -> Any:
        """Generic session-state read (replaces st.session_state.get)."""

    def set(self, key: str, value: Any) -> None:
        """Generic session-state write."""

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Set key to default if absent; return the value."""


# ---- Rendering primitives ----


@runtime_checkable
class UIAdapter(Protocol):
    """Minimal rendering surface needed by core panel functions."""

    def show_error(self, message: str) -> None:
        """Display an error to the user."""

    def show_warning(self, message: str) -> None:
        """Display a warning."""

    def show_info(self, message: str) -> None:
        """Display an informational message."""

    def show_success(self, message: str) -> None:
        """Display a success message."""

    def metric(self, label: str, value: str, delta: str | None = None) -> None:
        """Render a metric card."""

    def render_dataframe(
        self, rows: Sequence[Mapping[str, Any]], width: str = "stretch"
    ) -> None:
        """Render a tabular data view."""

    def rerun(self) -> None:
        """Trigger a UI refresh (st.rerun equivalent)."""

    def clear_cache(self) -> None:
        """Clear any framework-level data cache."""

    def header(self, text: str) -> None:
        """Render a section header."""

    def subheader(self, text: str) -> None:
        """Render a subsection header."""

    def write(self, text: Any) -> None:
        """Render markdown / text."""

    def caption(self, text: str) -> None:
        """Render small caption text."""

    def text_input(
        self,
        label: str,
        value: str = "",
        placeholder: str = "",
        key: str | None = None,
    ) -> str:
        """Render a text input widget and return its current value."""
        ...

    def number_input(
        self,
        label: str,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        value: int | float = 0,
        step: int | float = 1,
        key: str | None = None,
    ) -> int | float:
        """Render a numeric input widget and return its current value."""
        ...

    def button(self, label: str, key: str | None = None) -> bool:
        """Render a button and return True when clicked."""
        ...

    def columns(self, spec: int | Sequence[int | float]) -> Any:
        """Return a list of column context-managers."""
        ...

    def json(self, data: Any) -> None:
        """Render a JSON payload."""

    def empty(self) -> Any:
        """Return an empty placeholder container."""
        ...

    def expander(self, label: str, expanded: bool = False) -> Any:
        """Return an expander context-manager."""
        ...

    def divider(self) -> None:
        """Render a horizontal divider."""

    def checkbox(self, label: str, value: bool = False, key: str | None = None) -> bool:
        """Render a checkbox and return its current value."""
        ...

    def form(self, key: str) -> Any:
        """Return a form context-manager."""
        ...

    def form_submit_button(self, label: str, key: str | None = None) -> bool:
        """Render a form submit button and return True when clicked."""
        ...

    def container(self) -> Any:
        """Return a container context-manager."""
        ...

    def markdown(self, text: str) -> None:
        """Render markdown text."""


# ---- Panel callbacks ----
# Each panel receives the adapter plus the current auth and config.
# Core logic lives here; UI rendering is fully delegated to the adapter.

PanelFn = Callable[[UIAdapter, AuthManager, Any], None]
