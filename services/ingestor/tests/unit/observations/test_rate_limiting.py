"""Unit tests for advanced rate-limiting algorithms.

Pure logic tests — no database, no ASGI client.
Covers apply_jitter (thundering-herd prevention).
"""

import pytest

from services.ingestor.rate_limiting_advanced import apply_jitter


# ---------------------------------------------------------------------------
# apply_jitter
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestApplyJitter:
    """Unit tests for the thundering-herd jitter function."""

    def test_jitter_no_offset(self) -> None:
        """Zero jitter returns the base value unchanged."""
        result = apply_jitter(10.0, 0.0, 0.0)
        assert result == 10.0

    def test_jitter_positive_range(self) -> None:
        """Result stays within [base + min, base + max]."""
        for _ in range(50):
            result = apply_jitter(10.0, -2.0, 2.0)
            assert 8.0 <= result <= 12.0

    def test_jitter_clamps_to_zero(self) -> None:
        """Large negative jitter clamps result to 0, never negative."""
        result = apply_jitter(1.0, -100.0, -99.0)
        assert result == 0.0

    def test_jitter_all_positive(self) -> None:
        """Positive-only jitter always increases the base value."""
        for _ in range(50):
            result = apply_jitter(5.0, 1.0, 3.0)
            assert 6.0 <= result <= 8.0
