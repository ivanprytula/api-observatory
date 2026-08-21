"""Integration tests for user management repository functions.

These tests exercise ``create_user`` and ``update_user_role`` against a real
PostgreSQL database (via testcontainers when Docker is available) with a
live Casbin enforcer backed by the ``casbin_rule`` table.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.auth import get_casbin_enforcer
from services.ingestor.models import Tenant, UserTenant
from services.ingestor.repositories.users import create_user, update_user_role


pytestmark = pytest.mark.integration


async def test_create_user_auto_provisions_personal_tenant(
    db: AsyncSession,
) -> None:
    """create_user with no tenant_id creates a personal tenant and assigns the role."""
    user = await create_user(
        db,
        username="alice",
        email="alice@example.com",
        password_hash="hash123",
    )

    assert user.id is not None
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert user.tenant_id is not None

    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one()
    assert tenant.name == "alice-personal"

    enforcer = get_casbin_enforcer()
    roles = enforcer.get_roles_for_user_in_domain("alice", str(user.tenant_id))
    assert "user" in roles


async def test_create_user_with_explicit_tenant_id(
    db: AsyncSession,
) -> None:
    """create_user with an explicit tenant_id reuses that tenant and assigns the role."""
    tenant = Tenant(name="explicit-tenant")
    db.add(tenant)
    await db.flush()

    user = await create_user(
        db,
        username="bob",
        email="bob@example.com",
        password_hash="hash456",
        role="admin",
        tenant_id=tenant.id,
    )

    assert user.tenant_id == tenant.id

    result = await db.execute(
        select(UserTenant).where(
            UserTenant.user_id == user.id,
            UserTenant.tenant_id == tenant.id,
        )
    )
    assert result.scalar_one() is not None

    enforcer = get_casbin_enforcer()
    roles = enforcer.get_roles_for_user_in_domain("bob", str(tenant.id))
    assert "admin" in roles


async def test_update_user_role_replaces_existing_roles(
    db: AsyncSession,
) -> None:
    """update_user_role replaces the user's Casbin role assignment in domain '*'."""
    user = await create_user(
        db,
        username="carol",
        email="carol@example.com",
        password_hash="hash789",
        role="user",
    )

    enforcer = get_casbin_enforcer()
    user_domain = str(user.tenant_id)
    assert "user" in enforcer.get_roles_for_user_in_domain("carol", user_domain)

    result = await update_user_role(db, "carol", "admin")

    assert result is not None
    assert result.id == user.id

    star_roles = enforcer.get_roles_for_user_in_domain("carol", "*")
    assert "admin" in star_roles


async def test_update_user_role_returns_none_for_missing_user(
    db: AsyncSession,
) -> None:
    """update_user_role returns None when the user does not exist."""
    result = await update_user_role(db, "ghost", "admin")
    assert result is None
