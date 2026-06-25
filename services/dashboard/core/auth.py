"""Framework-agnostic authentication state machine.

Stores tokens in memory; adapters persist state via cookies, session_state, or Redis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from services.dashboard.core.config import DashboardConfig


class AuthApiError(Exception):
    """Raised when an auth endpoint call fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AuthState:
    """Current authentication state for a user session."""

    access_token: str = ""
    refresh_token: str = ""
    username: str = ""
    logged_in: bool = False
    token_expires_at: float | None = None

    @property
    def is_valid(self) -> bool:
        if not self.logged_in or not self.access_token:
            return False
        if self.token_expires_at is not None:
            return time.time() < self.token_expires_at - 30
        return True


class AuthManager:
    """Manages OAuth2 token lifecycle: login, refresh, logout.

    Framework-agnostic — callers must persist state via their own session backend.
    """

    def __init__(self, config: DashboardConfig | None = None) -> None:
        self._config = config
        self._state = AuthState()

    @property
    def config(self) -> DashboardConfig:
        if self._config is None:
            from services.dashboard.core.config import _CONFIG_SINGLETON

            self._config = _CONFIG_SINGLETON
        return self._config

    @config.setter
    def config(self, value: DashboardConfig) -> None:
        self._config = value

    @property
    def state(self) -> AuthState:
        return self._state

    @property
    def access_token(self) -> str:
        return self._state.access_token

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self._state.access_token:
            return {}
        return {"Authorization": f"Bearer {self._state.access_token}"}

    def login(
        self,
        access_token: str,
        refresh_token: str,
        username: str,
        expires_in: int | None = None,
    ) -> None:
        self._state.access_token = access_token
        self._state.refresh_token = refresh_token
        self._state.username = username
        self._state.logged_in = bool(access_token)
        if expires_in is not None:
            self._state.token_expires_at = time.time() + expires_in

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        self._state.access_token = access_token
        self._state.refresh_token = refresh_token

    def logout(self) -> None:
        self._state = AuthState()

    def refresh(
        self,
        new_access_token: str,
        new_refresh_token: str,
        expires_in: int | None = None,
    ) -> None:
        self._state.access_token = new_access_token
        self._state.refresh_token = new_refresh_token
        if expires_in is not None:
            self._state.token_expires_at = time.time() + expires_in
        self._state.logged_in = bool(new_access_token)

    def rotate_from_dict(self, body: dict) -> bool:
        access = body.get("access_token", "")
        if not access:
            self.logout()
            return False
        refresh = body.get("refresh_token", self._state.refresh_token)
        self.set_tokens(access, refresh)
        return True

    # ------------------------------------------------------------------
    # API call helpers (Core-level, no UI dependencies)
    # ------------------------------------------------------------------

    def do_register(self, username: str, email: str, password: str) -> str | None:
        """POST /api/v1/auth/register.

        Returns an error message string or None on success.
        Does NOT auto-login — caller switches to the login tab on success.
        """
        url = f"{self.config.api_base_url}/api/v1/auth/register"
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(
                    url,
                    json={
                        "username": username,
                        "email": email,
                        "password": password,
                    },
                )
                if r.status_code == 201:
                    return None
                detail = r.json().get("detail", r.text[:120])
                return f"Registration failed ({r.status_code}): {detail}"
        except Exception as exc:  # noqa: BLE001
            return f"Connection error: {exc}"

    def do_login(self, username: str, password: str) -> str | None:
        """POST /api/v1/auth/token.

        Returns an error message string or None on success.
        On success, updates token state in-place.
        """
        url = f"{self.config.api_base_url}/api/v1/auth/token"
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(url, data={"username": username, "password": password})
                if r.status_code == 200:
                    body = r.json()
                    self.login(
                        access_token=body["access_token"],
                        refresh_token=body.get("refresh_token", ""),
                        username=username,
                    )
                    return None
                return f"Login failed ({r.status_code}): {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            return f"Connection error: {exc}"

    def do_refresh(self) -> bool:
        """POST /api/v1/auth/refresh with the current refresh token.

        Rotates both tokens on success. Returns True on success, False on failure.
        On failure, clears auth state.
        """
        rt = self._state.refresh_token
        if not rt:
            return False
        url = f"{self.config.api_base_url}/api/v1/auth/refresh"
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(url, json={"refresh_token": rt})
                if r.status_code == 200:
                    body = r.json()
                    self.set_tokens(body["access_token"], body.get("refresh_token", ""))
                    return True
        except Exception:  # noqa: BLE001  # nosec B110 — refresh failure: force logout path
            pass
        self.logout()
        return False
