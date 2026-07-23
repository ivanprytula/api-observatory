"""Subscription and delivery endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.subscriptions import (
    AlertPolicyListResponse,
    ChannelConfigListResponse,
    DeliveryLog,
    DeliveryLogListResponse,
    EscalationPreview,
    EscalationPreviewRequest,
    TestDeliveryRequest,
)
from services.ingestor.auth import jwt_role_guard
from services.ingestor.constants import API_V1_PREFIX, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.ingestor.database import get_db
from services.ingestor.notifications import dispatch_notification_event
from services.ingestor.repositories.subscriptions import (
    build_escalation_preview,
    list_alert_policies,
    list_channel_configs,
    list_delivery_logs,
)


router = APIRouter(prefix=f"{API_V1_PREFIX}/subscriptions", tags=["subscriptions"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]
type AdminJwtDep = Annotated[dict[str, Any], Depends(jwt_role_guard("admin"))]

_R404 = {"404": {"description": "Requested source profile was not found."}}
_R422 = {"422": {"description": "Validation error in query parameters or payload."}}


@router.get(
    "/alert-policies",
    response_model=AlertPolicyListResponse,
    summary="List subscription alert policies",
    responses={**_R422},
)
async def get_alert_policies(
    db: DbDep,
    source_id: int | None = Query(None, ge=1, description="Optional source filter."),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of policy items to return.",
    ),
) -> AlertPolicyListResponse:
    """Return computed alert policies for active sources."""
    items = await list_alert_policies(db, source_id=source_id, limit=limit)
    return AlertPolicyListResponse(items=items, total=len(items))


@router.get(
    "/channel-configs",
    response_model=ChannelConfigListResponse,
    summary="List delivery channel configurations",
)
async def get_channel_configs() -> ChannelConfigListResponse:
    """Return safe summaries of configured delivery channels."""
    items = list_channel_configs()
    return ChannelConfigListResponse(items=items, total=len(items))


@router.get(
    "/delivery-logs",
    response_model=DeliveryLogListResponse,
    summary="List delivery logs",
    responses={**_R422},
)
async def get_delivery_logs(
    db: DbDep,
    source_id: int | None = Query(None, ge=1, description="Optional source filter."),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of delivery log items to return.",
    ),
) -> DeliveryLogListResponse:
    """Return delivery results built from recent drift events."""
    items = await list_delivery_logs(db, source_id=source_id, limit=limit)
    return DeliveryLogListResponse(items=items, total=len(items))


@router.post(
    "/escalations/preview",
    response_model=EscalationPreview,
    summary="Preview escalation plan",
    responses={**_R404, **_R422},
)
async def preview_escalation(
    payload: EscalationPreviewRequest,
    db: DbDep,
) -> EscalationPreview:
    """Return a computed escalation plan for the supplied event payload."""
    preview = await build_escalation_preview(
        db,
        event=payload.event,
        severity=payload.severity,
        source_id=payload.source_id,
        channels=payload.channels,
    )
    if payload.source_id is not None and preview.policy_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source profile not found",
        )
    return preview


@router.post(
    "/deliveries/test",
    response_model=DeliveryLog,
    summary="Dispatch test delivery",
    responses={**_R422},
)
async def test_delivery(
    payload: TestDeliveryRequest,
    _: AdminJwtDep,
) -> DeliveryLog:
    """Send a test notification through configured channels."""
    result = await dispatch_notification_event(
        event=payload.event,
        message=payload.message,
        severity=payload.severity,
        channels=payload.channels,
        context={
            "source": "subscription_delivery_test",
            "source_id": payload.source_id,
        },
    )

    status = "delivered" if result.get("sent", 0) > 0 else "suppressed"
    detail = result.get("detail") or (
        f"sent={result.get('sent', 0)} failed={result.get('failed', 0)}"
    )
    now = datetime.now(UTC).replace(tzinfo=None)

    return DeliveryLog(
        delivery_id=f"delivery-test-{int(now.timestamp())}",
        source_id=payload.source_id,
        policy_id=(
            f"policy-source-{payload.source_id}"
            if payload.source_id is not None
            else None
        ),
        event_type=payload.event,
        severity=payload.severity,
        status=status,
        channel=(payload.channels[0] if payload.channels else None),
        detail=detail,
        created_at=now,
        metadata={"results": result.get("results", [])},
    )
