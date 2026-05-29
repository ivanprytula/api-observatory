"""Unit tests for CRUD functions.

Pure logic tests using mocked sessions — no real database.
Covers edge cases like empty batch early-return.
"""

from unittest.mock import AsyncMock

import pytest

from services.ingestor.repositories.observations import (
    create_observations_batch,
    create_observations_batch_naive,
)


# ---------------------------------------------------------------------------
# Batch empty list early-return
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestBatchEmptyList:
    """Empty list early-return in both batch CRUD functions."""

    async def test_create_observations_batch_empty(self) -> None:
        """Optimised batch with empty list returns [] immediately."""
        mock_session = AsyncMock()
        result = await create_observations_batch(mock_session, [])

        assert result == []
        mock_session.execute.assert_not_called()

    async def test_create_observations_batch_naive_empty(self) -> None:
        """Naive batch with empty list returns [] immediately."""
        mock_session = AsyncMock()
        result = await create_observations_batch_naive(mock_session, [])

        assert result == []
        mock_session.add_all.assert_not_called()
