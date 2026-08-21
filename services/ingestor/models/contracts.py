from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.core.utils import _utcnow
from services.ingestor.models.base import TimestampMixin


class ContractSnapshot(Base, TimestampMixin):
    """Schema snapshot for a source payload contract at a point in time."""

    __tablename__ = "contract_snapshots"
    __table_args__ = (
        Index("ix_contract_snapshots_source_id", "source_id"),
        Index("ix_contract_snapshots_fingerprint", "schema_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    compatibility_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=100.0
    )
    snapshot_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ContractSnapshot id={self.id} source_id={self.source_id} "
            f"fingerprint={self.schema_fingerprint[:8]}...>"
        )


class ContractBaseline(Base, TimestampMixin):
    """Versioned accepted contract baseline and its current candidate state."""

    __tablename__ = "contract_baselines"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "version",
            name="uq_contract_baselines_source_version",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_contract_baselines_status",
        ),
        Index("ix_contract_baselines_source_status", "source_id", "status"),
        Index("ix_contract_baselines_tenant_status", "tenant_id", "status"),
        Index("ix_contract_baselines_baseline_snapshot", "baseline_snapshot_id"),
        Index("ix_contract_baselines_active_key", "active_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    promoted_from_baseline_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    accepted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    acceptance_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    candidate_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_schema_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    candidate_observation_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    candidate_drift_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    candidate_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<ContractBaseline id={self.id} source_id={self.source_id} "
            f"version={self.version} status={self.status!r}>"
        )


class DriftEvent(Base, TimestampMixin):
    """Confirmed schema drift from an accepted baseline to a candidate snapshot."""

    __tablename__ = "drift_events"
    __table_args__ = (
        Index("ix_drift_events_source_id", "source_id"),
        Index("ix_drift_events_event_type", "event_type"),
        Index("ix_drift_events_severity", "severity"),
        Index("ix_drift_events_current_snapshot_id", "current_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_snapshot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    added_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    removed_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    type_changed_fields: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    compatibility_score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DriftEvent id={self.id} source_id={self.source_id} "
            f"event_type={self.event_type!r} severity={self.severity!r}>"
        )
