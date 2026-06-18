"""ETL preview endpoints for backend selection and transform planning."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from services.ingestor.api_schemas.etl import ETLPreviewRequest, ETLPreviewResponse
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.repositories.etl import preview_etl_transform


router = APIRouter(prefix=f"{API_V1_PREFIX}/etl", tags=["etl"])

_R422 = {"422": {"description": "Validation error in request payload."}}
_R501 = {"501": {"description": "Requested ETL backend is intentionally unavailable."}}


@router.post(
    "/preview",
    response_model=ETLPreviewResponse,
    summary="Preview ETL transform",
    responses={**_R422, **_R501},
)
async def preview_transform(payload: ETLPreviewRequest) -> ETLPreviewResponse:
    """Run a small ETL preview using the requested backend."""
    from services.ingestor.transformations.tabular import UnsupportedETLBackendError

    try:
        return preview_etl_transform(payload)
    except UnsupportedETLBackendError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
