from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.utils import _utcnow
from services.ingestor.database import Base
from services.ingestor.models.base import TimestampMixin


class Observation(Base, TimestampMixin):
    __tablename__ = "observations"
    __table_args__ = (
        Index(
            "ix_observations_active_source",
            "source",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_observations_timestamp", "timestamp"),
        Index("ix_observations_processed", "processed"),
        UniqueConstraint(
            "source", "timestamp", name="uq_observations_source_timestamp"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Observation id={self.id} source={self.source!r}>"


class ObservationArchive(Base):
    """Warm-tier copy of an observation removed from the hot table."""

    __tablename__ = "observations_archive"
    __table_args__ = (
        Index("ix_observations_archive_timestamp", "timestamp"),
        Index("ix_observations_archive_archived_at", "archived_at"),
        Index("ix_observations_archive_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
