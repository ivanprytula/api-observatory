"""Notification dispatching for operational alerts (Pillar 8 baseline)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from services.ingestor.config import settings
from services.ingestor.constants import (
    NOTIFICATION_SEVERITY_INFO,
    NOTIFICATION_SEVERITY_WARNING,
)


logger = logging.getLogger(__name__)

NotificationChannel = Literal["slack", "telegram", "webhook", "email"]


def _parse_channels(raw: str) -> list[NotificationChannel]:
    values = [v.strip().lower() for v in raw.split(",") if v.strip()]
    valid: set[str] = {"slack", "telegram", "webhook", "email"}
    channels: list[NotificationChannel] = []
    for value in values:
        if value in valid:
            channels.append(value)  # type: ignore[arg-type]
    return channels


def _default_channels() -> list[NotificationChannel]:
    return _parse_channels(settings.notification_default_channels)


def _email_recipients() -> list[str]:
    if not settings.notification_email_to:
        return []
    return [x.strip() for x in settings.notification_email_to.split(",") if x.strip()]


async def dispatch_notification_event(
    *,
    event: str,
    message: str,
    severity: str = NOTIFICATION_SEVERITY_WARNING,
    context: dict[str, Any] | None = None,
    channels: list[NotificationChannel] | None = None,
) -> dict[str, Any]:
    """Send one notification event to configured channels.

    Returns per-channel statuses and summary counts.
    """
    if not settings.notifications_enabled:
        return {
            "event": event,
            "severity": severity,
            "sent": 0,
            "failed": 0,
            "results": [],
            "detail": "notifications disabled",
        }

    selected = channels or _default_channels()
    results: list[dict[str, str]] = []

    for channel in selected:
        try:
            detail = await _dispatch_to_channel(
                channel=channel,
                event=event,
                message=message,
                severity=severity,
                context=context or {},
            )
            results.append(
                {
                    "channel": channel,
                    "status": "sent",
                    "detail": detail,
                }
            )
        except Exception as exc:
            logger.warning(
                "notification_dispatch_failed",
                extra={"channel": channel, "event": event, "error": str(exc)},
            )
            results.append(
                {
                    "channel": channel,
                    "status": "failed",
                    "detail": str(exc),
                }
            )

    sent = sum(1 for r in results if r["status"] == "sent")
    failed = sum(1 for r in results if r["status"] == "failed")
    return {
        "event": event,
        "severity": severity,
        "sent": sent,
        "failed": failed,
        "results": results,
    }


async def notify_background_task_failed(
    *,
    task_id: str,
    batch_size: int,
    error: str,
) -> dict[str, Any]:
    """Send an operational alert for failed background ingestion tasks."""
    return await dispatch_notification_event(
        event="background_task_failed",
        message=(
            "Background task failed"
            f" (task_id={task_id}, batch_size={batch_size}, error={error})"
        ),
        severity="critical",
        context={
            "task_id": task_id,
            "batch_size": batch_size,
            "error": error,
        },
    )


async def _dispatch_to_channel(
    *,
    channel: NotificationChannel,
    event: str,
    message: str,
    severity: str,
    context: dict[str, Any],
) -> str:
    if channel == "slack":
        return await _send_slack(event, message, severity, context)
    if channel == "telegram":
        return await _send_telegram(event, message, severity, context)
    if channel == "webhook":
        return await _send_webhook(event, message, severity, context)
    if channel == "email":
        return await _send_email(event, message, severity, context)
    raise ValueError(f"Unsupported channel: {channel}")


async def _send_slack(
    event: str,
    message: str,
    severity: str,
    context: dict[str, Any],
) -> str:
    if not settings.notification_slack_webhook_url:
        raise ValueError("notification_slack_webhook_url is not configured")

    color = (
        "danger"
        if severity == "critical"
        else "warning"
        if severity == NOTIFICATION_SEVERITY_WARNING
        else "good"
    )
    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"[{severity.upper()}] {event}",
                "text": message,
                "fields": [
                    {"title": k, "value": str(v), "short": True}
                    for k, v in context.items()
                ],
            }
        ]
    }
    async with httpx.AsyncClient(
        timeout=settings.notification_http_timeout_seconds
    ) as c:
        resp = await c.post(settings.notification_slack_webhook_url, json=payload)
        resp.raise_for_status()
    return "slack webhook delivered"


async def _send_telegram(
    event: str,
    message: str,
    severity: str,
    context: dict[str, Any],
) -> str:
    if (
        not settings.notification_telegram_bot_token
        or not settings.notification_telegram_chat_id
    ):
        raise ValueError(
            "notification_telegram_bot_token or notification_telegram_chat_id missing"
        )

    lines = [f"[{severity.upper()}] {event}", message]
    lines.extend([f"{k}: {v}" for k, v in context.items()])
    text = "\n".join(lines)

    url = (
        "https://api.telegram.org/bot"
        f"{settings.notification_telegram_bot_token}/sendMessage"
    )
    payload = {"chat_id": settings.notification_telegram_chat_id, "text": text}
    async with httpx.AsyncClient(
        timeout=settings.notification_http_timeout_seconds
    ) as c:
        resp = await c.post(url, json=payload)
        resp.raise_for_status()
    return "telegram message delivered"


async def _send_webhook(
    event: str,
    message: str,
    severity: str,
    context: dict[str, Any],
) -> str:
    if not settings.notification_webhook_url:
        raise ValueError("notification_webhook_url is not configured")

    payload = {
        "event": event,
        "severity": severity,
        "message": message,
        "context": context,
    }
    async with httpx.AsyncClient(
        timeout=settings.notification_http_timeout_seconds
    ) as c:
        resp = await c.post(settings.notification_webhook_url, json=payload)
        resp.raise_for_status()
    return "webhook delivered"


async def _send_email(
    event: str,
    message: str,
    severity: str,
    context: dict[str, Any],
) -> str:
    provider = settings.notification_email_provider.strip().lower()
    if provider != "resend":
        raise ValueError("Only resend provider is supported in this baseline")

    if not settings.notification_resend_api_key:
        raise ValueError("notification_resend_api_key is not configured")
    if not settings.notification_email_from:
        raise ValueError("notification_email_from is not configured")

    recipients = _email_recipients()
    if not recipients:
        raise ValueError("notification_email_to is not configured")

    subject = f"[{severity.upper()}] {event}"
    context_lines = "\n".join([f"- {k}: {v}" for k, v in context.items()])
    body = (
        f"{message}\n\n"
        f"Severity: {severity}\n"
        f"Event: {event}\n"
        f"\nContext:\n{context_lines}\n"
    )

    payload = {
        "from": settings.notification_email_from,
        "to": recipients,
        "subject": subject,
        "text": body,
    }
    headers = {
        "Authorization": f"Bearer {settings.notification_resend_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=settings.notification_http_timeout_seconds
    ) as c:
        resp = await c.post(
            "https://api.resend.com/emails", json=payload, headers=headers
        )
        resp.raise_for_status()
    return "resend email delivered"


async def notify_info(
    *, event: str, message: str, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Convenience helper for informational notifications."""
    return await dispatch_notification_event(
        event=event,
        message=message,
        severity=NOTIFICATION_SEVERITY_INFO,
        context=context,
    )
