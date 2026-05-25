"""Unit tests for scorecard business-logic helpers.

These tests cover ``_scorecard_from_agg`` and ``_row_to_kwargs`` directly —
no database, no HTTP client.  They are the fast lane for verifying metric
formulas and edge cases.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.ingestor.repositories.scorecards import (
    _row_to_kwargs,
    _scorecard_from_agg,
)


def _mock_source(source_id: int = 1, name: str = "test-api") -> MagicMock:
    src = MagicMock()
    src.id = source_id
    src.name = name
    return src


@pytest.mark.unit
class TestScorecardFromAgg:
    """_scorecard_from_agg: pure metric derivation from pre-aggregated scalars."""

    def test_zero_samples_returns_100_uptime(self) -> None:
        sc = _scorecard_from_agg(
            _mock_source(),
            window_days=7,
            slo_target_pct=99.9,
            sample_count=0,
            error_count=0,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
        )
        assert sc.uptime_pct == 100.0
        assert sc.error_count == 0
        assert sc.p95_latency_ms == 0.0
        assert sc.error_budget_burn_rate == 0.0

    def test_all_successful_samples(self) -> None:
        sc = _scorecard_from_agg(
            _mock_source(),
            window_days=1,
            slo_target_pct=99.9,
            sample_count=100,
            error_count=0,
            avg_latency_ms=42.0,
            p50_latency_ms=40.0,
            p95_latency_ms=95.0,
        )
        assert sc.uptime_pct == 100.0
        assert sc.error_budget_burn_rate == 0.0
        assert sc.avg_latency_ms == 42.0
        assert sc.p50_latency_ms == 40.0
        assert sc.p95_latency_ms == 95.0

    def test_burn_rate_computed_correctly(self) -> None:
        # 80% uptime, 95% SLO target → budget = 5%, error_rate = 20%
        # burn_rate = 0.20 / 0.05 = 4.0
        sc = _scorecard_from_agg(
            _mock_source(),
            window_days=30,
            slo_target_pct=95.0,
            sample_count=10,
            error_count=2,
            avg_latency_ms=100.0,
            p50_latency_ms=90.0,
            p95_latency_ms=480.0,
        )
        assert abs(sc.uptime_pct - 80.0) < 0.01
        assert abs(sc.error_budget_burn_rate - 4.0) < 0.01

    def test_high_burn_rate_when_slo_99_9_and_10_pct_errors(self) -> None:
        # error_rate=0.10, budget=0.001 → burn_rate ≈ 100
        sc = _scorecard_from_agg(
            _mock_source(),
            window_days=7,
            slo_target_pct=99.9,
            sample_count=10,
            error_count=1,
            avg_latency_ms=200.0,
            p50_latency_ms=150.0,
            p95_latency_ms=900.0,
        )
        assert sc.error_budget_burn_rate > 50.0

    def test_100_pct_slo_with_no_errors_gives_zero_burn(self) -> None:
        sc = _scorecard_from_agg(
            _mock_source(),
            window_days=7,
            slo_target_pct=100.0,
            sample_count=5,
            error_count=0,
            avg_latency_ms=10.0,
            p50_latency_ms=9.0,
            p95_latency_ms=15.0,
        )
        assert sc.error_budget_burn_rate == 0.0

    def test_fields_are_rounded(self) -> None:
        sc = _scorecard_from_agg(
            _mock_source(),
            window_days=1,
            slo_target_pct=99.9,
            sample_count=3,
            error_count=1,
            avg_latency_ms=33.333_333,
            p50_latency_ms=30.0,
            p95_latency_ms=100.0,
        )
        # uptime_pct: 2/3 * 100 ≈ 66.6667 → rounded to 4dp
        assert sc.uptime_pct == round(2 / 3 * 100, 4)
        # avg rounded to 2 decimal places
        assert sc.avg_latency_ms == round(33.333_333, 2)

    def test_source_metadata_propagated(self) -> None:
        sc = _scorecard_from_agg(
            _mock_source(source_id=42, name="payments-api"),
            window_days=14,
            slo_target_pct=99.9,
            sample_count=0,
            error_count=0,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
        )
        assert sc.source_id == 42
        assert sc.source_name == "payments-api"
        assert sc.window_days == 14
        assert sc.slo_target_pct == 99.9


@pytest.mark.unit
class TestRowToKwargs:
    """_row_to_kwargs: mapping aggregate result rows to keyword arguments."""

    def test_none_row_returns_zeros(self) -> None:
        kwargs = _row_to_kwargs(None)
        assert kwargs == {
            "sample_count": 0,
            "error_count": 0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }

    def test_populated_row_maps_correctly(self) -> None:
        row = SimpleNamespace(
            sample_count=20,
            error_count=2,
            avg_latency_ms=55.5,
            p50_latency_ms=50.0,
            p95_latency_ms=190.5,
        )
        kwargs = _row_to_kwargs(row)  # type: ignore[arg-type]
        assert kwargs["sample_count"] == 20
        assert kwargs["error_count"] == 2
        assert kwargs["avg_latency_ms"] == 55.5
        assert kwargs["p50_latency_ms"] == 50.0
        assert kwargs["p95_latency_ms"] == 190.5

    def test_null_latency_columns_default_to_zero(self) -> None:
        row = SimpleNamespace(
            sample_count=0,
            error_count=0,
            avg_latency_ms=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
        )
        kwargs = _row_to_kwargs(row)  # type: ignore[arg-type]
        assert kwargs["avg_latency_ms"] == 0.0
        assert kwargs["p50_latency_ms"] == 0.0
        assert kwargs["p95_latency_ms"] == 0.0
