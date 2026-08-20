"""Idempotent bootstrap helpers for first-run initialization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from argon2 import PasswordHasher

from services.ingestor.config import settings
from services.ingestor.models import User
from services.ingestor.repositories.users import (
    count_active_admins,
    create_user,
    get_user_by_username,
)


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


async def ensure_superadmin(session: AsyncSession) -> None:
    """Create the reserved global superadmin if configured and absent.

    The superadmin is tenant-less (no Tenant/UserTenant row) and bypasses Casbin
    via the ``is_superuser`` matcher function rather than g-rules, so it needs no
    role assignment. Idempotent: safe to call on every startup.

    Requires ``SUPERADMIN_PASSWORD`` to be set; no-op otherwise. Root authenticates
    like any user via ``/auth/token`` (argon2 hash + JWT with ``tenant_id=None``),
    so no separate credential store or setup script is required.
    """
    if not settings.superadmin_password:
        return

    subject = settings.superadmin_subject
    existing = await get_user_by_username(session, subject)
    if existing is not None:
        logger.info("ensure_superadmin_skipped", extra={"reason": "subject_exists"})
        return

    email = settings.superadmin_email or f"{subject}@example.com"
    password_hash = _ph.hash(settings.superadmin_password)

    # Intentionally NOT using create_user() — the superadmin is tenant-less
    # (no Tenant or UserTenant row) and bypasses Casbin via the is_superuser
    # matcher rather than g-rules. create_user() provisions a tenant and assigns
    # a Casbin role, neither of which applies here.
    try:
        user = User(username=subject, email=email, password_hash=password_hash)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    except Exception as exc:
        await session.rollback()
        logger.error("ensure_superadmin_failed", extra={"error": str(exc)})
        return

    logger.info(
        "ensure_superadmin_complete",
        extra={"username": user.username, "user_id": user.id},
    )
