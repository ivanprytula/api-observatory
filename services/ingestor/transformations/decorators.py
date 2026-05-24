"""Composable record transformers (Decorator pattern).

Each transformer wraps a previous one, forming a chain:
- ValidatorTransformer → validates via strategy, rejects invalid, passes valid to next
- DeduplicatorTransformer → checks content hash, rejects duplicates, passes new to next
- EnricherTransformer → adds computed fields, passes enriched to next
- NullTransformer → terminal (identity, no-op)

Chain is built by factory based on source.sync_config.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .strategies import RecordValidationStrategy


class RecordTransformer(ABC):
    """Abstract interface for record transformation.

    Each transformer can:
    1. Process the record (validate, deduplicate, enrich)
    2. Optionally reject it (return None)
    3. Delegate to the next transformer in the chain
    """

    @abstractmethod
    async def transform(self, record: dict) -> dict | None:
        """Transform a record.

        Args:
            record: The raw record dict.

        Returns:
            Transformed record dict, or None if rejected.
        """


class NullTransformer(RecordTransformer):
    """Terminal transformer (identity, no-op).

    Used as the end of the chain. Simply returns the record unchanged.
    """

    async def transform(self, record: dict) -> dict | None:
        """Return record unchanged."""
        return record


class ValidatorTransformer(RecordTransformer):
    """Validation layer (Decorator).

    Uses a RecordValidationStrategy to validate the record.
    If valid, delegates to next transformer.
    If invalid, returns None (rejects).
    """

    def __init__(
        self, next_transformer: RecordTransformer, strategy: RecordValidationStrategy
    ):
        """Initialize with next transformer and validation strategy.

        Args:
            next_transformer: The transformer to delegate to if valid.
            strategy: The validation strategy to use.
        """
        self.next_transformer = next_transformer
        self.strategy = strategy

    async def transform(self, record: dict) -> dict | None:
        """Validate record, then delegate to next if valid."""
        is_valid, error = await self.strategy.validate(record)
        if not is_valid:
            # Record rejected; return None
            return None

        # Valid; pass to next transformer
        return await self.next_transformer.transform(record)


class DeduplicatorTransformer(RecordTransformer):
    """Deduplication layer (Decorator).

    Tracks content hash (MD5) of each record. Rejects duplicates.
    First time seeing a record: passes to next transformer.
    Duplicate: returns None (rejects).

    In production, the hash set would be in Redis for distributed dedup.
    For now, using in-memory set (per-request or per-sync scope).
    """

    def __init__(self, next_transformer: RecordTransformer):
        """Initialize with next transformer.

        Args:
            next_transformer: The transformer to delegate to if not duplicate.
        """
        self.next_transformer = next_transformer
        # In-memory hash set (per deduplicator instance)
        # In production: Redis SADD / SISMEMBER for distributed dedup
        self._seen_hashes: set[str] = set()

    async def transform(self, record: dict) -> dict | None:
        """Check hash; reject duplicate, pass new to next."""
        # Compute SHA256 hash of record (treat as JSON-like for hashing)
        import json

        record_json = json.dumps(record, sort_keys=True, default=str)
        record_hash = hashlib.sha256(record_json.encode()).hexdigest()

        # Check if seen before
        if record_hash in self._seen_hashes:
            # Duplicate; reject
            return None

        # New record; mark as seen
        self._seen_hashes.add(record_hash)

        # Delegate to next transformer and return result
        return await self.next_transformer.transform(record)


class EnricherTransformer(RecordTransformer):
    """Enrichment layer (Decorator).

    Adds computed fields to the record:
    - _ingested_at: current timestamp (UTC)
    - _source_hash: SHA256 of entire record (for tracking)
    """

    def __init__(self, next_transformer: RecordTransformer):
        """Initialize with next transformer.

        Args:
            next_transformer: The transformer to delegate to (after enrichment).
        """
        self.next_transformer = next_transformer

    async def transform(self, record: dict) -> dict | None:
        """Add computed fields, then delegate to next."""
        import json

        # Add ingestion timestamp
        record["_ingested_at"] = datetime.now(tz=UTC).isoformat()

        # Add source hash (SHA256 of JSON representation)
        record_json = json.dumps(record, sort_keys=True, default=str)
        source_hash = hashlib.sha256(record_json.encode()).hexdigest()
        record["_source_hash"] = source_hash

        # Delegate to next transformer
        return await self.next_transformer.transform(record)
