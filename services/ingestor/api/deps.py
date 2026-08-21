"""Reusable FastAPI dependency type aliases.

Centralizes the most common dependency signatures so routers can import
a single name instead of repeating ``Annotated[...]`` inline.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.auth import (
    casbin_guard,
    verify_bearer_token,
    verify_jwt_token,
    verify_session,
)
from services.ingestor.core.database import get_db
from services.ingestor.rate_limiting_token_bucket import enforce_v1_token_bucket
from services.ingestor.repositories.users import get_user_by_username


# Database
DbDep = Annotated[AsyncSession, Depends(get_db)]
SessionDep = Annotated[dict[str, Any], Depends(verify_session)]

# Authentication
JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]
BearerDep = Annotated[str, Depends(verify_bearer_token)]
TokenDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]

# Authorization
AdminGuard = Annotated[dict[str, Any], Depends(casbin_guard("admin"))]
SuperuserDep = Annotated[dict[str, Any], Depends(casbin_guard("admin"))]
TokenBucketGuard = Annotated[dict[str, Any], Depends(enforce_v1_token_bucket)]


async def _current_user(
    claims: dict[str, Any] = Depends(verify_jwt_token),
    db: AsyncSession = Depends(get_db),
) -> Any:
    username = claims.get("sub")
    if not username:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail="Invalid token claims.",
        )
    user = await get_user_by_username(db, str(username))
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail="User not found or inactive.",
        )
    return user


CurrentUser = Annotated[Any, Depends(_current_user)]


def _tenant_dep(
    claims: dict[str, Any] = Depends(verify_jwt_token),
) -> int | None:
    return claims.get("tenant_id")


TenantDep = Annotated[int | None, Depends(_tenant_dep)]
