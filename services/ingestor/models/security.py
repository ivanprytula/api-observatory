from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.core.utils import _utcnow
from services.ingestor.models.base import TimestampMixin


class SecurityAuditEvent(Base):
    """Append-only security audit stream with tamper-evident hash chaining."""

    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_events_created_at", "created_at"),
        Index("ix_security_audit_events_event_type", "event_type"),
        Index("ix_security_audit_events_tenant_id", "tenant_id"),
        Index("ix_security_audit_events_actor_type", "actor_type"),
        Index("ix_security_audit_events_actor_id", "actor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    prev_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SecurityAuditEvent id={self.id} event_type={self.event_type!r} "
            f"decision={self.decision!r}>"
        )


class AbuseSignal(Base, TimestampMixin):
    """Mutable observation of a detected abuse pattern."""

    __tablename__ = "abuse_signals"
    __table_args__ = (
        Index("ix_abuse_signals_signal_type", "signal_type"),
        Index("ix_abuse_signals_actor", "actor_type", "actor_id"),
        Index("ix_abuse_signals_severity", "severity"),
        Index("ix_abuse_signals_tenant_id", "tenant_id"),
        Index("ix_abuse_signals_resolved_at", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    detection_rule: Mapped[str] = mapped_column(String(64), nullable=False)

    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    action_taken: Mapped[str] = mapped_column(
        String(32), nullable=False, default="logged"
    )

    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AbuseSignal id={self.id} signal_type={self.signal_type!r} "
            f"actor={self.actor_type}:{self.actor_id!r} severity={self.severity!r}>"
        )
