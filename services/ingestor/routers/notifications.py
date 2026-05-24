"""Notification routes for Pillar 8 baseline."""

from __future__ import annotations

from fastapi import APIRouter, status

from services.ingestor.api_schemas.records import (
    NotificationTestRequest,
    NotificationTestResponse,
)
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.notifications import dispatch_notification_event


router = APIRouter(prefix=f"{API_V1_PREFIX}/notifications", tags=["notifications"])


@router.post(
    "/test",
    response_model=NotificationTestResponse,
    status_code=status.HTTP_200_OK,
)
async def test_notification_dispatch(
    payload: NotificationTestRequest,
) -> NotificationTestResponse:
    """Dispatch a test notification to selected/default channels."""
    raw = await dispatch_notification_event(
        event=payload.event,
        message=payload.message,
        severity=payload.severity,
        channels=payload.channels,
        context={"source": "api_test_endpoint"},
    )
    return NotificationTestResponse.model_validate(raw)
