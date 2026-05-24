"""Repository-style orchestration for ETL preview requests."""

from __future__ import annotations

from services.ingestor.api_schemas.etl import (
    ETLPreviewRequest,
    ETLPreviewResponse,
    NumericFieldSummary,
)
from services.ingestor.transformations.tabular import TabularETLEngine


def preview_etl_transform(payload: ETLPreviewRequest) -> ETLPreviewResponse:
    """Run a bounded ETL preview for a small record batch."""
    result = TabularETLEngine.preview(
        backend=payload.backend,  # ty: ignore[arg-type]
        records=payload.records,
        rename_columns=payload.rename_columns,
        select_columns=payload.select_columns,
        filter_equals=payload.filter_equals,
        sort_by=payload.sort_by,
        descending=payload.descending,
        numeric_fields=payload.numeric_fields,
    )
    return ETLPreviewResponse(
        backend_requested=result.backend_requested,
        backend_used=result.backend_used,
        row_count=result.row_count,
        columns=result.columns,
        records=result.records,
        numeric_summaries=[
            NumericFieldSummary(
                field=item.field,
                min_value=item.min_value,
                max_value=item.max_value,
                mean_value=item.mean_value,
                null_count=item.null_count,
            )
            for item in result.numeric_summaries
        ],
        recommendation=result.recommendation,
        truncated=result.truncated,
    )
