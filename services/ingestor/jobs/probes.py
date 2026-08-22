import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.platform.circuit_breaker import CircuitBreaker, CircuitOpenError
from services.ingestor.api_schemas.scorecards import HealthSampleCreate
from services.ingestor.constants import SOURCE_HEALTH_TIMEOUT_SECONDS
from services.ingestor.core.auth_headers import build_auth_headers
from services.ingestor.fetch import get_http_client
from services.ingestor.incident_lifecycle import record_health_sample
from services.ingestor.models import SourceProfile
from services.ingestor.repositories.source_registry import validate_source_base_url


logger = logging.getLogger(__name__)

_source_probe_breakers: dict[int, CircuitBreaker] = {}


def _get_source_probe_breaker(source_id: int) -> CircuitBreaker:
    breaker = _source_probe_breakers.get(source_id)
    if breaker is None:
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        _source_probe_breakers[source_id] = breaker
    return breaker


async def run_source_probe(db: AsyncSession, source_id: int) -> dict[str, Any]:
    """Probe one active source and persist a provider health sample."""
    stmt = select(SourceProfile).where(
        SourceProfile.id == source_id,
        SourceProfile.deleted_at.is_(None),
        SourceProfile.is_active.is_(True),
    )
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if profile is None:
        return {"source_id": source_id, "skipped": True, "reason": "source_inactive"}

    target_url = (
        f"{profile.base_url.rstrip('/')}/{profile.health_check_path.lstrip('/')}"
    )
    breaker = _get_source_probe_breaker(source_id)

    if breaker.is_open:
        logger.warning(
            "source_probe_skipped_circuit_open",
            extra={"source_id": source_id, "target_url": target_url},
        )
        return {"source_id": source_id, "skipped": True, "reason": "circuit_open"}

    # Re-validate the target URL immediately before the outbound request.
    # This defeats DNS-rebinding: the IP allow-list is checked again at
    # request time, not just at registration.
    try:
        await validate_source_base_url(target_url)
    except ValueError as exc:
        error_message = f"SSRF validation failed: {exc}"
        logger.warning(
            "source_probe_ssrf_blocked",
            extra={
                "source_id": source_id,
                "target_url": target_url,
                "error": error_message,
            },
        )
        await record_health_sample(
            db,
            HealthSampleCreate(
                source_id=source_id,
                sampled_at=datetime.now(UTC),
                latency_ms=0.0,
                is_success=False,
                http_status=None,
                response_body_hash=None,
                error_message=error_message,
                region=None,
                tenant_id=profile.tenant_id,
            ),
        )
        return {
            "source_id": source_id,
            "target_url": target_url,
            "status_code": None,
            "latency_ms": 0.0,
            "response_body_hash": None,
            "is_success": False,
            "error": error_message,
        }

    start = time.monotonic()
    sampled_at = datetime.now(UTC)

    async def _do_probe_head() -> httpx.Response:
        client = await get_http_client()
        headers = build_auth_headers(
            profile.auth_type,
            profile.api_key,
            profile.auth_header_name,
            profile.auth_username,
        )
        return await client.head(
            target_url, headers=headers, timeout=SOURCE_HEALTH_TIMEOUT_SECONDS
        )

    status_code: int | None = None
    error_message: str | None = None
    is_success = False

    try:
        response = await breaker.call(_do_probe_head)
        status_code = response.status_code
        is_success = 200 <= response.status_code < 400
        if not is_success:
            error_message = f"upstream_status_{response.status_code}"
    except CircuitOpenError:
        logger.warning(
            "source_probe_skipped_circuit_open",
            extra={"source_id": source_id, "target_url": target_url},
        )
        return {"source_id": source_id, "skipped": True, "reason": "circuit_open"}
    except Exception as exc:
        error_message = str(exc)

    elapsed_ms = round((time.monotonic() - start) * 1000, 2)

    await record_health_sample(
        db,
        HealthSampleCreate(
            source_id=source_id,
            sampled_at=sampled_at,
            latency_ms=elapsed_ms,
            is_success=is_success,
            http_status=status_code,
            response_body_hash=None,
            error_message=error_message,
            region=None,
            tenant_id=profile.tenant_id,
        ),
    )

    return {
        "source_id": source_id,
        "target_url": target_url,
        "status_code": status_code,
        "latency_ms": elapsed_ms,
        "response_body_hash": None,
        "is_success": is_success,
    }


async def run_source_contract_snapshot(
    db: AsyncSession, source_id: int
) -> dict[str, Any]:
    """Fetch a sample response from a source and ingest it as a contract snapshot."""
    stmt = select(SourceProfile).where(
        SourceProfile.id == source_id,
        SourceProfile.deleted_at.is_(None),
        SourceProfile.is_active.is_(True),
    )
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if profile is None:
        return {"source_id": source_id, "skipped": True, "reason": "source_inactive"}

    target_url = (
        f"{profile.base_url.rstrip('/')}/{profile.health_check_path.lstrip('/')}"
    )
    breaker = _get_source_probe_breaker(source_id)

    if breaker.is_open:
        return {"source_id": source_id, "skipped": True, "reason": "circuit_open"}

    # Re-validate the target URL immediately before the outbound request.
    # This defeats DNS-rebinding: the IP allow-list is checked again at
    # request time, not just at registration.
    try:
        await validate_source_base_url(target_url)
    except ValueError as exc:
        logger.warning(
            "source_contract_snapshot_ssrf_blocked",
            extra={"source_id": source_id, "target_url": target_url, "error": str(exc)},
        )
        return {"source_id": source_id, "skipped": True, "reason": "ssrf_blocked"}

    try:
        client = await get_http_client()
        headers = build_auth_headers(
            profile.auth_type,
            profile.api_key,
            profile.auth_header_name,
            profile.auth_username,
        )
        response = await breaker.call(
            lambda: client.get(
                target_url, headers=headers, timeout=SOURCE_HEALTH_TIMEOUT_SECONDS
            )
        )
        response.raise_for_status()
        payload = response.json()
    except (CircuitOpenError, httpx.HTTPError, ValueError):
        return {"source_id": source_id, "skipped": True, "reason": "fetch_failed"}

    if not isinstance(payload, dict):
        return {"source_id": source_id, "skipped": True, "reason": "non_dict_response"}

    from services.ingestor.api_schemas.contract_drift import ContractSnapshotCreate
    from services.ingestor.repositories.contract_drift import create_contract_snapshot

    snapshot, drift_event = await create_contract_snapshot(
        db,
        ContractSnapshotCreate(source_id=source_id, payload_schema=payload),
    )

    return {
        "source_id": source_id,
        "snapshot_id": snapshot.id if snapshot else None,
        "drift_detected": drift_event is not None,
        "drift_event_id": drift_event.id if drift_event else None,
    }
