"""HTTP API client — resource classes + backwards-compatible flat functions.

Two access patterns:
  1. ``API`` object (preferred) — resource-class hierarchy::

       from services.dashboard.core.api_client import api
       sources = api.sources.list(token="...")
       obs = api.observations.list(token="...", page=1)

  2. Flat functions (legacy) — for backward compatibility with panels::

       from services.dashboard.core.api_client import fetch_sources
       sources = fetch_sources(auth=manager)
"""

from __future__ import annotations

from typing import Any

from libs.contracts.schemas_dashboard import (
    DriftEventResponse,
    ObservationListResponse,
    ObservationResponse,
    ScorecardListResponse,
    SourceHealthResponse,
    SourceProfileResponse,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.core.http_client import SyncClient, sync_client


class DashboardApiError(Exception):
    """Raised when the ingestor API returns an unexpected error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _raise_on_error(response: Any, context: str) -> None:
    """Check a response-like object for error status and raise."""
    from httpx import Response

    if isinstance(response, Response):
        status = response.status_code
        if status == 401:
            raise DashboardApiError(f"Unauthorized — {context}", status_code=401)
        if status >= 400:
            raise DashboardApiError(
                f"{context} failed ({status}): {response.text[:200]}",
                status_code=status,
            )
    elif isinstance(response, dict) and "status_code" in response:
        status = response.get("status_code")
        if status == 401:
            raise DashboardApiError(f"Unauthorized — {context}", status_code=401)
        if status and status >= 400:
            raise DashboardApiError(
                f"{context} failed ({status}): {response.get('body', '')}",
                status_code=status,
            )


# ---------------------------------------------------------------------------
# Resource classes
# ---------------------------------------------------------------------------


class SourcesResource:
    """CRUD + health probe for source profiles."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def list(self, token: str = "", limit: int = 50) -> list[SourceProfileResponse]:
        data = self._c.request(
            "GET", "/api/v1/sources", params={"limit": limit}, token=token
        )
        items = data.get("items", []) if isinstance(data, dict) else data
        return [SourceProfileResponse(**item) for item in items]

    def get(self, source_id: int, token: str = "") -> SourceProfileResponse:
        data = self._c.request("GET", f"/api/v1/sources/{source_id}", token=token)
        return SourceProfileResponse(**data)

    def create(
        self,
        token: str = "",
        name: str = "",
        base_url: str = "",
        health_check_path: str = "/health",
        probe_interval_seconds: int = 60,
        is_active: bool = True,
    ) -> SourceProfileResponse:
        payload = {
            "name": name,
            "base_url": base_url,
            "health_check_path": health_check_path,
            "probe_interval_seconds": probe_interval_seconds,
            "is_active": is_active,
        }
        try:
            data = self._c.request("POST", "/api/v1/sources", token=token, json=payload)
            return SourceProfileResponse(**data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                raise DashboardApiError(
                    "Source name already registered.", status_code=409
                ) from None
            raise DashboardApiError(
                f"Create source failed ({exc.response.status_code})",
                status_code=exc.response.status_code,
            ) from None

    def update(
        self,
        source_id: int,
        token: str = "",
        base_url: str | None = None,
        health_check_path: str | None = None,
        probe_interval_seconds: int | None = None,
        is_active: bool | None = None,
    ) -> SourceProfileResponse:
        payload: dict[str, Any] = {}
        if base_url is not None:
            payload["base_url"] = base_url
        if health_check_path is not None:
            payload["health_check_path"] = health_check_path
        if probe_interval_seconds is not None:
            payload["probe_interval_seconds"] = probe_interval_seconds
        if is_active is not None:
            payload["is_active"] = is_active
        data = self._c.request(
            "PATCH", f"/api/v1/sources/{source_id}", token=token, json=payload
        )
        return SourceProfileResponse(**data)

    def delete(self, source_id: int, token: str = "") -> None:
        resp = self._c.request_raw(
            "DELETE", f"/api/v1/sources/{source_id}", token=token
        )
        if resp.status_code != 204:
            _raise_on_error(resp, "delete_source")

    def probe(
        self, source_id: int, token: str = "", timeout: float | None = None
    ) -> SourceHealthResponse:
        data = self._c.request(
            "GET", f"/api/v1/sources/{source_id}/health", token=token
        )
        return SourceHealthResponse(**data)


class ObservationsResource:
    """Observations list + detail."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def list(
        self,
        token: str = "",
        page: int = 1,
        page_size: int = 25,
        source_filter: str | None = None,
    ) -> ObservationListResponse:
        skip = (page - 1) * page_size
        params: dict[str, Any] = {"skip": skip, "limit": page_size}
        if source_filter:
            params["source"] = source_filter
        data = self._c.request(
            "GET", "/api/v1/observations", token=token, params=params
        )
        return ObservationListResponse(**data)

    def get(self, observation_id: int, token: str = "") -> ObservationResponse:
        data = self._c.request(
            "GET", f"/api/v1/observations/{observation_id}", token=token
        )
        return ObservationResponse(**data)


class ScorecardsResource:
    """Provider scorecards."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def list(self, token: str = "", limit: int = 50) -> ScorecardListResponse:
        data = self._c.request(
            "GET", "/api/v1/scorecards", token=token, params={"limit": limit}
        )
        return ScorecardListResponse(**data)


class DriftResource:
    """Contract drift events."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def list(
        self, source_id: int, token: str = "", limit: int = 20
    ) -> list[DriftEventResponse]:
        data = self._c.request(
            "GET",
            f"/api/v1/contracts/sources/{source_id}/drift-events",
            token=token,
            params={"limit": limit},
        )
        items = data.get("items", []) if isinstance(data, dict) else data
        return [DriftEventResponse(**item) for item in items]


class HealthResource:
    """Liveness + readiness + scheduler health."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def probes(self) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for label, url_part in (
            ("liveness (/health)", "/health"),
            ("readiness (/readyz)", "/readyz"),
        ):
            try:
                r = self._c.request_raw("GET", url_part)
                results[label] = {"status_code": r.status_code, "body": r.json()}
            except Exception as exc:
                results[label] = {"status_code": None, "body": None, "error": str(exc)}
        return results

    def scheduler_jobs(self) -> dict:
        return self._c.request("GET", "/health/jobs-metrics")


class MetricsResource:
    """Prometheus /metrics text endpoint."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def raw(self, token: str = "") -> str:
        r = self._c.request_raw("GET", "/metrics", token=token)
        r.raise_for_status()
        return r.text


class AuthResource:
    """Login / register / refresh / logout."""

    def __init__(self, client: SyncClient) -> None:
        self._c = client

    def register(self, username: str, email: str, password: str) -> dict:
        return self._c.request(
            "POST",
            "/api/v1/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    def login(self, username: str, password: str) -> dict:
        return self._c.request(
            "POST",
            "/api/v1/auth/token",
            json={"username": username, "password": password},
        )

    def refresh(self, refresh_token: str) -> dict:
        return self._c.request(
            "POST", "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )


# ---------------------------------------------------------------------------
# API root object — single entry point for all resources
# ---------------------------------------------------------------------------


class API:
    """Top-level API accessor. Instantiated once; use the ``api`` singleton."""

    def __init__(self, client: SyncClient | None = None) -> None:
        c = client or sync_client
        self.sources = SourcesResource(c)
        self.observations = ObservationsResource(c)
        self.scorecards = ScorecardsResource(c)
        self.drift = DriftResource(c)
        self.health = HealthResource(c)
        self.metrics = MetricsResource(c)
        self.auth = AuthResource(c)


api = API()


# ---------------------------------------------------------------------------
# Backwards-compatible flat functions — delegate to api singleton
# These match the original function signatures used by existing panels.
# ---------------------------------------------------------------------------

import httpx  # noqa: E402 — import after httpx.HTTPStatusError reference


def _extract_token(auth: AuthManager | None = None) -> str:
    return auth.access_token if auth else ""


def fetch_sources(
    auth: AuthManager,
    limit: int = 50,
    timeout: float | None = None,
) -> list[SourceProfileResponse]:
    return api.sources.list(token=_extract_token(auth), limit=limit)


def create_source(
    auth: AuthManager,
    name: str,
    base_url: str,
    health_check_path: str = "/health",
    probe_interval_seconds: int = 60,
    is_active: bool = True,
    timeout: float | None = None,
) -> SourceProfileResponse:
    return api.sources.create(
        token=_extract_token(auth),
        name=name,
        base_url=base_url,
        health_check_path=health_check_path,
        probe_interval_seconds=probe_interval_seconds,
        is_active=is_active,
    )


def update_source(
    auth: AuthManager,
    source_id: int,
    base_url: str | None = None,
    health_check_path: str | None = None,
    probe_interval_seconds: int | None = None,
    is_active: bool | None = None,
    timeout: float | None = None,
) -> SourceProfileResponse:
    return api.sources.update(
        source_id=source_id,
        token=_extract_token(auth),
        base_url=base_url,
        health_check_path=health_check_path,
        probe_interval_seconds=probe_interval_seconds,
        is_active=is_active,
    )


def delete_source(
    auth: AuthManager,
    source_id: int,
    timeout: float | None = None,
) -> None:
    api.sources.delete(source_id=source_id, token=_extract_token(auth))


def fetch_scorecards(
    auth: AuthManager | None = None,
    limit: int = 50,
    timeout: float | None = None,
) -> ScorecardListResponse:
    return api.scorecards.list(token=_extract_token(auth), limit=limit)


def fetch_drift_events(
    source_id: int,
    auth: AuthManager,
    limit: int = 20,
    timeout: float | None = None,
) -> list[DriftEventResponse]:
    return api.drift.list(source_id=source_id, token=_extract_token(auth), limit=limit)


def fetch_health_status(timeout: float | None = None) -> dict[str, dict]:
    return api.health.probes()


def fetch_scheduler_jobs(timeout: float | None = None) -> dict:
    return api.health.scheduler_jobs()


def fetch_prometheus_metrics(timeout: float | None = None) -> str:
    return api.metrics.raw()


def fetch_observations(
    auth: AuthManager,
    page: int = 1,
    page_size: int = 25,
    source_filter: str | None = None,
    timeout: float | None = None,
) -> ObservationListResponse:
    return api.observations.list(
        token=_extract_token(auth),
        page=page,
        page_size=page_size,
        source_filter=source_filter,
    )


def fetch_observation(
    observation_id: int,
    auth: AuthManager,
    timeout: float | None = None,
) -> ObservationResponse:
    return api.observations.get(
        observation_id=observation_id, token=_extract_token(auth)
    )


def probe_source(
    source_id: int,
    auth: AuthManager,
    timeout: float | None = None,
) -> SourceHealthResponse:
    return api.sources.probe(source_id=source_id, token=_extract_token(auth))


# ---------------------------------------------------------------------------
# Async variants (for frameworks with an event loop)
# ---------------------------------------------------------------------------


from services.dashboard.core.http_client import async_client  # noqa: E402


async def fetch_prometheus_metrics_async(
    auth: AuthManager | None = None,
    timeout: float | None = None,
) -> str:
    token = _extract_token(auth)
    r = await async_client.request_raw("GET", "/metrics", token=token)
    r.raise_for_status()
    return r.text


async def fetch_sources_async(
    auth: AuthManager,
    limit: int = 50,
    timeout: float | None = None,
) -> list[SourceProfileResponse]:
    token = _extract_token(auth)
    data = await async_client.request(
        "GET", "/api/v1/sources", token=token, params={"limit": limit}
    )
    items = data.get("items", []) if isinstance(data, dict) else data
    return [SourceProfileResponse(**item) for item in items]
