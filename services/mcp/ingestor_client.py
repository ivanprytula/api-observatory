"""Thin authenticated HTTP client for the ingestor's real API.

Every function here calls the actual ingestor endpoint over HTTP (never an
in-process repository import) — same "own client, `raise_for_status()`,
explicit timeout" pattern `services.ingestor.vector_search` already uses to
call the `inference` service. A 401 triggers exactly one forced re-login and
one retry; any other error propagates as `httpx.HTTPStatusError`.
"""

from __future__ import annotations

from typing import Any

import httpx

from services.mcp import auth_client
from services.mcp.config import settings
from services.mcp.http import get_http_client


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """Issue one authenticated request, retrying once on a 401."""
    client = await get_http_client()
    url = f"{settings.ingestor_url.rstrip('/')}{path}"

    token = await auth_client.get_valid_token()
    response = await client.request(
        method,
        url,
        params=params,
        json=json,
        headers={"Authorization": f"Bearer {token}"},
        timeout=settings.http_timeout_seconds,
    )
    if response.status_code == httpx.codes.UNAUTHORIZED:
        token = await auth_client.force_relogin()
        response = await client.request(
            method,
            url,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.http_timeout_seconds,
        )

    response.raise_for_status()
    return response.json()


async def list_sources(
    is_active: bool | None = None, offset: int = 0, limit: int = 20
) -> Any:
    """List registered source profiles, optionally filtered by active state."""
    params: dict[str, Any] = {"offset": offset, "limit": limit}
    if is_active is not None:
        params["is_active"] = is_active
    return await _request("GET", "/api/v1/sources", params=params)


async def get_source(source_id: int) -> Any:
    """Fetch a single source profile by ID."""
    return await _request("GET", f"/api/v1/sources/{source_id}")


async def get_source_summary() -> Any:
    """Return aggregate source-registry statistics."""
    return await _request("GET", "/api/v1/sources/summary")


async def probe_source_health(source_id: int) -> Any:
    """Perform a live reachability/latency probe against one source."""
    return await _request("GET", f"/api/v1/sources/{source_id}/health")


async def list_scorecards(
    days: int | None = None,
    source_id: int | None = None,
    limit: int | None = None,
) -> Any:
    """List reliability scorecards (uptime, p95 latency, error-budget burn) for
    all active sources."""
    params: dict[str, Any] = {}
    if days is not None:
        params["days"] = days
    if source_id is not None:
        params["source_id"] = source_id
    if limit is not None:
        params["limit"] = limit
    return await _request("GET", "/api/v1/scorecards", params=params)


async def get_scorecard(source_id: int, days: int | None = None) -> Any:
    """Fetch the reliability scorecard for one source."""
    params: dict[str, Any] = {}
    if days is not None:
        params["days"] = days
    return await _request("GET", f"/api/v1/scorecards/{source_id}", params=params)


async def list_contract_snapshots(
    source_id: int, offset: int = 0, limit: int = 20
) -> Any:
    """List schema contract snapshots recorded for one source."""
    return await _request(
        "GET",
        f"/api/v1/contracts/sources/{source_id}/snapshots",
        params={"offset": offset, "limit": limit},
    )


async def list_drift_events(source_id: int, offset: int = 0, limit: int = 20) -> Any:
    """List detected contract drift events for one source."""
    return await _request(
        "GET",
        f"/api/v1/contracts/sources/{source_id}/drift-events",
        params={"offset": offset, "limit": limit},
    )


async def get_compatibility_report(source_id: int) -> Any:
    """Fetch the compatibility score and latest drift breakdown for one source."""
    return await _request("GET", f"/api/v1/contracts/sources/{source_id}/compatibility")


async def get_agent_run(run_id: int) -> Any:
    """Fetch the current status of one incident-triage agent run."""
    return await _request("GET", f"/api/v1/agent/runs/{run_id}")


async def resume_agent_run(run_id: int, approve: bool) -> Any:
    """Approve or reject a paused (awaiting_review) agent run.

    Reviewer identity is derived server-side from this account's JWT — never
    client-supplied (see Phase 4's `reviewer_user_id` spoof-proofing).
    """
    return await _request(
        "POST", f"/api/v1/agent/runs/{run_id}/resume", json={"approve": approve}
    )
