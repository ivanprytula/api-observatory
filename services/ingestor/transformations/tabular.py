"""Tabular ETL helpers for Polars-first preview transforms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal


if TYPE_CHECKING:
    import pandas as pd
    import polars as pl


ETLBackend = Literal["polars", "pandas", "dask"]


@dataclass(slots=True)
class NumericSummary:
    """Summary statistics for one numeric field."""

    field: str
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    null_count: int


@dataclass(slots=True)
class TabularPreviewResult:
    """In-memory preview result returned by the ETL engine."""

    backend_requested: str
    backend_used: str
    row_count: int
    columns: list[str]
    observations: list[dict[str, Any]]
    numeric_summaries: list[NumericSummary]
    recommendation: str
    truncated: bool


class UnsupportedETLBackendError(ValueError):
    """Raised when a requested ETL backend is intentionally unavailable."""


class TabularETLEngine:
    """Preview engine for small ETL transforms.

    This engine is deliberately scoped to small preview workloads so the API can
    demonstrate concrete backend choice without introducing distributed runtime
    complexity into the request path.
    """

    @staticmethod
    def preview(
        *,
        backend: ETLBackend,
        observations: list[dict[str, Any]],
        select_columns: list[str] | None = None,
        rename_columns: dict[str, str] | None = None,
        filter_equals: dict[str, Any] | None = None,
        sort_by: str | None = None,
        descending: bool = False,
        numeric_fields: list[str] | None = None,
        preview_limit: int = 100,
    ) -> TabularPreviewResult:
        """Apply a small ETL preview using the requested backend."""
        normalized_backend = backend.lower()
        if normalized_backend == "dask":
            raise UnsupportedETLBackendError(
                "Dask backend is intentionally disabled until distributed ETL pain exists. "
                "Use polars for production transforms and pandas for compatibility workflows."
            )

        if normalized_backend == "polars":
            return TabularETLEngine._preview_with_polars(
                backend_requested=normalized_backend,
                observations=observations,
                select_columns=select_columns,
                rename_columns=rename_columns,
                filter_equals=filter_equals,
                sort_by=sort_by,
                descending=descending,
                numeric_fields=numeric_fields,
                preview_limit=preview_limit,
            )
        if normalized_backend == "pandas":
            return TabularETLEngine._preview_with_pandas(
                backend_requested=normalized_backend,
                observations=observations,
                select_columns=select_columns,
                rename_columns=rename_columns,
                filter_equals=filter_equals,
                sort_by=sort_by,
                descending=descending,
                numeric_fields=numeric_fields,
                preview_limit=preview_limit,
            )
        raise ValueError(f"Unsupported ETL backend: {backend}")

    @staticmethod
    def _preview_with_polars(
        *,
        backend_requested: str,
        observations: list[dict[str, Any]],
        select_columns: list[str] | None,
        rename_columns: dict[str, str] | None,
        filter_equals: dict[str, Any] | None,
        sort_by: str | None,
        descending: bool,
        numeric_fields: list[str] | None,
        preview_limit: int,
    ) -> TabularPreviewResult:
        import polars as pl

        frame = pl.from_dicts(observations)
        frame = _apply_polars_ops(
            frame,
            select_columns=select_columns,
            rename_columns=rename_columns,
            filter_equals=filter_equals,
            sort_by=sort_by,
            descending=descending,
        )
        numeric_summaries = _summarize_polars(frame, numeric_fields or [])
        row_count = frame.height
        preview = frame.head(preview_limit)
        return TabularPreviewResult(
            backend_requested=backend_requested,
            backend_used="polars",
            row_count=row_count,
            columns=preview.columns,
            observations=preview.to_dicts(),
            numeric_summaries=numeric_summaries,
            recommendation=(
                "Polars is the default production ETL backend for predictable memory use "
                "and fast columnar transforms."
            ),
            truncated=row_count > preview_limit,
        )

    @staticmethod
    def _preview_with_pandas(
        *,
        backend_requested: str,
        observations: list[dict[str, Any]],
        select_columns: list[str] | None,
        rename_columns: dict[str, str] | None,
        filter_equals: dict[str, Any] | None,
        sort_by: str | None,
        descending: bool,
        numeric_fields: list[str] | None,
        preview_limit: int,
    ) -> TabularPreviewResult:
        import pandas as pd

        frame = pd.DataFrame.from_observations(observations)
        frame = _apply_pandas_ops(
            frame,
            select_columns=select_columns,
            rename_columns=rename_columns,
            filter_equals=filter_equals,
            sort_by=sort_by,
            descending=descending,
        )
        numeric_summaries = _summarize_pandas(frame, numeric_fields or [])
        row_count = len(frame.index)
        preview = frame.head(preview_limit)
        sanitized_observations = preview.where(pd.notna(preview), None).to_dict(
            "observations"
        )
        return TabularPreviewResult(
            backend_requested=backend_requested,
            backend_used="pandas",
            row_count=row_count,
            columns=list(preview.columns),
            observations=sanitized_observations,
            numeric_summaries=numeric_summaries,
            recommendation=(
                "Pandas remains available for compatibility and notebook workflows, but "
                "Polars is preferred for production ETL paths."
            ),
            truncated=row_count > preview_limit,
        )


def _apply_polars_ops(
    frame: pl.DataFrame,
    *,
    select_columns: list[str] | None,
    rename_columns: dict[str, str] | None,
    filter_equals: dict[str, Any] | None,
    sort_by: str | None,
    descending: bool,
) -> pl.DataFrame:
    import polars as pl

    if rename_columns:
        applicable = {
            current: renamed
            for current, renamed in rename_columns.items()
            if current in frame.columns
        }
        if applicable:
            frame = frame.rename(applicable)
    if filter_equals:
        for field, value in filter_equals.items():
            if field in frame.columns:
                frame = frame.filter(pl.col(field) == value)
    if select_columns:
        available = [column for column in select_columns if column in frame.columns]
        if available:
            frame = frame.select(available)
    if sort_by and sort_by in frame.columns:
        frame = frame.sort(sort_by, descending=descending)
    return frame


def _apply_pandas_ops(
    frame: pd.DataFrame,
    *,
    select_columns: list[str] | None,
    rename_columns: dict[str, str] | None,
    filter_equals: dict[str, Any] | None,
    sort_by: str | None,
    descending: bool,
) -> pd.DataFrame:

    if rename_columns:
        applicable = {
            current: renamed
            for current, renamed in rename_columns.items()
            if current in frame.columns
        }
        if applicable:
            frame = frame.rename(columns=applicable)
    if filter_equals:
        for field, value in filter_equals.items():
            if field in frame.columns:
                frame = frame.loc[frame[field] == value]
    if select_columns:
        available = [column for column in select_columns if column in frame.columns]
        if available:
            frame = frame.loc[:, available]
    if sort_by and sort_by in frame.columns:
        frame = frame.sort_values(by=sort_by, ascending=not descending)
    return frame


def _summarize_polars(
    frame: pl.DataFrame, numeric_fields: list[str]
) -> list[NumericSummary]:
    import polars as pl

    summaries: list[NumericSummary] = []
    for field in numeric_fields:
        if field not in frame.columns:
            continue
        numeric_series = frame.get_column(field).cast(pl.Float64, strict=False)
        summaries.append(
            NumericSummary(
                field=field,
                min_value=numeric_series.min(),
                max_value=numeric_series.max(),
                mean_value=numeric_series.mean(),
                null_count=numeric_series.null_count(),
            )
        )
    return summaries


def _summarize_pandas(
    frame: pd.DataFrame, numeric_fields: list[str]
) -> list[NumericSummary]:
    import pandas as pd

    summaries: list[NumericSummary] = []
    for field in numeric_fields:
        if field not in frame.columns:
            continue
        numeric_series = pd.to_numeric(frame[field], errors="coerce")
        summaries.append(
            NumericSummary(
                field=field,
                min_value=_as_optional_float(numeric_series.min()),
                max_value=_as_optional_float(numeric_series.max()),
                mean_value=_as_optional_float(numeric_series.mean()),
                null_count=int(numeric_series.isna().sum()),
            )
        )
    return summaries


def _as_optional_float(value: object) -> float | None:
    import pandas as pd

    if pd.isna(value):
        return None
    if value is None:
        return None
    return float(value)
