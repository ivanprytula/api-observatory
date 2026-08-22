from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.database import Base
from services.ingestor.models.base import TimestampMixin


class Tenant(Base, TimestampMixin):
    """Minimal tenant for multi-tenancy."""

    __tablename__ = "tenants"
    __table_args__ = (Index("ix_tenants_name", "name", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} name={self.name!r}>"


class User(Base, TimestampMixin):
    """Basic user model for authentication."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
        Index("ix_users_email", "email", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} username={self.username!r}>"


class UserTenant(Base, TimestampMixin):
    """Junction table for many-to-many user-to-tenant mapping."""

    __tablename__ = "user_tenants"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} user_id={self.user_id} tenant_id={self.tenant_id}>"


class TenantConfig(Base, TimestampMixin):
    """Per-tenant operational settings."""

    __tablename__ = "tenant_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_configs_tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    retention_days: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_alert_threshold_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    max_incident_occurrences: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_flags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.id} tenant_id={self.tenant_id} "
            f"retention_days={self.retention_days!r}>"
        )
