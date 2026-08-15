"""Idempotent bootstrap helpers for first-run initialization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from argon2 import PasswordHasher

from services.ingestor.config import settings
from services.ingestor.repositories.users import count_active_admins, create_user


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
_ph = PasswordHasher()


async def bootstrap_initial_admin(session: AsyncSession) -> None:
    """Create the initial admin user if configured and no admin exists yet.

    Idempotent: safe to call on every startup. Requires both
    ``INIT_ADMIN_USERNAME`` and ``INIT_ADMIN_PASSWORD`` to be set in the
    environment. Uses the same ``create_user`` CRUD path as public
    registration so tenant provisioning and password hashing stay consistent.
    """
    if not settings.init_admin_username or not settings.init_admin_password:
        return

    admin_count = await count_active_admins(session)
    if admin_count > 0:
        logger.info("bootstrap_initial_admin_skipped", extra={"reason": "admin_exists"})
        return

    email = settings.init_admin_email or (f"{settings.init_admin_username}@example.com")
    password_hash = _ph.hash(settings.init_admin_password)

    try:
        user = await create_user(
            session=session,
            username=settings.init_admin_username,
            email=email,
            password_hash=password_hash,
            role="admin",
        )
    except Exception as exc:
        logger.error(
            "bootstrap_initial_admin_failed",
            extra={"error": str(exc)},
        )
        return

    logger.info(
        "bootstrap_initial_admin_complete",
        extra={"username": user.username, "user_id": user.id},
    )
