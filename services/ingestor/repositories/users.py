"""User CRUD operations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.auth import get_casbin_enforcer
from services.ingestor.models import Tenant, User, UserTenant, _utcnow


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """Fetch a user by username."""
    result = await session.execute(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def update_user_role(
    session: AsyncSession,
    username: str,
    role: str,
) -> User | None:
    """Assign a new role to a user by syncing Casbin g-rules."""
    user = await get_user_by_username(session, username)
    if user is None:
        return None
    enforcer = get_casbin_enforcer()
    domain = "*"
    existing_roles = list(enforcer.get_roles_for_user_in_domain(username, domain))
    for existing in existing_roles:
        enforcer.delete_roles_for_user_in_domain(username, existing, domain)
    enforcer.add_role_for_user_in_domain(username, role, domain)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Fetch an active user by primary key."""
    result = await session.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
    password_hash: str,
    role: str = "user",
    tenant_id: int | None = None,
) -> User:
    """Create a new user and sync the initial role to Casbin."""
    if tenant_id is None:
        tenant = Tenant(name=f"{username}-personal")
        session.add(tenant)
        await session.flush()
        tenant_id = tenant.id

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        tenant_id=tenant_id,
    )
    session.add(user)
    await session.flush()

    user_tenant = UserTenant(user_id=user.id, tenant_id=tenant_id)
    session.add(user_tenant)

    enforcer = get_casbin_enforcer()
    domain = str(tenant_id) if tenant_id is not None else "*"
    enforcer.add_role_for_user_in_domain(username, role, domain)

    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int) -> User | None:
    """Soft-delete a user by primary key."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    user.is_active = False
    user.deleted_at = _utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def count_active_admins(
    session: AsyncSession,
    exclude_username: str | None = None,
) -> int:
    """Count active admin users via Casbin g-rules."""
    from casbin_sqlalchemy_adapter import CasbinRule

    stmt = (
        select(func.count(User.id))
        .join(
            CasbinRule,
            (CasbinRule.v0 == User.username)
            & (CasbinRule.ptype == "g")
            & (CasbinRule.v1 == "admin"),
        )
        .where(User.is_active.is_(True))
    )
    if exclude_username:
        stmt = stmt.where(User.username != exclude_username)
    result = await session.execute(stmt)
    return result.scalar_one()


async def has_tenant_access(
    session: AsyncSession, user_id: int, target_tenant_id: int
) -> bool:
    """Check if a user is explicitly authorized for a specific tenant via UserTenant."""
    result = await session.execute(
        select(UserTenant).where(
            UserTenant.user_id == user_id,
            UserTenant.tenant_id == target_tenant_id,
            UserTenant.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def add_tenant_to_user(
    session: AsyncSession, user_id: int, target_tenant_id: int
) -> UserTenant:
    """Grant a user access to a specific tenant via the UserTenant junction table."""
    user_tenant = UserTenant(
        user_id=user_id,
        tenant_id=target_tenant_id,
    )
    try:
        session.add(user_tenant)
        await session.commit()
        await session.refresh(user_tenant)
        return user_tenant
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(UserTenant).where(
                UserTenant.user_id == user_id,
                UserTenant.tenant_id == target_tenant_id,
            )
        )
        existing = result.scalar_one()
        if existing.deleted_at is not None:
            existing.deleted_at = None
            await session.commit()
            await session.refresh(existing)
        return existing


async def list_users(
    session: AsyncSession, limit: int = 100, offset: int = 0
) -> tuple[list[User], int]:
    """List users with pagination."""
    stmt = select(User).where(User.is_active.is_(True)).limit(limit).offset(offset)
    result = await session.execute(stmt)
    users = result.scalars().all()

    count_stmt = select(func.count(User.id)).where(User.is_active.is_(True))
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    return list(users), total
