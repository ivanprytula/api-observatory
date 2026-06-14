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


# ---- Panel callbacks ----
# Each panel receives the adapter plus the current auth and config.
# Core logic lives here; UI rendering is fully delegated to the adapter.

PanelFn = Callable[[UIAdapter, AuthManager, Any], None]
