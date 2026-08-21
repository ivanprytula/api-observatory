"""Auth routes — register, login (JWT), me, logout."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.auth import (
    LogoutRequest,
    RefreshRequest,
    RoleAssignment,
    TokenResponse,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from services.ingestor.auth import (
    casbin_guard,
    create_jwt_token,
    create_refresh_token,
    create_session,
    delete_session,
    get_user_roles_in_domain,
    resolve_effective_role,
    revoke_refresh_token,
    verify_jwt_token,
    verify_refresh_token,
)
from services.ingestor.config import settings
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.database import get_db
from services.ingestor.rate_limiting_token_bucket import enforce_public_v1_token_bucket
from services.ingestor.repositories.users import (
    count_active_admins,
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    update_user,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/auth",
    tags=["auth"],
    dependencies=[Depends(enforce_public_v1_token_bucket)],
)

type DbDep = Annotated[AsyncSession, Depends(get_db)]
type JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]

_ph = PasswordHash((Argon2Hasher(), BcryptHasher()))

_R404 = {
    404: {
        "description": "User not found.",
        "content": {"application/json": {"example": {"detail": "User not found."}}},
    }
}
_R401 = {
    401: {
        "description": "Not authenticated - missing or invalid JWT.",
        "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
    }
}
_R403 = {
    403: {
        "description": "Forbidden - authenticated but lacking the required role.",
        "content": {"application/json": {"example": {"detail": "Insufficient role"}}},
    }
}
_R409 = {
    409: {
        "description": "Conflict - username or email already registered.",
        "content": {
            "application/json": {
                "example": {"detail": "Username or email already registered."}
            }
        },
    }
}
_R422 = {
    422: {
        "description": "Validation error - invalid request body or query parameters.",
        "content": {
            "application/json": {
                "example": {
                    "detail": [
                        {
                            "loc": ["body", "username"],
                            "msg": "field required",
                            "type": "value_error.missing",
                        }
                    ]
                }
            }
        },
    }
}


@router.post(
    "/register",
    summary="Register a new user",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R409, **_R422},
)
async def register(body: UserCreate, db: DbDep) -> UserResponse:
    """Register a new user account.

    Args:
        body: UserCreate payload with username, email, and password.
        db: Injected async database session.

    Returns:
        201 UserResponse on success.
        409 if username or email is already taken.
    """
    password_hash = _ph.hash(body.password)
    try:
        user = await create_user(
            session=db,
            username=body.username,
            email=body.email,
            password_hash=password_hash,
            role="user",
            tenant_id=None,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered.",
        ) from None
    logger.info("user_registered", extra={"username": body.username})
    return UserResponse.model_validate(user).model_copy(update={"role": "user"})


@router.post(
    "/users/{username}/role",
    summary="Assign a role to a user",
    response_model=UserResponse,
    responses={**_R401, **_R403, **_R404, **_R422},
)
async def assign_role(
    username: str,
    body: RoleAssignment,
    db: DbDep,
    claims: Annotated[dict[str, Any], Depends(casbin_guard("admin"))],
) -> UserResponse:
    """Assign a role to a user (admin only).

    Requires a valid user JWT with admin role.

    Args:
        username: Target user to update.
        body: RoleAssignment payload with the new role.
        db: Injected async database session.
        claims: Verified JWT claims (dependency injection).

    Returns:
        200 UserResponse with the updated role.
        401 if the JWT is missing or invalid.
        403 if the caller is not an admin.
        404 if the target user does not exist.
    """
    from services.ingestor.auth import assign_user_role

    await assign_user_role(db, username, body.role)
    user = await get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    logger.info(
        "user_role_assigned",
        extra={
            "username": username,
            "role": body.role,
            "by_service": claims.get("sub", ""),
        },
    )
    user_roles = await get_user_roles_in_domain(db, user.username, user.tenant_id)
    role = resolve_effective_role(user_roles)
    return UserResponse.model_validate(user).model_copy(update={"role": role})


@router.delete(
    "/users/{user_id}",
    summary="Soft-delete a user by ID",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_R401, **_R403, **_R404, **_R409},
)
async def delete_user_route(
    user_id: int,
    db: DbDep,
    claims: Annotated[dict[str, Any], Depends(casbin_guard("admin"))],
) -> None:
    """Soft-delete a user by ID (internal service-to-service only).

    Prevents the caller from deleting itself and protects the last active admin.

    Args:
        user_id: Target user primary key.
        db: Injected async database session.
        claims: Verified internal service claims.

    Returns:
        204 No Content on success.
        403 if the caller attempts to delete itself.
        404 if the target user does not exist.
        409 if the target is the last active admin.
    """
    caller: str = claims.get("sub", "")

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.username == caller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users cannot delete themselves.",
        )

    from services.ingestor.auth import has_role_in_domain

    if await has_role_in_domain(db, user.username, "admin", user.tenant_id):
        remaining_admins = await count_active_admins(db, exclude_username=user.username)
        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the last active admin.",
            )

    await delete_user(db, user.id)
    logger.info(
        "user_deleted",
        extra={"username": user.username, "by_service": claims.get("sub", "")},
    )


@router.post(
    "/token",
    summary="Authenticate and return a JWT access token",
    response_model=TokenResponse,
    responses={**_R401, **_R422},
)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbDep,
    response: Response,
) -> TokenResponse:
    """Authenticate and return a JWT access token.

    Also creates a Cache-backed session and sets a session cookie.

    Args:
        request: Raw FastAPI request used to set a secure session cookie.
        form: OAuth2 form with username + password fields.
        db: Injected async database session.

    Returns:
        200 TokenResponse on success.
        401 on invalid credentials.
    """
    user = await get_user_by_username(db, form.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    try:
        valid = _ph.verify(user.password_hash, form.password)
    except UnknownHashError:
        valid = False
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        ) from None

    # Issue JWT with tenant_id claim
    token = create_jwt_token(
        sub=user.username,
        custom_claims={"tenant_id": user.tenant_id},
    )

    # Issue refresh token (Cache-backed, revocable)
    refresh_token = await create_refresh_token(
        sub=user.username,
        custom_claims={"tenant_id": user.tenant_id},
    )

    # Also create a Cache session with tenant_id and set session cookie
    session_id, _ = await create_session(user.username, {"tenant_id": user.tenant_id})
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=settings.token_expiry_hours * 3600,
    )

    logger.info("user_login", extra={"username": user.username})
    return TokenResponse(access_token=token, refresh_token=refresh_token)


@router.get(
    "/me",
    summary="Return the current user profile",
    response_model=UserResponse,
    responses={**_R401, **_R404},
)
async def me(claims: JwtDep, db: DbDep) -> UserResponse:
    """Return the profile of the currently authenticated user.

    Args:
        claims: Decoded JWT payload (injected by verify_jwt_token).
        db: Injected async database session.

    Returns:
        200 UserResponse.
        401 if token is missing/invalid or user no longer exists.
    """
    username: str | None = claims.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims.",
        )
    user = await get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    user_roles = await get_user_roles_in_domain(db, user.username, user.tenant_id)
    role = resolve_effective_role(user_roles)
    return UserResponse.model_validate(user).model_copy(update={"role": role})


@router.post(
    "/logout",
    summary="Invalidate the current session and optionally revoke the refresh token",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    body: LogoutRequest | None = None,
    session_id: str | None = Cookie(default=None),
) -> None:
    """Invalidate the current session and optionally revoke the refresh token.

    Args:
        body: Optional body with refresh_token to revoke.
        session_id: Session ID from the HTTP-only cookie (if present).
    """
    if session_id:
        await delete_session(session_id)
    if body and body.refresh_token:
        import jwt as _jwt

        try:
            # Decode without verification to extract jti — we issued this token
            unverified = _jwt.decode(
                body.refresh_token,
                options={"verify_signature": False, "verify_exp": False},
                algorithms=["HS256"],
            )
            jti = unverified.get("jti")
            if jti:
                await revoke_refresh_token(jti)
        except Exception:  # nosec B110 — malformed token on logout: safe to discard
            pass
    logger.info("user_logout", extra={"session_id": session_id})


@router.post(
    "/refresh",
    summary="Issue a new access and refresh token pair from a valid refresh token",
    response_model=TokenResponse,
    responses={**_R401, **_R422},
)
async def refresh(
    body: RefreshRequest,
    db: DbDep,
) -> TokenResponse:
    """Issue a new access + refresh token pair from a valid refresh token.

    Implements single-use rotation: the old refresh token JTI is revoked
    immediately and a new one is issued, preventing replay attacks.

    Args:
        body: JSON body with refresh_token field.
        db: Injected async database session.

    Returns:
        200 TokenResponse with new access_token + refresh_token.
        401 if refresh token is invalid, expired, or already revoked.
    """
    claims = await verify_refresh_token(body.refresh_token)

    username: str = claims.get("sub", "")
    user = await get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    # Rotate: revoke old refresh token JTI
    old_jti = claims.get("jti")
    if old_jti:
        await revoke_refresh_token(old_jti)

    custom_claims = {"tenant_id": user.tenant_id}
    new_access_token = create_jwt_token(sub=username, custom_claims=custom_claims)
    new_refresh_token = await create_refresh_token(
        sub=username, custom_claims=custom_claims
    )

    logger.info("token_refreshed", extra={"username": username})
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)


# ============================================================================
# Superadmin-protected admin management routes
# ============================================================================


@router.post(
    "/admin/users",
    summary="Create a new admin user",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_R401, **_R403, **_R409, **_R422},
)
async def create_admin(
    body: UserCreate,
    db: DbDep,
    claims: Annotated[dict[str, Any], Depends(casbin_guard("admin"))],
) -> UserResponse:
    """Create a new admin user (admin only).

    Args:
        body: UserCreate payload with username, email, and password.
        db: Injected async database session.
        claims: Verified JWT payload.

    Returns:
        201 UserResponse with the created admin.
        403 if the caller is not an admin.
        409 if username or email is already taken.
    """
    username: str | None = claims.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims.",
        )

    password_hash = _ph.hash(body.password)
    try:
        user = await create_user(
            session=db,
            username=body.username,
            email=body.email,
            password_hash=password_hash,
            role="admin",
            tenant_id=body.tenant_id,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered.",
        ) from None
    logger.info(
        "admin_created",
        extra={"username": body.username, "by": username},
    )
    user_roles = await get_user_roles_in_domain(db, user.username, user.tenant_id)
    role = resolve_effective_role(user_roles)
    return UserResponse.model_validate(user).model_copy(update={"role": role})


@router.get(
    "/admin/users",
    summary="List all users",
    response_model=UserListResponse,
    responses={**_R401, **_R403, **_R422},
)
async def list_users_route(
    db: DbDep,
    claims: Annotated[dict[str, Any], Depends(casbin_guard("admin"))],
    limit: int = 100,
    offset: int = 0,
) -> UserListResponse:
    """List all users (admin only).

    Args:
        db: Injected async database session.
        claims: Verified JWT payload.
        limit: Maximum number of users to return.
        offset: Number of users to skip.

    Returns:
        200 UserListResponse with paginated users.
        403 if the caller is not an admin.
    """
    username: str | None = claims.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims.",
        )

    users, total = await list_users(db, limit=limit, offset=offset)
    responses = []
    for u in users:
        user_roles = await get_user_roles_in_domain(db, u.username, u.tenant_id)
        role = resolve_effective_role(user_roles)
        responses.append(
            UserResponse.model_validate(u).model_copy(update={"role": role})
        )
    return UserListResponse(
        users=responses,
        total=total,
    )


@router.patch(
    "/users/{user_id}",
    summary="Update a user by ID",
    response_model=UserResponse,
    responses={**_R401, **_R403, **_R404, **_R409, **_R422},
)
async def update_user_route(
    user_id: int,
    body: UserUpdate,
    db: DbDep,
    claims: Annotated[dict[str, Any], Depends(casbin_guard("admin"))],
) -> UserResponse:
    """Update mutable fields of a user (admin only).

    Args:
        user_id: Target user primary key.
        body: UserUpdate payload with fields to update.
        db: Injected async database session.
        claims: Verified JWT payload.

    Returns:
        200 UserResponse with the updated user.
        401 if the JWT is missing or invalid.
        403 if the caller is not an admin.
        404 if the target user does not exist.
        409 if the new email is already taken.
    """
    username: str | None = claims.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims.",
        )

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return UserResponse.model_validate(user).model_copy(update={"role": "user"})

    try:
        user = await update_user(
            session=db,
            user_id=user_id,
            email=update_data.get("email"),
            is_active=update_data.get("is_active"),
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        ) from None

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    logger.info(
        "user_updated",
        extra={"user_id": user_id, "by": username},
    )
    user_roles = await get_user_roles_in_domain(db, user.username, user.tenant_id)
    role = resolve_effective_role(user_roles)
    return UserResponse.model_validate(user).model_copy(update={"role": role})
