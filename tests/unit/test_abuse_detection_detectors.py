"""Unit tests for the abuse detection signal evaluators."""

from __future__ import annotations

import pytest

from services.ingestor.constants import (
    ABUSE_SEVERITY_CRITICAL,
    ABUSE_SEVERITY_HIGH,
    ABUSE_SEVERITY_MEDIUM,
)
from services.ingestor.security.abuse_detection import (
    evaluate_key_suspicion,
    evaluate_source_noise,
    is_high_or_above,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# evaluate_source_noise
# ---------------------------------------------------------------------------
class TestEvaluateSourceNoise:
    """Pure function: returns AbuseSignalCreate or None based on call ratio."""

    def test_below_threshold_returns_none(self) -> None:
        result = evaluate_source_noise(
            source_name="src-001",
            request_count=59,
            window_seconds=60,
            quota_per_minute=60,
        )
        assert result is None

    def test_exactly_at_quota_returns_none(self) -> None:
        result = evaluate_source_noise(
            source_name="src-001",
            request_count=60,
            window_seconds=60,
            quota_per_minute=60,
        )
        assert result is None

    def test_ratio_2x_returns_medium(self) -> None:
        result = evaluate_source_noise(
            source_name="src-001",
            request_count=120,
            window_seconds=60,
            quota_per_minute=60,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_MEDIUM

    def test_ratio_5x_returns_high(self) -> None:
        result = evaluate_source_noise(
            source_name="src-001",
            request_count=300,
            window_seconds=60,
            quota_per_minute=60,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_HIGH

    def test_ratio_10x_returns_critical(self) -> None:
        result = evaluate_source_noise(
            source_name="src-001",
            request_count=600,
            window_seconds=60,
            quota_per_minute=60,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_CRITICAL

    def test_result_actor_id_matches_source_id(self) -> None:
        result = evaluate_source_noise(
            source_name="src-xyz",
            request_count=200,
            window_seconds=60,
            quota_per_minute=60,
        )
        assert result is not None
        assert result.actor_id == "src-xyz"

    def test_zero_quota_uses_default(self) -> None:
        """quota_per_minute=None falls back to default quota constant."""
        result = evaluate_source_noise(
            source_name="src-001",
            request_count=1,
            window_seconds=60,
            quota_per_minute=None,
        )
        # With default quota, 1 call is far below threshold → None
        assert result is None


# ---------------------------------------------------------------------------
# evaluate_key_suspicion
# ---------------------------------------------------------------------------
class TestEvaluateKeySuspicion:
    """Pure function: returns AbuseSignalCreate or None based on key behaviour metrics."""

    def test_no_signals_returns_none(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=1,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is None

    # --- auth_failures thresholds ---
    def test_auth_failures_below_threshold_returns_none(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=4,
            distinct_ip_count=1,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is None

    def test_auth_failures_at_medium_threshold_returns_medium(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=5,
            distinct_ip_count=1,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_MEDIUM

    def test_auth_failures_at_high_threshold_returns_high(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=20,
            distinct_ip_count=1,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_HIGH

    # --- distinct_ips thresholds ---
    def test_distinct_ips_below_threshold_returns_none(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=4,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is None

    def test_distinct_ips_at_medium_threshold_returns_medium(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=5,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_MEDIUM

    def test_distinct_ips_at_high_threshold_returns_high(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=10,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_HIGH

    # --- error_rate thresholds ---
    def test_error_rate_below_threshold_returns_none(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=1,
            error_rate=0.49,
            total_requests=100,
        )
        assert result is None

    def test_error_rate_at_medium_threshold_returns_medium(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=1,
            error_rate=0.5,
            total_requests=100,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_MEDIUM

    def test_error_rate_at_high_threshold_returns_high(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=1,
            error_rate=0.9,
            total_requests=100,
        )
        assert result is not None
        assert result.severity == ABUSE_SEVERITY_HIGH

    def test_zero_total_requests_skips_error_rate(self) -> None:
        """If total_requests=0, error rate check is skipped (no ZeroDivisionError)."""
        result = evaluate_key_suspicion(
            key_prefix="key-001",
            window_seconds=3600,
            auth_failure_count=0,
            distinct_ip_count=1,
            error_rate=0.0,
            total_requests=0,
        )
        assert result is None

    def test_result_actor_id_matches_key_id(self) -> None:
        result = evaluate_key_suspicion(
            key_prefix="key-xyz",
            window_seconds=3600,
            auth_failure_count=5,
            distinct_ip_count=1,
            error_rate=0.0,
            total_requests=100,
        )
        assert result is not None
        assert result.actor_id == "key-xyz"


# ---------------------------------------------------------------------------
# is_high_or_above
# ---------------------------------------------------------------------------
class TestIsHighOrAbove:
    """Utility: returns True for high/critical, False for low/medium."""

    @pytest.mark.parametrize("severity", ["low", "medium"])
    def test_low_and_medium_return_false(self, severity: str) -> None:
        assert is_high_or_above(severity) is False

    @pytest.mark.parametrize("severity", ["high", "critical"])
    def test_high_and_critical_return_true(self, severity: str) -> None:
        assert is_high_or_above(severity) is True

    def test_unknown_severity_returns_false(self) -> None:
        assert is_high_or_above("unknown") is False
