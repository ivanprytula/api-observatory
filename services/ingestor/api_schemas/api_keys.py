"""Pydantic v2 schemas for the API Keys resource."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from services.ingestor.security.api_keys import VALID_SCOPES


class ApiKeyCreate(BaseModel):
    """Request body for creating a new API key."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable label for this key.",
    )
    tenant_id: int | None = Field(
        None, description="Tenant this key is scoped to. None = global."
    )
    scopes: list[str] = Field(
        ...,
        min_length=1,
        description=(
            f"Permissions granted to this key. Valid values: {sorted(VALID_SCOPES)}."
        ),
    )
    expires_at: datetime | None = Field(
        None, description="Optional expiry. None = no expiry."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "ci-read-key",
                "tenant_id": 1,
                "scopes": ["observations:read", "sources:read"],
                "expires_at": None,
            }
        }
    }


class ApiKeyResponse(BaseModel):
    """Response schema for an API key (without the raw secret)."""

    id: int
    name: str
    key_prefix: str = Field(..., description="First 8 hex chars — safe to log.")
    tenant_id: int | None
    scopes: list[str]
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Extended response returned only at creation time — includes the full raw key.

    The ``full_key`` field is shown **once** and never stored. Store it securely.
    """

    full_key: str = Field(..., description="Full raw key. Shown once — store securely.")
