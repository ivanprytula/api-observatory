"""Subscription and delivery read models built from existing operational data."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.subscriptions import (
    AlertPolicy,
    ChannelConfig,
    DeliveryLog,
    EscalationPreview,
    EscalationStep,
    NotificationRule,
    SuppressionWindow,
)
from services.ingestor.config import settings
from services.ingestor.constants import (
    SUBSCRIPTION_DEFAULT_CHANNELS,
    SUBSCRIPTION_DEFAULT_ESCALATION_MINUTES,
    SUBSCRIPTION_DEFAULT_SUPPRESSION_MINUTES,
)
from services.ingestor.models import DriftEvent, SourceProfile


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _severity_rank(severity: str) -> int:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    return order.get(severity, 1)


def _default_policy_id(source_id: int | None) -> str | None:
    if source_id is None:
        return None
    return f"policy-source-{source_id}"


def _parse_default_channels() -> list[str]:
    raw = settings.notification_default_channels or ""
    return [channel.strip() for channel in raw.split(",") if channel.strip()]


def list_channel_configs() -> list[ChannelConfig]:
    """Return safe channel configuration summaries without exposing secrets."""
    default_channels = set(_parse_default_channels())
    raw_email_recipients = settings.notification_email_to or ""
    email_recipients = [
        item.strip() for item in raw_email_recipients.split(",") if item.strip()
    ]

    channel_rows = [
        (
            "webhook",
            bool(settings.notification_webhook_url),
            "webhook",
            "Webhook destination configured"
            if settings.notification_webhook_url
            else None,
        ),
        (
            "slack",
            bool(settings.notification_slack_webhook_url),
            "webhook",
            "Slack webhook configured"
            if settings.notification_slack_webhook_url
            else None,
        ),
        (
            "telegram",
            bool(
                settings.notification_telegram_bot_token
                and settings.notification_telegram_chat_id
            ),
            "chat",
            "Telegram chat configured"
            if settings.notification_telegram_bot_token
            and settings.notification_telegram_chat_id
            else None,
        ),
        (
            "email",
            bool(settings.notification_email_from and email_recipients),
            "email",
            f"{len(email_recipients)} recipient(s) configured"
            if email_recipients
            else None,
        ),
    ]

    return [
        ChannelConfig(
            channel=channel,
            enabled=channel in default_channels,
            configured=configured,
            delivery_mode=delivery_mode,
            target_summary=target_summary,
            metadata={"notifications_enabled": settings.notifications_enabled},
        )
        for channel, configured, delivery_mode, target_summary in channel_rows
    ]


async def list_alert_policies(
    db: AsyncSession,
    *,
    source_id: int | None,
    limit: int,
) -> list[AlertPolicy]:
    """Generate alert policies per active source profile.

    Current baseline is configuration-derived and deterministic.
    """
    stmt = (
        select(SourceProfile)
        .where(SourceProfile.deleted_at.is_(None))
        .order_by(SourceProfile.created_at.desc())
        .limit(limit)
    )
    if source_id is not None:
        stmt = stmt.where(SourceProfile.id == source_id)

    sources = list((await db.execute(stmt)).scalars().all())
    generated_at = _now_utc_naive()

    return [
        AlertPolicy(
            policy_id=f"policy-source-{source.id}",
            source_id=source.id,
            name=f"Default policy for {source.name}",
            enabled=bool(source.is_active),
            min_severity="medium",
            notification_rule=NotificationRule(
                channels=list(SUBSCRIPTION_DEFAULT_CHANNELS),
                min_severity="medium",
                escalation_minutes=SUBSCRIPTION_DEFAULT_ESCALATION_MINUTES,
            ),
            suppression_window=SuppressionWindow(
                minutes=SUBSCRIPTION_DEFAULT_SUPPRESSION_MINUTES,
                reason="Suppress repetitive non-critical drift noise",
            ),
            created_at=generated_at,
            metadata={
                "base_url": source.base_url,
                "probe_interval_seconds": source.probe_interval_seconds,
                "latency_threshold_ms": source.latency_threshold_ms,
            },
        )
        for source in sources
    ]


async def list_delivery_logs(
    db: AsyncSession,
    *,
    source_id: int | None,
    limit: int,
) -> list[DeliveryLog]:
    """Build delivery log view from recent drift events.

    This read model avoids write-path migration risk while giving users a
    useful historical feed to validate routing policy behavior.
    """
    stmt = select(DriftEvent).order_by(DriftEvent.created_at.desc()).limit(limit)
    if source_id is not None:
        stmt = stmt.where(DriftEvent.source_id == source_id)

    events = list((await db.execute(stmt)).scalars().all())

    logs: list[DeliveryLog] = []
    for event in events:
        severity_rank = _severity_rank(event.severity)
        if severity_rank >= _severity_rank("medium"):
            status = "delivered"
            channel = "webhook"
            detail = "Delivered by default subscription rule."
        else:
            status = "suppressed"
            channel = None
            detail = "Suppressed by default low-severity window."

        logs.append(
            DeliveryLog(
                delivery_id=f"delivery-drift-{event.id}",
                source_id=event.source_id,
                policy_id=f"policy-source-{event.source_id}",
                event_type=event.event_type,
                severity=event.severity,
                status=status,
                channel=channel,
                detail=detail,
                created_at=event.created_at,
                metadata={
                    "drift_event_id": event.id,
                    "compatibility_score": event.compatibility_score,
                },
            )
        )

    return logs


async def build_escalation_preview(
    db: AsyncSession,
    *,
    event: str,
    severity: str,
    source_id: int | None,
    channels: list[str] | None,
) -> EscalationPreview:
    """Build a deterministic escalation plan preview for a given event."""
    source: SourceProfile | None = None
    if source_id is not None:
        source = await db.scalar(
            select(SourceProfile).where(
                SourceProfile.id == source_id,
                SourceProfile.deleted_at.is_(None),
            )
        )

    selected_channels = channels or list(SUBSCRIPTION_DEFAULT_CHANNELS)
    effective_channels = [channel for channel in selected_channels if channel]
    severity_rank = _severity_rank(severity)

    steps: list[EscalationStep] = []
    for index, channel in enumerate(effective_channels, start=1):
        after_minutes = (
            0 if index == 1 else (index - 1) * SUBSCRIPTION_DEFAULT_ESCALATION_MINUTES
        )
        if severity_rank >= _severity_rank("critical") and index == 1:
            action = "Page immediately through the highest-priority configured channel."
        elif index == 1:
            action = "Deliver the initial alert notification."
        else:
            action = "Escalate because earlier channel did not produce acknowledgement."

        steps.append(
            EscalationStep(
                order=index,
                channel=channel,
                after_minutes=after_minutes,
                action=action,
                condition="Previous step remains unacknowledged.",
            )
        )

    source_name = source.name if source is not None else "global defaults"
    summary = (
        f"{len(steps)} escalation step(s) would run for {event} at severity {severity} "
        f"using {source_name}."
    )

    policy_id = _default_policy_id(source.id) if source is not None else None
    if source_id is None:
        policy_id = None

    return EscalationPreview(
        policy_id=policy_id,
        source_id=source_id,
        severity=severity,
        event=event,
        suppression_window=SuppressionWindow(
            minutes=SUBSCRIPTION_DEFAULT_SUPPRESSION_MINUTES,
            reason="Suppress repetitive non-critical drift noise",
        ),
        steps=steps,
        summary=summary,
    )
