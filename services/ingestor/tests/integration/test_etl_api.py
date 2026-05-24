"""Integration tests for ETL preview API."""

from __future__ import annotations

from httpx import AsyncClient


_RECORDS = [
    {"provider": "alpha", "latency_ms": 110, "status": "ok"},
    {"provider": "beta", "latency_ms": 190, "status": "warn"},
    {"provider": "alpha", "latency_ms": 95, "status": "ok"},
]


class TestETLPreviewApi:
    """ETL backend preview behavior."""

    async def test_preview_transform_with_polars(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/etl/preview",
            json={
                "backend": "polars",
                "records": _RECORDS,
                "rename_columns": {"latency_ms": "p95_latency_ms"},
                "select_columns": ["provider", "p95_latency_ms", "status"],
                "sort_by": "p95_latency_ms",
                "descending": True,
                "numeric_fields": ["p95_latency_ms"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["backend_used"] == "polars"
        assert body["row_count"] == 3
        assert body["columns"] == ["provider", "p95_latency_ms", "status"]
        assert body["records"][0]["p95_latency_ms"] == 190
        assert body["numeric_summaries"][0]["field"] == "p95_latency_ms"

    async def test_preview_transform_with_pandas(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/etl/preview",
            json={
                "backend": "pandas",
                "records": _RECORDS,
                "filter_equals": {"provider": "alpha"},
                "sort_by": "latency_ms",
                "numeric_fields": ["latency_ms"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["backend_used"] == "pandas"
        assert body["row_count"] == 2
        assert all(item["provider"] == "alpha" for item in body["records"])

    async def test_preview_transform_with_dask_returns_501(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/etl/preview",
            json={
                "backend": "dask",
                "records": _RECORDS,
            },
        )
        assert response.status_code == 501
        assert "Dask backend is intentionally disabled" in response.json()["detail"]
