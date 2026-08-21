from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.models.base import TimestampMixin


class SourceProfile(Base, TimestampMixin):
    """Registry entry for an external API / data source being ingested."""

    __tablename__ = "source_profiles"
    __table_args__ = (
        Index("ix_source_profiles_name", "name", unique=True),
        Index(
            "ix_source_profiles_active",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
        Index("ix_source_profiles_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    health_check_path: Mapped[str] = mapped_column(
        String(255), default="/health", nullable=False
    )
    probe_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_threshold_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    incident_failure_threshold: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False
    )
    incident_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, default=900, nullable=False
    )

    def __repr__(self) -> str:
        return f"<SourceProfile id={self.id} name={self.name!r}>"


class ProviderHealthSample(Base, TimestampMixin):
    """Single health probe result for an API provider / source."""

    __tablename__ = "provider_health_samples"
    __table_args__ = (
        Index("ix_phs_source_id", "source_id"),
        Index("ix_phs_sampled_at", "sampled_at"),
        Index("ix_phs_source_sampled", "source_id", "sampled_at"),
        Index("ix_phs_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ProviderHealthSample id={self.id} source_id={self.source_id} "
            f"sampled_at={self.sampled_at!r} success={self.is_success}>"
        )
