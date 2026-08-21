from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.models.base import TimestampMixin


class ProcessedEvent(Base, TimestampMixin):
    """Tracks consumed Kafka events with processing state and idempotency."""

    __tablename__ = "processed_events"
    __table_args__ = (
        Index("ix_events_idempotency_key", "idempotency_key", unique=True),
        Index("ix_events_status", "status"),
        Index("ix_events_kafka_offset", "kafka_offset"),
        Index("ix_events_dead_letter_queue", "dead_letter_queue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kafka_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    kafka_partition: Mapped[int] = mapped_column(Integer, nullable=False)
    kafka_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dead_letter_queue: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    dlq_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OutboxEvent(Base, TimestampMixin):
    """Transactional outbox event for reliable publish-after-commit workflows."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_published_at", "published_at"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_outbox_events_tenant_id", "tenant_id"),
        Index("ix_outbox_events_idempotency_key", "idempotency_key", unique=True),
        Index(
            "ix_outbox_events_publish_due",
            "published_at",
            "next_attempt_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)


class InboxConsumption(Base, TimestampMixin):
    """Inbox deduplication observation keyed by (consumer_name, message_id)."""

    __tablename__ = "inbox_consumptions"
    __table_args__ = (
        UniqueConstraint(
            "consumer_name",
            "message_id",
            name="uq_inbox_consumptions_consumer_message",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed', "
            "'completed_with_dead_letters', 'dead_letter')",
            name="ck_inbox_consumptions_status",
        ),
        Index("ix_inbox_consumptions_consumer_name", "consumer_name"),
        Index("ix_inbox_consumptions_processed_at", "processed_at"),
        Index(
            "ix_inbox_consumptions_claim",
            "status",
            "lease_expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="processing", nullable=False
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationDelivery(Base, TimestampMixin):
    """Durable per-channel delivery, retry, and terminal outcome state."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "channel",
            name="uq_notification_deliveries_message_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'retry_scheduled', "
            "'delivered', 'dead_letter')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 3",
            name="ck_notification_deliveries_attempt_count",
        ),
        Index(
            "ix_notification_deliveries_retry_due",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
        Index(
            "ix_notification_deliveries_tenant_created",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_notification_deliveries_source_created",
            "source_id",
            "created_at",
        ),
        Index("ix_notification_deliveries_incident_id", "incident_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inbox_consumption_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    incident_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
