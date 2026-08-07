"""Tests for transformation pipeline (Strategy, Decorator, Factory patterns).

Tests verify:
- Each strategy validates correctly (Strategy pattern)
- Decorators compose correctly (Decorator pattern)
- Factory builds right pipeline from config (Factory pattern)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.ingestor.transformations.decorators import (
    DeduplicatorTransformer,
    EnricherTransformer,
    NullTransformer,
    ValidatorTransformer,
)
from services.ingestor.transformations.factory import TransformationPipelineFactory
from services.ingestor.transformations.strategies import (
    APIObservationValidator,
    CSVObservationValidator,
    JSONObservationValidator,
)
from services.ingestor.transformations.types import SyncConfig


pytestmark = pytest.mark.unit


class TestStrategyPattern:
    """Test validation strategies (Strategy pattern)."""

    @pytest.mark.asyncio
    async def test_csv_validator_valid_observation(self) -> None:
        """CSV validator accepts valid observation."""
        validator = CSVObservationValidator()
        observation = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        is_valid, error = await validator.validate(observation)
        assert is_valid
        assert error is None

    @pytest.mark.asyncio
    async def test_csv_validator_missing_field(self) -> None:
        """CSV validator rejects observation with missing field."""
        validator = CSVObservationValidator()
        observation = {
            "id": "123",
            "price": "99.99",
            # missing timestamp
        }
        is_valid, error = await validator.validate(observation)
        assert not is_valid
        assert error is not None
        assert "Missing required field" in error

    @pytest.mark.asyncio
    async def test_csv_validator_invalid_price(self) -> None:
        """CSV validator rejects non-numeric price."""
        validator = CSVObservationValidator()
        observation = {
            "id": "123",
            "price": "not-a-number",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        is_valid, error = await validator.validate(observation)
        assert not is_valid
        assert error is not None
        assert "numeric" in error.lower()

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("id", "", "Invalid 'id'"),
            ("price", -1, "Price must be >= 0"),
            ("timestamp", "not-a-date", "Invalid timestamp format"),
        ],
    )
    async def test_csv_validator_rejects_invalid_required_values(
        self,
        field: str,
        value: object,
        message: str,
    ) -> None:
        observation = {
            "id": "123",
            "price": 99.99,
            "timestamp": "2024-01-15T10:00:00Z",
        }
        observation[field] = value

        is_valid, error = await CSVObservationValidator().validate(observation)

        assert is_valid is False
        assert error is not None
        assert message in error

    async def test_csv_validator_rejects_future_timestamp(self) -> None:
        observation = {
            "id": "123",
            "price": 99.99,
            "timestamp": datetime.now(UTC) + timedelta(days=1),
        }

        is_valid, error = await CSVObservationValidator().validate(observation)

        assert is_valid is False
        assert error == "Timestamp cannot be in future"

    @pytest.mark.asyncio
    async def test_json_validator_valid_observation(self) -> None:
        """JSON validator accepts dict with id."""
        validator = JSONObservationValidator()
        observation = {"id": "xyz", "nested": {"field": "value"}}
        is_valid, error = await validator.validate(observation)
        assert is_valid
        assert error is None

    @pytest.mark.asyncio
    async def test_json_validator_missing_id(self) -> None:
        """JSON validator rejects observation without id."""
        validator = JSONObservationValidator()
        observation = {"field": "value"}
        is_valid, error = await validator.validate(observation)
        assert not is_valid
        assert error is not None
        assert "Missing required field" in error

    @pytest.mark.parametrize(
        "observation",
        [[], {}, {"id": None}],
    )
    async def test_json_validator_rejects_invalid_shapes(
        self, observation: object
    ) -> None:
        is_valid, error = await JSONObservationValidator().validate(observation)  # type: ignore[arg-type]

        assert is_valid is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_api_validator_accepts_any_dict(self) -> None:
        """API validator is permissive (only checks dict not empty)."""
        validator = APIObservationValidator()
        observation = {"id": "123", "anything": "goes"}
        is_valid, error = await validator.validate(observation)
        assert is_valid
        assert error is None

    @pytest.mark.parametrize("observation", [[], {}])
    async def test_api_validator_rejects_non_object_or_empty(
        self, observation: object
    ) -> None:
        is_valid, error = await APIObservationValidator().validate(observation)  # type: ignore[arg-type]

        assert is_valid is False
        assert error is not None


class TestDecoratorPattern:
    """Test transformer decorators (Decorator pattern)."""

    @pytest.mark.asyncio
    async def test_validator_transformer_valid(self) -> None:
        """ValidatorTransformer passes valid observation to next."""
        strategy = CSVObservationValidator()
        null = NullTransformer()
        validator = ValidatorTransformer(null, strategy)

        observation = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = await validator.transform(observation)
        assert result is not None
        assert result["id"] == "123"

    @pytest.mark.asyncio
    async def test_validator_transformer_invalid(self) -> None:
        """ValidatorTransformer rejects invalid observation."""
        strategy = CSVObservationValidator()
        null = NullTransformer()
        validator = ValidatorTransformer(null, strategy)

        observation = {"id": "123"}  # missing required fields
        result = await validator.transform(observation)
        assert result is None

    @pytest.mark.asyncio
    async def test_deduplicator_transformer_new_observation(self) -> None:
        """DeduplicatorTransformer passes new observation to next."""
        null = NullTransformer()
        dedup = DeduplicatorTransformer(null)

        observation1 = {"id": "123", "value": "a"}
        result1 = await dedup.transform(observation1)
        assert result1 is not None

    @pytest.mark.asyncio
    async def test_deduplicator_transformer_duplicate(self) -> None:
        """DeduplicatorTransformer rejects duplicate."""
        null = NullTransformer()
        dedup = DeduplicatorTransformer(null)

        observation = {"id": "123", "value": "a"}
        result1 = await dedup.transform(observation)
        assert result1 is not None

        # Same observation again
        result2 = await dedup.transform(observation)
        assert result2 is None  # Rejected as duplicate

    @pytest.mark.asyncio
    async def test_enricher_transformer_adds_fields(self) -> None:
        """EnricherTransformer adds computed fields."""
        null = NullTransformer()
        enricher = EnricherTransformer(null)

        observation = {"id": "123", "value": "a"}
        result = await enricher.transform(observation)

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
        validator = ValidatorTransformer(dedup, CSVObservationValidator())

        # Valid observation
        observation = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = await validator.transform(observation)

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
        valid_observation = {
            "id": "123",
            "price": "99.99",
            "timestamp": "2024-01-15T10:00:00Z",
        }
        result = await pipeline.transform(valid_observation)
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

        valid_observation = {"id": "123", "nested": "value"}
        result = await pipeline.transform(valid_observation)
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

        observation = {"id": "123"}
        result1 = await pipeline.transform(observation)
        assert result1 is not None

        # Same observation again should be rejected
        result2 = await pipeline.transform(observation)
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

        observation = {"id": "123"}
        result = await pipeline.transform(observation)

        assert result is not None
        assert "_ingested_at" in result
        assert "_source_hash" in result

    @pytest.mark.asyncio
    async def test_factory_invalid_strategy(self) -> None:
        """Factory raises ValueError for unknown strategy."""
        with pytest.raises(ValueError, match="Unknown strategy_type"):
            TransformationPipelineFactory._build_strategy("unknown")
