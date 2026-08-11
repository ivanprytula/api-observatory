from datetime import datetime

from sqlalchemy import (
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column

from services.ingestor.core.utils import _utcnow


class TimestampMixin:
    """Adds created_at, updated_at, and deleted_at to any model.

    - created_at: set once on INSERT, never changes
    - updated_at: set on INSERT and refreshed on every UPDATE
    - deleted_at: NULL until soft-deleted; non-NULL means logically deleted
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
