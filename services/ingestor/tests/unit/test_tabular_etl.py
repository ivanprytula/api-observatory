"""Unit tests for the tabular ETL engine."""

from __future__ import annotations

import pytest

from services.ingestor.transformations.tabular import (
    TabularETLEngine,
    UnsupportedETLBackendError,
)


_RECORDS = [
    {"provider": "alpha", "latency_ms": 110, "status": "ok"},
    {"provider": "beta", "latency_ms": 190, "status": "warn"},
    {"provider": "alpha", "latency_ms": 95, "status": "ok"},
]


class TestTabularETLEngine:
    """Polars-first tabular ETL behavior."""

    def test_polars_preview(self) -> None:
        result = TabularETLEngine.preview(
            backend="polars",
            records=_RECORDS,
            rename_columns={"latency_ms": "p95_latency_ms"},
            select_columns=["provider", "p95_latency_ms"],
            sort_by="p95_latency_ms",
            descending=True,
            numeric_fields=["p95_latency_ms"],
        )
        assert result.backend_used == "polars"
        assert result.row_count == 3
        assert result.columns == ["provider", "p95_latency_ms"]
        assert result.records[0]["p95_latency_ms"] == 190

    def test_pandas_preview(self) -> None:
        result = TabularETLEngine.preview(
            backend="pandas",
            records=_RECORDS,
            filter_equals={"provider": "alpha"},
            sort_by="latency_ms",
            numeric_fields=["latency_ms"],
        )
        assert result.backend_used == "pandas"
        assert result.row_count == 2
        assert all(item["provider"] == "alpha" for item in result.records)

    def test_dask_preview_is_blocked(self) -> None:
        with pytest.raises(UnsupportedETLBackendError):
            TabularETLEngine.preview(backend="dask", records=_RECORDS)
