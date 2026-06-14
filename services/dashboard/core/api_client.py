"""HTTP API client for the dashboard.

Framework-agnostic sync function collection returning typed Pydantic models.
Adapters can call these directly; caching should wrap them (framework-specific).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from services.dashboard.core.auth import AuthManager
from services.dashboard.core.config import config
from services.dashboard.core.models import (
    DriftEventResponse,
    ScorecardListResponse,
    SourceHealthResponse,
    SourceProfileResponse,
)


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DashboardApiError(Exception):
    """Raised when the ingestor API returns an unexpected error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _headers(auth: AuthManager | None = None) -> dict[str, str]:
    token = auth.access_token if auth else ""
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _handle_error(response: httpx.Response, context: str) -> None:
    if response.status_code == 401:
        raise DashboardApiError(f"Unauthorized — {context}", status_code=401)
    if response.status_code >= 400:
        raise DashboardApiError(
            f"{context} failed ({response.status_code}): {response.text[:200]}",
            status_code=response.status_code,
        )


def fetch_scorecards(
    auth: AuthManager | None = None,
    limit: int = 50,
    timeout: float | None = None,
) -> ScorecardListResponse:
    """Return parsed scorecard list from the ingestor API."""
    url = f"{config.api_base_url}/api/v1/scorecards"
    try:
        with httpx.Client(timeout=timeout or config.request_timeout) as client:
            r = client.get(url, params={"limit": limit}, headers=_headers(auth))
            _handle_error(r, "fetch_scorecards")
            data = r.json()
            return ScorecardListResponse(**data)
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Network error fetching scorecards: {exc}") from exc


def fetch_sources(
    auth: AuthManager,
    limit: int = 50,
    timeout: float | None = None,
) -> list[SourceProfileResponse]:
    """Return parsed source profile list."""
    url = f"{config.api_base_url}/api/v1/sources"
    try:
        with httpx.Client(timeout=timeout or config.request_timeout) as client:
            r = client.get(url, params={"limit": limit}, headers=_headers(auth))
            _handle_error(r, "fetch_sources")
            data = r.json()
            items = data.get("items", [])
            return [SourceProfileResponse(**item) for item in items]
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Network error fetching sources: {exc}") from exc


def fetch_drift_events(
    source_id: int,
    auth: AuthManager,
    limit: int = 20,
    timeout: float | None = None,
) -> list[DriftEventResponse]:
    """Return parsed drift events for a single source."""
    url = f"{config.api_base_url}/api/v1/contracts/sources/{source_id}/drift-events"
    try:
        with httpx.Client(timeout=timeout or config.request_timeout) as client:
            r = client.get(url, params={"limit": limit}, headers=_headers(auth))
            _handle_error(r, "fetch_drift_events")
            data = r.json()
            items = data.get("items", [])
            return [DriftEventResponse(**item) for item in items]
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Network error fetching drift events: {exc}") from exc


def fetch_health_status(timeout: float | None = None) -> dict[str, dict]:
    """Probe /health and /readyz; return a dict of {endpoint: {status_code, body, error?}}."""
    results: dict[str, dict] = {}
    to = timeout or config.request_timeout
    for label, url in (
        ("liveness (/health)", f"{config.api_base_url}/health"),
        ("readiness (/readyz)", f"{config.api_base_url}/readyz"),
    ):
        try:
            with httpx.Client(timeout=to) as client:
                r = client.get(url)
            results[label] = {"status_code": r.status_code, "body": r.json()}
        except Exception as exc:  # noqa: BLE001
            results[label] = {"status_code": None, "body": None, "error": str(exc)}
    return results


def fetch_scheduler_jobs(timeout: float | None = None) -> dict:
    """Return scheduler job status from /health/jobs-metrics."""
    url = f"{config.api_base_url}/health/jobs-metrics"
    try:
        with httpx.Client(timeout=timeout or config.request_timeout) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Failed to fetch scheduler jobs: {exc}") from exc


def fetch_prometheus_metrics(timeout: float | None = None) -> str:
    """Return raw Prometheus metrics text."""
    url = f"{config.api_base_url}/metrics"
    try:
        with httpx.Client(timeout=timeout or config.request_timeout) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Failed to fetch metrics: {exc}") from exc


def probe_source(
    source_id: int,
    auth: AuthManager,
    timeout: float | None = None,
) -> SourceHealthResponse:
    """Trigger a live health probe for a single source."""
    url = f"{config.api_base_url}/api/v1/sources/{source_id}/health"
    try:
        with httpx.Client(timeout=timeout or config.probe_timeout) as client:
            r = client.get(url, headers=_headers(auth))
            _handle_error(r, "probe_source")
            return SourceHealthResponse(**r.json())
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Probe failed for source {source_id}: {exc}") from exc


def agent_enrich(
    observation_id: int,
    auth: AuthManager,
    timeout: float | None = None,
) -> dict:
    """Trigger a full-auto enrichment run; returns the JSON response body."""
    url = f"{config.api_base_url}/api/v1/agent/enrich/{observation_id}"
    try:
        with httpx.Client(timeout=timeout or config.agent_timeout) as client:
            r = client.post(url, headers=_headers(auth))
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Agent enrichment failed: {exc}") from exc


def agent_start_hitl(
    observation_id: int,
    auth: AuthManager,
    timeout: float | None = None,
) -> dict:
    """Start a Human-in-the-Loop enrichment review."""
    url = f"{config.api_base_url}/api/v1/agent/enrich/{observation_id}/review"
    try:
        with httpx.Client(timeout=timeout or config.agent_timeout) as client:
            r = client.post(url, headers=_headers(auth))
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"HITL start failed: {exc}") from exc


def agent_resume(
    run_id: str,
    approve: bool,
    auth: AuthManager,
    timeout: float | None = None,
) -> dict:
    """Resume a paused HITL run with approve or reject."""
    url = f"{config.api_base_url}/api/v1/agent/runs/{run_id}/resume"
    try:
        with httpx.Client(timeout=timeout or config.agent_timeout) as client:
            r = client.post(url, json={"approve": approve}, headers=_headers(auth))
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Agent resume failed: {exc}") from exc


async def fetch_prometheus_metrics_async(
    auth: AuthManager | None = None,
    timeout: float | None = None,
) -> str:
    """Async variant — for frameworks with an event loop (Dash callback, React)."""
    url = f"{config.api_base_url}/metrics"
    headers = _headers(auth) if auth else {}
    try:
        async with httpx.AsyncClient(
            timeout=timeout or config.request_timeout
        ) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Async metrics fetch failed: {exc}") from exc


async def fetch_sources_async(
    auth: AuthManager,
    limit: int = 50,
    timeout: float | None = None,
) -> list[SourceProfileResponse]:
    """Async variant of fetch_sources."""
    url = f"{config.api_base_url}/api/v1/sources"
    try:
        async with httpx.AsyncClient(
            timeout=timeout or config.request_timeout
        ) as client:
            r = await client.get(url, params={"limit": limit}, headers=_headers(auth))
            _handle_error(r, "fetch_sources_async")
            data = r.json()
            return [SourceProfileResponse(**item) for item in data.get("items", [])]
    except httpx.HTTPError as exc:
        raise DashboardApiError(f"Async sources fetch failed: {exc}") from exc
