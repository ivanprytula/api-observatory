"""Abuse detection logic: NoisySourceDetector and SuspiciousKeyDetector.

Both detectors follow the same pattern:
- Accept plain numeric metrics (no DB queries inside the detector itself)
- Return an ``AbuseSignalCreate`` if a threshold is breached, else ``None``
- Callers are responsible for persisting the signal via the repository
- All detectors are deterministic and synchronous for easy unit testing

Fail-open helpers (``record_*`` functions) wrap the detector + persistence
in a try/except so a DB failure never blocks the hot request path.
"""

from __future__ import annotations

import logging

from services.ingestor.api_schemas.abuse_detection import AbuseSignalCreate
from services.ingestor.constants import (
    ABUSE_ACTION_ALERTED,
    ABUSE_ACTION_LOGGED,
    ABUSE_ACTOR_API_KEY,
    ABUSE_ACTOR_SOURCE_ID,
    ABUSE_KEY_AUTH_FAILURE_THRESHOLD_HIGH,
    ABUSE_KEY_AUTH_FAILURE_THRESHOLD_MEDIUM,
    ABUSE_KEY_DISTINCT_IP_THRESHOLD_HIGH,
    ABUSE_KEY_DISTINCT_IP_THRESHOLD_MEDIUM,
    ABUSE_KEY_ERROR_RATE_THRESHOLD_HIGH,
    ABUSE_KEY_ERROR_RATE_THRESHOLD_MEDIUM,
    ABUSE_NOISY_SOURCE_DEFAULT_QUOTA,
    ABUSE_NOISY_SOURCE_MULTIPLIER_CRITICAL,
    ABUSE_NOISY_SOURCE_MULTIPLIER_HIGH,
    ABUSE_NOISY_SOURCE_MULTIPLIER_MEDIUM,
    ABUSE_RULE_AUTH_FAILURE_SPIKE,
    ABUSE_RULE_ERROR_RATE_SPIKE,
    ABUSE_RULE_MULTI_IP_KEY,
    ABUSE_RULE_QUOTA_EXCEEDED,
    ABUSE_SEVERITY_CRITICAL,
    ABUSE_SEVERITY_HIGH,
    ABUSE_SEVERITY_LOW,
    ABUSE_SEVERITY_MEDIUM,
    ABUSE_SIGNAL_NOISY_SOURCE,
    ABUSE_SIGNAL_SUSPICIOUS_KEY,
)
from services.ingestor.database import AsyncSessionLocal
from services.ingestor.repositories.abuse_detection import create_signal


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NoisySourceDetector
# ---------------------------------------------------------------------------


