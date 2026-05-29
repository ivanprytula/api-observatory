"""Watermark tracking for incremental syncs.

Tracks the last successful sync timestamp per source,
enabling incremental re-fetches instead of full re-syncs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    class DataSource(Protocol):
        """Minimal protocol required by watermark management helpers."""

        _last_synced_at: datetime | None

else:
    AsyncSession = Any


class WatermarkManager:
    """Manages sync watermarks (last successful sync timestamps).

    Watermarks enable incremental syncs:
    - First sync: sync all observations (watermark = None)
    - Subsequent syncs: sync observations modified since watermark
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for ORM queries.
        """
        self.db = db

    async def get_watermark(self, source: DataSource) -> datetime | None:
        """Get last successful sync timestamp for a source.

        Args:
            source: The DataSource to check.

        Returns:
            Last sync timestamp (if exists), or None (first sync).
        """
        # Watermark is stored as _last_synced_at on the source model
        # Return None if never synced, datetime if synced before
        if hasattr(source, "_last_synced_at") and source._last_synced_at:
            return source._last_synced_at
        return None

    async def update_watermark(
        self, source: DataSource, sync_time: datetime | None = None
    ) -> None:
        """Update watermark to mark sync as successful.

        Args:
            source: The DataSource to update.
            sync_time: Timestamp to set (default: now).
        """
        if sync_time is None:
            sync_time = datetime.now(tz=UTC)

        source._last_synced_at = sync_time
        self.db.add(source)
        await self.db.commit()

    async def should_full_sync(self, source: DataSource) -> bool:
        """Determine if a full or incremental sync is needed.

        Args:
            source: The DataSource to check.

        Returns:
            True if never synced (full); False if has watermark (incremental).
        """
        watermark = await self.get_watermark(source)
        return watermark is None
