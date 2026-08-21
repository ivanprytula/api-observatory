"""Reusable FastAPI dependency type aliases.

Centralizes the most common dependency signatures so routers can import
a single name instead of repeating ``Annotated[...]`` inline.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.auth import (
    casbin_guard,
    verify_bearer_token,
    verify_jwt_token,
)
from services.ingestor.database import get_db
from services.ingestor.rate_limiting_token_bucket import enforce_v1_token_bucket


# Database
DbDep = Annotated[AsyncSession, Depends(get_db)]

# Authentication
JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]
BearerDep = Annotated[str, Depends(verify_bearer_token)]

# Authorization
AdminGuard = Annotated[dict[str, Any], Depends(casbin_guard("admin"))]
TokenBucketGuard = Annotated[dict[str, Any], Depends(enforce_v1_token_bucket)]
