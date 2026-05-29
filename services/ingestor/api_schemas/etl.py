"""Pydantic schemas for ETL preview endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NumericFieldSummary(BaseModel):
    """Summary statistics for one numeric field in preview output."""

    field: str = Field(..., description="Name of the numeric field being summarized.")
    min_value: float | None = Field(
        None,
        description="Minimum value observed for the field in the preview window.",
    )
    max_value: float | None = Field(
        None,
        description="Maximum value observed for the field in the preview window.",
    )
    mean_value: float | None = Field(
        None,
        description="Mean value observed for the field in the preview window.",
    )
    null_count: int = Field(
        ...,
        ge=0,
        description="Number of null or non-numeric values encountered for the field.",
    )


class ETLPreviewRequest(BaseModel):
    """Request body for tabular ETL preview execution."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "backend": "polars",
                    "observations": [
                        {"provider": "alpha", "latency_ms": 110, "status": "ok"},
                        {"provider": "beta", "latency_ms": 190, "status": "warn"},
                    ],
                    "rename_columns": {"latency_ms": "p95_latency_ms"},
                    "select_columns": ["provider", "p95_latency_ms", "status"],
                    "sort_by": "p95_latency_ms",
                    "descending": True,
                    "numeric_fields": ["p95_latency_ms"],
                }
            ]
        }
    }

    backend: str = Field(
        default="polars",
        description="Requested ETL backend. Supported: polars, pandas, dask.",
    )
    observations: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Small in-memory batch of observations used for ETL preview execution.",
    )
    rename_columns: dict[str, str] | None = Field(
        default=None,
        description="Optional mapping of source column names to renamed output columns.",
    )
    select_columns: list[str] | None = Field(
        default=None,
        description="Optional ordered subset of columns to keep in preview output.",
    )
    filter_equals: dict[str, Any] | None = Field(
        default=None,
        description="Optional equality filters applied before projection and sorting.",
    )
    sort_by: str | None = Field(
        default=None,
        description="Optional column name used to sort the preview output.",
    )
    descending: bool = Field(
        default=False,
        description="Whether the sort order should be descending when sort_by is set.",
    )
    numeric_fields: list[str] | None = Field(
        default=None,
        description="Fields for which numeric summaries should be computed.",
    )


class ETLPreviewResponse(BaseModel):
    """Response payload for ETL preview execution."""

    backend_requested: str = Field(
        ..., description="Backend originally requested by the caller."
    )
    backend_used: str = Field(
        ...,
        description="Backend that actually executed the preview.",
    )
    row_count: int = Field(..., ge=0, description="Total rows after ETL filtering.")
    columns: list[str] = Field(
        ..., description="Ordered output columns after ETL steps."
    )
    observations: list[dict[str, Any]] = Field(
        ..., description="Preview rows after ETL operations have been applied."
    )
    numeric_summaries: list[NumericFieldSummary] = Field(
        ..., description="Numeric summary rows for selected fields."
    )
    recommendation: str = Field(
        ..., description="Guidance explaining the preferred backend for this workload."
    )
    truncated: bool = Field(
        ..., description="Whether preview rows were truncated to the API preview limit."
    )
