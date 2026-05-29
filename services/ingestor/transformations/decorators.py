"""Composable observation transformers (Decorator pattern).

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
    from .strategies import ObservationValidationStrategy


class ObservationTransformer(ABC):
    """Abstract interface for observation transformation.

    Each transformer can:
    1. Process the observation (validate, deduplicate, enrich)
    2. Optionally reject it (return None)
    3. Delegate to the next transformer in the chain
    """

    @abstractmethod
    async def transform(self, observation: dict) -> dict | None:
        """Transform a observation.

        Args:
            observation: The raw observation dict.

        Returns:
            Transformed observation dict, or None if rejected.
        """


class NullTransformer(ObservationTransformer):
    """Terminal transformer (identity, no-op).

    Used as the end of the chain. Simply returns the observation unchanged.
    """

    async def transform(self, observation: dict) -> dict | None:
        """Return observation unchanged."""
        return observation


class ValidatorTransformer(ObservationTransformer):
    """Validation layer (Decorator).

    Uses a ObservationValidationStrategy to validate the observation.
    If valid, delegates to next transformer.
    If invalid, returns None (rejects).
    """

    def __init__(
        self,
        next_transformer: ObservationTransformer,
        strategy: ObservationValidationStrategy,
    ):
        """Initialize with next transformer and validation strategy.

        Args:
            next_transformer: The transformer to delegate to if valid.
            strategy: The validation strategy to use.
        """
        self.next_transformer = next_transformer
        self.strategy = strategy

    async def transform(self, observation: dict) -> dict | None:
        """Validate observation, then delegate to next if valid."""
        is_valid, error = await self.strategy.validate(observation)
        if not is_valid:
            # Observation rejected; return None
            return None

        # Valid; pass to next transformer
        return await self.next_transformer.transform(observation)


class DeduplicatorTransformer(ObservationTransformer):
    """Deduplication layer (Decorator).

    Tracks content hash (MD5) of each observation. Rejects duplicates.
    First time seeing a observation: passes to next transformer.
    Duplicate: returns None (rejects).

    In production, the hash set would be in Redis for distributed dedup.
    For now, using in-memory set (per-request or per-sync scope).
    """

    def __init__(self, next_transformer: ObservationTransformer):
        """Initialize with next transformer.

        Args:
            next_transformer: The transformer to delegate to if not duplicate.
        """
        self.next_transformer = next_transformer
        # In-memory hash set (per deduplicator instance)
        # In production: Redis SADD / SISMEMBER for distributed dedup
        self._seen_hashes: set[str] = set()

    async def transform(self, observation: dict) -> dict | None:
        """Check hash; reject duplicate, pass new to next."""
        # Compute SHA256 hash of observation (treat as JSON-like for hashing)
        import json

        observation_json = json.dumps(observation, sort_keys=True, default=str)
        observation_hash = hashlib.sha256(observation_json.encode()).hexdigest()

        # Check if seen before
        if observation_hash in self._seen_hashes:
            # Duplicate; reject
            return None

        # New observation; mark as seen
        self._seen_hashes.add(observation_hash)

        # Delegate to next transformer and return result
        return await self.next_transformer.transform(observation)


class EnricherTransformer(ObservationTransformer):
    """Enrichment layer (Decorator).

    Adds computed fields to the observation:
    - _ingested_at: current timestamp (UTC)
    - _source_hash: SHA256 of entire observation (for tracking)
    """

    def __init__(self, next_transformer: ObservationTransformer):
        """Initialize with next transformer.

        Args:
            next_transformer: The transformer to delegate to (after enrichment).
        """
        self.next_transformer = next_transformer

    async def transform(self, observation: dict) -> dict | None:
        """Add computed fields, then delegate to next."""
        import json

        # Add ingestion timestamp
        observation["_ingested_at"] = datetime.now(tz=UTC).isoformat()

        # Add source hash (SHA256 of JSON representation)
        observation_json = json.dumps(observation, sort_keys=True, default=str)
        source_hash = hashlib.sha256(observation_json.encode()).hexdigest()
        observation["_source_hash"] = source_hash

        # Delegate to next transformer
        return await self.next_transformer.transform(observation)