def evaluate_source_noise(
    *,
    source_name: str,
    request_count: int,
    window_seconds: int,
    quota_per_minute: int | None,
    tenant_id: int | None = None,
    ip_address: str | None = None,
) -> AbuseSignalCreate | None:
    """Evaluate whether a source is generating excessive traffic.

    Computes the expected request budget for the given window from
    ``quota_per_minute`` and compares against ``request_count``.

    Returns an ``AbuseSignalCreate`` if a threshold is breached, else ``None``.

    Args:
        source_name: Identifier matching SourceProfile.name.
        request_count: Observed number of requests in the measurement window.
        window_seconds: Length of the measurement window in seconds.
        quota_per_minute: Allowed requests per minute from SourceProfile (or None).
        tenant_id: Optional tenant context.
        ip_address: Optional originating IP.
    """
    effective_quota = (
        quota_per_minute
        if quota_per_minute is not None
        else ABUSE_NOISY_SOURCE_DEFAULT_QUOTA
    )  # noqa: E501

    # Expected requests for this window (pro-rated from per-minute quota)
    expected = effective_quota * (window_seconds / 60.0)
    if expected <= 0:
        return None

    ratio = request_count / expected

    if ratio >= ABUSE_NOISY_SOURCE_MULTIPLIER_CRITICAL:
        severity = ABUSE_SEVERITY_CRITICAL
        action = ABUSE_ACTION_ALERTED
    elif ratio >= ABUSE_NOISY_SOURCE_MULTIPLIER_HIGH:
        severity = ABUSE_SEVERITY_HIGH
        action = ABUSE_ACTION_ALERTED
    elif ratio >= ABUSE_NOISY_SOURCE_MULTIPLIER_MEDIUM:
        severity = ABUSE_SEVERITY_MEDIUM
        action = ABUSE_ACTION_LOGGED
    else:
        return None

    return AbuseSignalCreate(
        signal_type=ABUSE_SIGNAL_NOISY_SOURCE,
        actor_type=ABUSE_ACTOR_SOURCE_ID,
        actor_id=source_name,
        severity=severity,
        detection_rule=ABUSE_RULE_QUOTA_EXCEEDED,
        evidence={
            "request_count": request_count,
            "expected_for_window": round(expected, 2),
            "ratio": round(ratio, 3),
            "window_seconds": window_seconds,
            "quota_per_minute": effective_quota,
        },
        action_taken=action,
        tenant_id=tenant_id,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# SuspiciousKeyDetector
# ---------------------------------------------------------------------------


def evaluate_key_suspicion(
    *,
    key_prefix: str,
    window_seconds: int,
    auth_failure_count: int = 0,
    distinct_ip_count: int = 0,
    error_rate: float = 0.0,
    total_requests: int = 0,
    tenant_id: int | None = None,
) -> AbuseSignalCreate | None:
    """Evaluate whether an API key is showing suspicious usage patterns.

    Checks three independent signals in priority order (highest severity wins):
    1. Auth failure spike
    2. Multiple distinct source IPs (key sharing / rotation)
    3. High error rate

    Returns a single ``AbuseSignalCreate`` for the worst finding, or ``None``.

    Args:
        key_prefix: The ``key_prefix`` field of the ApiKey row (for identification).
        window_seconds: Measurement window length in seconds.
        auth_failure_count: Number of authentication failures in the window.
        distinct_ip_count: Number of distinct IPs that used this key in the window.
        error_rate: Fraction of requests that returned 4xx/5xx (0.0–1.0).
        total_requests: Total requests made with the key in the window.
        tenant_id: Optional tenant context.
    """
    # 1. Auth failure spike
    if auth_failure_count >= ABUSE_KEY_AUTH_FAILURE_THRESHOLD_HIGH:
        return AbuseSignalCreate(
            signal_type=ABUSE_SIGNAL_SUSPICIOUS_KEY,
            actor_type=ABUSE_ACTOR_API_KEY,
            actor_id=key_prefix,
            severity=ABUSE_SEVERITY_HIGH,
            detection_rule=ABUSE_RULE_AUTH_FAILURE_SPIKE,
            evidence={
                "auth_failure_count": auth_failure_count,
                "threshold": ABUSE_KEY_AUTH_FAILURE_THRESHOLD_HIGH,
                "window_seconds": window_seconds,
            },
            action_taken=ABUSE_ACTION_ALERTED,
            tenant_id=tenant_id,
        )
    if auth_failure_count >= ABUSE_KEY_AUTH_FAILURE_THRESHOLD_MEDIUM:
        return AbuseSignalCreate(
            signal_type=ABUSE_SIGNAL_SUSPICIOUS_KEY,
            actor_type=ABUSE_ACTOR_API_KEY,
            actor_id=key_prefix,
            severity=ABUSE_SEVERITY_MEDIUM,
            detection_rule=ABUSE_RULE_AUTH_FAILURE_SPIKE,
            evidence={
                "auth_failure_count": auth_failure_count,
                "threshold": ABUSE_KEY_AUTH_FAILURE_THRESHOLD_MEDIUM,
                "window_seconds": window_seconds,
            },
            action_taken=ABUSE_ACTION_LOGGED,
            tenant_id=tenant_id,
        )

    # 2. Multi-IP key rotation
    if distinct_ip_count >= ABUSE_KEY_DISTINCT_IP_THRESHOLD_HIGH:
        return AbuseSignalCreate(
            signal_type=ABUSE_SIGNAL_SUSPICIOUS_KEY,
            actor_type=ABUSE_ACTOR_API_KEY,
            actor_id=key_prefix,
            severity=ABUSE_SEVERITY_HIGH,
            detection_rule=ABUSE_RULE_MULTI_IP_KEY,
            evidence={
                "distinct_ip_count": distinct_ip_count,
                "threshold": ABUSE_KEY_DISTINCT_IP_THRESHOLD_HIGH,
                "window_seconds": window_seconds,
            },
            action_taken=ABUSE_ACTION_ALERTED,
            tenant_id=tenant_id,
        )
    if distinct_ip_count >= ABUSE_KEY_DISTINCT_IP_THRESHOLD_MEDIUM:
        return AbuseSignalCreate(
            signal_type=ABUSE_SIGNAL_SUSPICIOUS_KEY,
            actor_type=ABUSE_ACTOR_API_KEY,
            actor_id=key_prefix,
            severity=ABUSE_SEVERITY_MEDIUM,
            detection_rule=ABUSE_RULE_MULTI_IP_KEY,
            evidence={
                "distinct_ip_count": distinct_ip_count,
                "threshold": ABUSE_KEY_DISTINCT_IP_THRESHOLD_MEDIUM,
                "window_seconds": window_seconds,
            },
            action_taken=ABUSE_ACTION_LOGGED,
            tenant_id=tenant_id,
        )

    # 3. Error rate spike
    if total_requests > 0:
        if error_rate >= ABUSE_KEY_ERROR_RATE_THRESHOLD_HIGH:
            return AbuseSignalCreate(
                signal_type=ABUSE_SIGNAL_SUSPICIOUS_KEY,
                actor_type=ABUSE_ACTOR_API_KEY,
                actor_id=key_prefix,
                severity=ABUSE_SEVERITY_HIGH,
                detection_rule=ABUSE_RULE_ERROR_RATE_SPIKE,
                evidence={
                    "error_rate": round(error_rate, 4),
                    "threshold": ABUSE_KEY_ERROR_RATE_THRESHOLD_HIGH,
                    "total_requests": total_requests,
                    "window_seconds": window_seconds,
                },
                action_taken=ABUSE_ACTION_ALERTED,
                tenant_id=tenant_id,
            )
        if error_rate >= ABUSE_KEY_ERROR_RATE_THRESHOLD_MEDIUM:
            return AbuseSignalCreate(
                signal_type=ABUSE_SIGNAL_SUSPICIOUS_KEY,
                actor_type=ABUSE_ACTOR_API_KEY,
                actor_id=key_prefix,
                severity=ABUSE_SEVERITY_MEDIUM,
                detection_rule=ABUSE_RULE_ERROR_RATE_SPIKE,
                evidence={
                    "error_rate": round(error_rate, 4),
                    "threshold": ABUSE_KEY_ERROR_RATE_THRESHOLD_MEDIUM,
                    "total_requests": total_requests,
                    "window_seconds": window_seconds,
                },
                action_taken=ABUSE_ACTION_LOGGED,
                tenant_id=tenant_id,
            )

    return None


# ---------------------------------------------------------------------------
# Fail-open helpers (thin wrappers that persist and swallow DB errors)
# ---------------------------------------------------------------------------


async def record_source_noise(
    *,
    source_name: str,
    request_count: int,
    window_seconds: int,
    quota_per_minute: int | None,
    tenant_id: int | None = None,
    ip_address: str | None = None,
) -> bool:
    """Evaluate and persist a noisy-source signal if thresholds are breached.

    Fail-open: DB errors are logged as warnings and ``False`` is returned.

    Returns:
        True if a signal was created, False if thresholds were not met or
        an error occurred.
    """
    signal_payload = evaluate_source_noise(
        source_name=source_name,
        request_count=request_count,
        window_seconds=window_seconds,
        quota_per_minute=quota_per_minute,
        tenant_id=tenant_id,
        ip_address=ip_address,
    )
    if signal_payload is None:
        return False
    try:
        async with AsyncSessionLocal() as db:
            await create_signal(db, payload=signal_payload)
            await db.commit()
        logger.info(
            "abuse_signal_created",
            extra={
                "signal_type": signal_payload.signal_type,
                "actor_id": signal_payload.actor_id,
                "severity": signal_payload.severity,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "abuse_signal_persist_failed",
            extra={"signal_type": signal_payload.signal_type, "error": str(exc)},
        )
        return False


async def record_key_suspicion(
    *,
    key_prefix: str,
    window_seconds: int,
    auth_failure_count: int = 0,
    distinct_ip_count: int = 0,
    error_rate: float = 0.0,
    total_requests: int = 0,
    tenant_id: int | None = None,
) -> bool:
    """Evaluate and persist a suspicious-key signal if thresholds are breached.

    Fail-open: DB errors are logged as warnings and ``False`` is returned.

    Returns:
        True if a signal was created, False if thresholds were not met or
        an error occurred.
    """
    signal_payload = evaluate_key_suspicion(
        key_prefix=key_prefix,
        window_seconds=window_seconds,
        auth_failure_count=auth_failure_count,
        distinct_ip_count=distinct_ip_count,
        error_rate=error_rate,
        total_requests=total_requests,
        tenant_id=tenant_id,
    )
    if signal_payload is None:
        return False
    try:
        async with AsyncSessionLocal() as db:
            await create_signal(db, payload=signal_payload)
            await db.commit()
        logger.info(
            "abuse_signal_created",
            extra={
                "signal_type": signal_payload.signal_type,
                "actor_id": signal_payload.actor_id,
                "severity": signal_payload.severity,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "abuse_signal_persist_failed",
            extra={"signal_type": signal_payload.signal_type, "error": str(exc)},
        )
        return False


# ---------------------------------------------------------------------------
# Severity helpers (convenience for callers)
# ---------------------------------------------------------------------------

SEVERITY_RANK: dict[str, int] = {
    ABUSE_SEVERITY_LOW: 0,
    ABUSE_SEVERITY_MEDIUM: 1,
    ABUSE_SEVERITY_HIGH: 2,
    ABUSE_SEVERITY_CRITICAL: 3,
}


def is_high_or_above(severity: str) -> bool:
    """Return True when severity is high or critical."""
    return SEVERITY_RANK.get(severity, -1) >= SEVERITY_RANK[ABUSE_SEVERITY_HIGH]
