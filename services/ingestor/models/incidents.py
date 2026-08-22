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
from services.ingestor.core.utils import _utcnow
from services.ingestor.models.base import TimestampMixin


class DependencyIncident(Base, TimestampMixin):
    """Tenant-scoped lifecycle for an actionable dependency failure."""

    __tablename__ = "dependency_incidents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="ck_dependency_incidents_status",
        ),
        CheckConstraint(
            "trigger_type IN ('availability', 'latency', 'drift')",
            name="ck_dependency_incidents_trigger_type",
        ),
        Index("ix_dependency_incidents_tenant_status", "tenant_id", "status"),
        Index("ix_dependency_incidents_source_status", "source_id", "status"),
        Index("ix_dependency_incidents_last_seen_at", "last_seen_at"),
        Index("ix_dependency_incidents_active_key", "active_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    guidance: Mapped[str] = mapped_column(String(2048), nullable=False)
    trigger_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.id} source_id={self.source_id} "
            f"trigger_type={self.trigger_type!r} status={self.status!r}>"
        )
