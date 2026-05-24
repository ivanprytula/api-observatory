"""Tests for transformation pipeline (Strategy, Decorator, Factory patterns).

Tests verify:
- Each strategy validates correctly (Strategy pattern)
- Decorators compose correctly (Decorator pattern)
- Factory builds right pipeline from config (Factory pattern)
"""

from __future__ import annotations

import pytest

from services.ingestor.transformations.decorators import (
    DeduplicatorTransformer,
    EnricherTransformer,
    NullTransformer,
    ValidatorTransformer,
)
from services.ingestor.transformations.factory import TransformationPipelineFactory
from services.ingestor.transformations.strategies import (
    APIRecordValidator,
    CSVRecordValidator,
    JSONRecordValidator,
)
from services.ingestor.transformations.types import SyncConfig


class TestStrategyPattern:
    """Test validation strategies (Strategy pattern)."""

    @pytest.mark.asyncio
    async def test_csv_validator_valid_record(self) -> None:
        """CSV validator accepts valid record."""
        validator = CSVRecordValidator()
        record = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        is_valid, error = await validator.validate(record)
        assert is_valid
        assert error is None

    @pytest.mark.asyncio
    async def test_csv_validator_missing_field(self) -> None:
        """CSV validator rejects record with missing field."""
        validator = CSVRecordValidator()
        record = {
            "id": "123",
            "price": "99.99",
            # missing timestamp
        }
        is_valid, error = await validator.validate(record)
        assert not is_valid
        assert error is not None
        assert "Missing required field" in error

    @pytest.mark.asyncio
    async def test_csv_validator_invalid_price(self) -> None:
        """CSV validator rejects non-numeric price."""
        validator = CSVRecordValidator()
        record = {
            "id": "123",
            "price": "not-a-number",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        is_valid, error = await validator.validate(record)
        assert not is_valid
        assert error is not None
        assert "numeric" in error.lower()

    @pytest.mark.asyncio
    async def test_json_validator_valid_record(self) -> None:
        """JSON validator accepts dict with id."""
        validator = JSONRecordValidator()
        record = {"id": "xyz", "nested": {"field": "value"}}
        is_valid, error = await validator.validate(record)
        assert is_valid
        assert error is None

    @pytest.mark.asyncio
    async def test_json_validator_missing_id(self) -> None:
        """JSON validator rejects record without id."""
        validator = JSONRecordValidator()
        record = {"field": "value"}
        is_valid, error = await validator.validate(record)
        assert not is_valid
        assert error is not None
        assert "Missing required field" in error

    @pytest.mark.asyncio
    async def test_api_validator_accepts_any_dict(self) -> None:
        """API validator is permissive (only checks dict not empty)."""
        validator = APIRecordValidator()
        record = {"id": "123", "anything": "goes"}
        is_valid, error = await validator.validate(record)
        assert is_valid
        assert error is None


class TestDecoratorPattern:
    """Test transformer decorators (Decorator pattern)."""

    @pytest.mark.asyncio
    async def test_validator_transformer_valid(self) -> None:
        """ValidatorTransformer passes valid record to next."""
        strategy = CSVRecordValidator()
        null = NullTransformer()
        validator = ValidatorTransformer(null, strategy)

        record = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = await validator.transform(record)
        assert result is not None
        assert result["id"] == "123"

    @pytest.mark.asyncio
    async def test_validator_transformer_invalid(self) -> None:
        """ValidatorTransformer rejects invalid record."""
        strategy = CSVRecordValidator()
        null = NullTransformer()
        validator = ValidatorTransformer(null, strategy)

        record = {"id": "123"}  # missing required fields
        result = await validator.transform(record)
        assert result is None

    @pytest.mark.asyncio
    async def test_deduplicator_transformer_new_record(self) -> None:
        """DeduplicatorTransformer passes new record to next."""
        null = NullTransformer()
        dedup = DeduplicatorTransformer(null)

        record1 = {"id": "123", "value": "a"}
        result1 = await dedup.transform(record1)
        assert result1 is not None

    @pytest.mark.asyncio
    async def test_deduplicator_transformer_duplicate(self) -> None:
        """DeduplicatorTransformer rejects duplicate."""
        null = NullTransformer()
        dedup = DeduplicatorTransformer(null)

        record = {"id": "123", "value": "a"}
        result1 = await dedup.transform(record)
        assert result1 is not None

        # Same record again
        result2 = await dedup.transform(record)
        assert result2 is None  # Rejected as duplicate

    @pytest.mark.asyncio
    async def test_enricher_transformer_adds_fields(self) -> None:
        """EnricherTransformer adds computed fields."""
        null = NullTransformer()
        enricher = EnricherTransformer(null)

        record = {"id": "123", "value": "a"}
        result = await enricher.transform(record)

        assert result is not None
        assert "_ingested_at" in result
        assert "_source_hash" in result
        assert result["id"] == "123"  # Original field preserved

    @pytest.mark.asyncio
    async def test_decorator_chain_full(self) -> None:
        """Full decorator chain: validate → deduplicate → enrich."""
        # Build chain manually
        null = NullTransformer()
        enricher = EnricherTransformer(null)
        dedup = DeduplicatorTransformer(enricher)
        validator = ValidatorTransformer(dedup, CSVRecordValidator())

        # Valid record
        record = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = await validator.transform(record)

        # Should have passed through all layers
        assert result is not None
        assert "_ingested_at" in result
        assert "_source_hash" in result
        assert result["id"] == "123"


class TestFactoryPattern:
    """Test factory assembly (Factory pattern)."""

    @pytest.mark.asyncio
    async def test_factory_csv_strategy(self) -> None:
        """Factory builds CSV validator pipeline."""

        # Mock source object
        class MockSource:
            sync_config: SyncConfig = {
                "strategy_type": "csv",
                "enable_dedup": False,
                "enrichment_rules": [],
            }

        source = MockSource()
        pipeline = await TransformationPipelineFactory.create(source)

        # Pipeline should be able to validate
        valid_record = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = await pipeline.transform(valid_record)
        assert result is not None

    @pytest.mark.asyncio
    async def test_factory_json_strategy(self) -> None:
        """Factory builds JSON validator pipeline."""

        class MockSource:
            sync_config: SyncConfig = {
                "strategy_type": "json",
                "enable_dedup": False,
                "enrichment_rules": [],
            }

        source = MockSource()
        pipeline = await TransformationPipelineFactory.create(source)

        valid_record = {"id": "123", "nested": "value"}
        result = await pipeline.transform(valid_record)
        assert result is not None

    @pytest.mark.asyncio
    async def test_factory_with_dedup(self) -> None:
        """Factory builds pipeline with deduplicator."""

        class MockSource:
            sync_config: SyncConfig = {
                "strategy_type": "json",
                "enable_dedup": True,
                "enrichment_rules": [],
            }

        source = MockSource()
        pipeline = await TransformationPipelineFactory.create(source)

        record = {"id": "123"}
        result1 = await pipeline.transform(record)
        assert result1 is not None

        # Same record again should be rejected
        result2 = await pipeline.transform(record)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_factory_with_enrichment(self) -> None:
        """Factory builds pipeline with enricher."""

        class MockSource:
            sync_config: SyncConfig = {
                "strategy_type": "api",
                "enable_dedup": False,
                "enrichment_rules": ["_ingested_at"],
            }

        source = MockSource()
        pipeline = await TransformationPipelineFactory.create(source)

        record = {"id": "123"}
        result = await pipeline.transform(record)

        assert result is not None
        assert "_ingested_at" in result
        assert "_source_hash" in result

    @pytest.mark.asyncio
    async def test_factory_invalid_strategy(self) -> None:
        """Factory raises ValueError for unknown strategy."""
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            TransformationPipelineFactory._build_strategy("unknown")
