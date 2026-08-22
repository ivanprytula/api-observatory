from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.models.base import TimestampMixin


class SecurityEvent(Base, TimestampMixin):
    """Unified security event stream covering abuse signals and audit events.

    The ``category`` column discriminates between the two former tables:
    - ``abuse``: mutable abuse workflow entries (resolved_at, resolved_by)
    - ``audit``: append-only tamper-evident audit trail (event_hash chain)
    """

    __tablename__ = "security_events"
    __table_args__ = (
        CheckConstraint(
            "category IN ('abuse', 'audit')",
            name="ck_security_events_category",
        ),
        Index("ix_security_events_created_at", "created_at"),
        Index("ix_security_events_event_type", "event_type"),
        Index("ix_security_events_tenant_id", "tenant_id"),
        Index("ix_security_events_actor_type", "actor_type"),
        Index("ix_security_events_actor_id", "actor_id"),
        Index("ix_security_events_signal_type", "signal_type"),
        Index("ix_security_events_resolved_at", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    category: Mapped[str] = mapped_column(String(32), nullable=False)

    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )

    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prev_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    signal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detection_rule: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(128), nullable=True)

    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.id} category={self.category!r} "
            f"event_type={self.event_type!r}>"
        )
