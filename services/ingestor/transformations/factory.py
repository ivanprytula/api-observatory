"""Transformation pipeline factory (Factory pattern).

Builds a transformation pipeline from source.sync_config.
Assembles the correct decorator chain based on:
- strategy_type: which validator to use
- enable_dedup: whether to include deduplicator
- enrichment_rules: which enrichers to include
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from .decorators import (
    DeduplicatorTransformer,
    EnricherTransformer,
    NullTransformer,
    ObservationTransformer,
    ValidatorTransformer,
)
from .strategies import (
    APIObservationValidator,
    CSVObservationValidator,
    JSONObservationValidator,
)
from .types import SyncConfig


if TYPE_CHECKING:

    class DataSource(Protocol):
        """Minimal source protocol for transformation pipeline construction."""

        sync_config: SyncConfig | None


class TransformationPipelineFactory:
    """Factory for building transformation pipelines.

    Reads source.sync_config and dynamically assembles the correct
    decorator chain.
    """

    @staticmethod
    async def create(source: DataSource) -> ObservationTransformer:
        """Build a transformation pipeline for a source.

        Args:
            source: The DataSource with sync_config specifying pipeline.

        Returns:
            A ObservationTransformer chain ready to transform observations.

        Raises:
            ValueError: If sync_config contains unknown strategy_type.
        """
        # Extract config (with defaults)
        sync_config = cast(
            SyncConfig,
            source.sync_config if source.sync_config is not None else {},
        )
        strategy_type = sync_config.get("strategy_type", "csv")
        enable_dedup = sync_config.get("enable_dedup", True)
        enrichment_rules = sync_config.get("enrichment_rules", [])

        # Start with terminal transformer
        transformer: ObservationTransformer = NullTransformer()

        # Build strategy-specific validator
        strategy = TransformationPipelineFactory._build_strategy(strategy_type)
        transformer = ValidatorTransformer(transformer, strategy)

        # Optionally add deduplicator
        if enable_dedup:
            transformer = DeduplicatorTransformer(transformer)

        # Optionally add enrichers
        if enrichment_rules:
            transformer = EnricherTransformer(transformer)

        return transformer

    @staticmethod
    def _build_strategy(strategy_type: str):
        """Build validation strategy from type string.

        Args:
            strategy_type: One of 'csv', 'json', 'api'.

        Returns:
            A ObservationValidationStrategy instance.

        Raises:
            ValueError: If strategy_type is unknown.
        """
        if strategy_type == "csv":
            return CSVObservationValidator()
        elif strategy_type == "json":
            return JSONObservationValidator()
        elif strategy_type == "api":
            return APIObservationValidator()
        else:
            raise ValueError(f"Unknown strategy_type: {strategy_type}")
