"""Reporting shared utilities."""

from datetime import UTC, datetime, timedelta


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _cutoff_utc_naive(days: int) -> datetime:
    return _now_utc_naive() - timedelta(days=days)
