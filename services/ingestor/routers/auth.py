"""Auth routes — register, login (JWT), me, logout."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import (
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from services.ingestor.auth import (
    create_jwt_token,
    create_refresh_token,
    create_session,
    delete_session,
    revoke_refresh_token,
    verify_jwt_token,
    verify_refresh_token,
)
from services.ingestor.config import settings
from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.database import get_db
from services.ingestor.rate_limiting_token_bucket import enforce_public_v1_token_bucket
from services.ingestor.repositories.observations import (
    create_user,
    get_user_by_username,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/auth",
    tags=["auth"],
    dependencies=[Depends(enforce_public_v1_token_bucket)],
)

type DbDep = Annotated[AsyncSession, Depends(get_db)]
type JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]

_ph = PasswordHasher()


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
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
            role="viewer",
            tenant_id=None,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered.",
        ) from None
    logger.info("user_registered", extra={"username": body.username})
    return UserResponse.model_validate(user)


@router.post("/token", response_model=TokenResponse)
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
        _ph.verify(user.password_hash, form.password)
    except VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        ) from None

    # Issue JWT with tenant_id claim
    token = create_jwt_token(
        sub=user.username,
        custom_claims={"role": user.role, "tenant_id": user.tenant_id},
    )

    # Issue refresh token (Cache-backed, revocable)
    refresh_token = await create_refresh_token(
        sub=user.username,
        custom_claims={"role": user.role, "tenant_id": user.tenant_id},
    )

    # Also create a Cache session with tenant_id and set session cookie
    session_id, _ = await create_session(
        user.username, {"role": user.role, "tenant_id": user.tenant_id}
    )
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


@router.get("/me", response_model=UserResponse)
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
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post("/refresh", response_model=TokenResponse)
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

    custom_claims = {"role": user.role, "tenant_id": user.tenant_id}
    new_access_token = create_jwt_token(sub=username, custom_claims=custom_claims)
    new_refresh_token = await create_refresh_token(
        sub=username, custom_claims=custom_claims
    )

    logger.info("token_refreshed", extra={"username": username})
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)
