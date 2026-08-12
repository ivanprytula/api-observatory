from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from libs.contracts.events import NotificationChannel


class SuppressionWindow(BaseModel):
    """Defines a mute window for noisy alerts."""

    minutes: int = Field(..., ge=1, description="Suppression duration in minutes.")
    reason: str = Field(..., description="Reason for the suppression rule.")


class NotificationRule(BaseModel):
    """Delivery-channel rule tied to a policy."""

    channels: list[str] = Field(..., description="Delivery channels in priority order.")
    min_severity: str = Field(..., description="Minimum severity to trigger delivery.")
    escalation_minutes: int = Field(
        ..., ge=1, description="Escalation timeout in minutes."
    )


class AlertPolicy(BaseModel):
    """Policy used to decide if and how an alert should be delivered."""

    policy_id: str = Field(..., description="Stable identifier for this alert policy.")
    source_id: int | None = Field(
        None, description="Associated source profile ID when scoped to one source."
    )
    name: str = Field(..., description="Human-friendly policy name.")
    enabled: bool = Field(..., description="Whether this policy is active.")
    min_severity: str = Field(
        ..., description="Lowest severity that can trigger the policy."
    )
    notification_rule: NotificationRule = Field(
        ..., description="Channel routing rule used for initial delivery."
    )
    suppression_window: SuppressionWindow = Field(
        ..., description="Suppression window applied to repetitive alerts."
    )
    created_at: datetime = Field(
        ..., description="UTC timestamp when policy was created."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryLog(BaseModel):
    """Delivery status item for one alert event dispatch."""

    delivery_id: str = Field(
        ..., description="Stable identifier for this delivery observation."
    )
    source_id: int | None = Field(
        None, description="Associated source profile ID when applicable."
    )
    policy_id: str | None = Field(
        None, description="Alert policy responsible for this delivery decision."
    )
    event_type: str = Field(..., description="Event type that triggered delivery.")
    severity: str = Field(..., description="Severity level of the triggering event.")
    status: str = Field(
        ..., description="Delivery outcome, such as delivered or suppressed."
    )
    channel: str | None = Field(
        None, description="Channel used for delivery when one was selected."
    )
    detail: str | None = Field(
        None, description="Operational detail explaining the delivery outcome."
    )
    created_at: datetime = Field(
        ..., description="UTC timestamp for the delivery observation."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelConfig(BaseModel):
    """Configuration view for one notification channel."""

    channel: str = Field(..., description="Notification channel name.")
    enabled: bool = Field(..., description="Whether the channel is enabled by default.")
    configured: bool = Field(
        ..., description="Whether the channel has enough configuration to send alerts."
    )
    delivery_mode: str = Field(
        ..., description="High-level delivery mechanism, for example webhook or email."
    )
    target_summary: str | None = Field(
        None,
        description="Safe human-readable summary of the configured destination.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional machine-readable configuration details.",
    )


class EscalationStep(BaseModel):
    """One step in an escalation plan preview."""

    order: int = Field(..., ge=1, description="Execution order of the escalation step.")
    channel: str = Field(..., description="Channel selected for this escalation step.")
    after_minutes: int = Field(
        ..., ge=0, description="Minutes after initial trigger before this step starts."
    )
    action: str = Field(..., description="Action performed at this escalation step.")
    condition: str = Field(
        ..., description="Condition that keeps this escalation step active."
    )


class EscalationPreview(BaseModel):
    """Computed escalation plan for an alert payload."""

    policy_id: str | None = Field(
        None, description="Alert policy used to compute the escalation preview."
    )
    source_id: int | None = Field(
        None,
        description="Associated source profile ID when the preview is source-specific.",
    )
    severity: str = Field(
        ..., description="Severity level used for escalation decisions."
    )
    event: str = Field(..., description="Event type used to generate the preview.")
    suppression_window: SuppressionWindow = Field(
        ..., description="Suppression rule that applies before repeated escalations."
    )
    steps: list[EscalationStep] = Field(
        ..., description="Ordered escalation steps that would be attempted."
    )
    summary: str = Field(
        ..., description="Human-readable explanation of the escalation plan."
    )


class ChannelConfigListResponse(BaseModel):
    """Paginated channel configuration response."""

    items: list[ChannelConfig] = Field(..., description="Channel configuration items.")
    total: int = Field(
        ..., ge=0, description="Total number of returned channel configs."
    )


class EscalationPreviewRequest(BaseModel):
    """Request body for escalation preview generation."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event": "drift_detected",
                    "severity": "critical",
                    "source_id": 1,
                    "channels": ["webhook", "slack", "email"],
                }
            ]
        }
    }

    event: str = Field(..., description="Event type used for escalation simulation.")
    severity: str = Field(
        ..., description="Severity level used for escalation simulation."
    )
    source_id: int | None = Field(
        default=None,
        ge=1,
        description="Optional source profile used to scope policy selection.",
    )
    channels: list[str] | None = Field(
        default=None,
        description="Optional channel override in escalation order.",
    )


class AlertPolicyListResponse(BaseModel):
    """Paginated alert policy response."""

    items: list[AlertPolicy] = Field(..., description="Alert policy items.")
    total: int = Field(..., ge=0, description="Total number of returned policies.")


class DeliveryLogListResponse(BaseModel):
    """Paginated delivery log response."""

    items: list[DeliveryLog] = Field(..., description="Delivery log items.")
    total: int = Field(..., ge=0, description="Total number of returned delivery logs.")


class TestDeliveryRequest(BaseModel):
    """Request body for test delivery dispatch."""

    event: str = Field(default="subscription_test_event")
    message: str = Field(default="Test notification from subscription delivery API.")
    severity: str = Field(default="warning")
    source_id: int | None = Field(default=None, ge=1)
    channels: list[NotificationChannel] | None = Field(default=None)
