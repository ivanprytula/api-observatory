"""Auth routes — register, login (JWT), me, logout."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.records import (
    TokenResponse,
    UserCreate,
    UserResponse,
)
from services.ingestor.auth import (
    create_jwt_token,
    create_session,
    delete_session,
    verify_jwt_token,
)
from services.ingestor.constants import API_V1_PREFIX, AUTH_LOGIN_RATE_LIMIT
from services.ingestor.database import get_db
from services.ingestor.rate_limiting import limiter
from services.ingestor.repositories.records import (
    create_user,
    get_user_by_username,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/auth", tags=["auth"])

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
            tenant_id=body.tenant_id,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered.",
        ) from None
    logger.info("user_registered", extra={"username": body.username})
    return UserResponse.model_validate(user)


@router.post("/token", response_model=TokenResponse)
@limiter.limit(AUTH_LOGIN_RATE_LIMIT)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbDep,
) -> TokenResponse:
    """Authenticate and return a JWT access token.

    Also creates a Redis-backed session and sets a session cookie.

    Args:
        request: Raw FastAPI request (required by slowapi).
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

    # Also create a Redis session with tenant_id
    await create_session(
        user.username, {"role": user.role, "tenant_id": user.tenant_id}
    )

    logger.info("user_login", extra={"username": user.username})
    return TokenResponse(access_token=token)


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
async def logout(session_id: str | None = Cookie(default=None)) -> None:
    """Invalidate the current session cookie.

    Args:
        session_id: Session ID from the HTTP-only cookie (if present).
    """
    if session_id:
        await delete_session(session_id)
    logger.info("user_logout", extra={"session_id": session_id})
