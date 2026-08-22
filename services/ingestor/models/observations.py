from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.models.base import TimestampMixin


class Observation(Base, TimestampMixin):
    __tablename__ = "observations"
    __table_args__ = (
        Index(
            "ix_observations_active_source",
            "source_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_observations_timestamp", "timestamp"),
        Index("ix_observations_processed", "processed"),
        UniqueConstraint(
            "source_id", "timestamp", name="uq_observations_source_timestamp"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} source_id={self.source_id}>"
