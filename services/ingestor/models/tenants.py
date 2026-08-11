from sqlalchemy import Boolean, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.database import Base
from services.ingestor.models.base import TimestampMixin


class Tenant(Base, TimestampMixin):
    """Minimal tenant for multi-tenancy."""

    __tablename__ = "tenants"
    __table_args__ = (Index("ix_tenants_name", "name", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} name={self.name!r}>"


class User(Base, TimestampMixin):
    """Basic user model for authentication and RBAC role assignment."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_role", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


class UserTenant(Base, TimestampMixin):
    """Junction table for many-to-many user-to-tenant mapping."""

    __tablename__ = "user_tenants"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<UserTenant user_id={self.user_id} tenant_id={self.tenant_id}>"
