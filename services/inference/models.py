"""ORM model for the inference service's document/embedding store."""

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.inference.config import settings
from services.inference.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class IndexedDocument(Base):
    """One embedded, searchable document within a named collection.

    `external_id` is opaque to this service — it's whatever the caller uses
    to identify the source record (e.g. `Observation.id` in the ingestor).
    This service never reads another service's tables directly; the only
    contract is the `/index` and `/search` HTTP interface.
    """

    __tablename__ = "indexed_documents"
    __table_args__ = (
        UniqueConstraint(
            "collection",
            "external_id",
            name="uq_indexed_documents_collection_external_id",
        ),
        Index("ix_indexed_documents_collection", "collection"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dim), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<IndexedDocument id={self.id} collection={self.collection!r} "
            f"external_id={self.external_id}>"
        )
