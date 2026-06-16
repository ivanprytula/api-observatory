"""Framework-agnostic reactive store.

Adapts to any UI framework via the ``Store`` protocol:

- Streamlit adapter → wraps ``st.session_state``
- React adapter → wraps ``useState`` / ``useReducer``
- Dash adapter → wraps ``dash.callback_context``

Usage::

    store = StreamlitStore()
    store.set("access_token", "abc")
    token = store.get("access_token", "")
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class Store(Protocol):
    """Minimal reactive state store.

    Implementations map to framework-specific backends
    (session_state, useState, callback_context).
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from the store."""

    def set(self, key: str, value: Any) -> None:
        """Write a value to the store."""

    def has(self, key: str) -> bool:
        """Return True if the key exists in the store."""

    def delete(self, key: str) -> None:
        """Remove a key from the store."""

    def clear(self) -> None:
        """Remove all keys from the store."""

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> Callable:
        """Register a change listener; returns an unsubscribe callable."""


class InMemoryStore:
    """Simple dict-backed store for testing or non-reactive contexts.

    Does NOT implement subscribe (no-ops are fine for MVP).
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> Callable:
        return lambda: None
