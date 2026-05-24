"""TypedDict schemas for transformation pipeline configuration."""

from __future__ import annotations

from typing import Literal, TypedDict


class SyncConfig(TypedDict, total=False):
    """Per-source transformation pipeline configuration.

    Fields:
        strategy_type: Validation strategy (csv, json, api).
        enable_dedup: Whether to deduplicate by content hash.
        enrichment_rules: List of enrichment transformations to apply.
    """

    strategy_type: Literal["csv", "json", "api"]
    enable_dedup: bool
    enrichment_rules: list[str]
