"""Integration coverage for the global superadmin (root) identity.

The superadmin bypasses authorization via two independent mechanisms, each
exercised here:

* Casbin matcher short-circuit (``is_superuser(r.sub) -> allow``) -- no g-rules
  are required for the reserved subject. Proven directly via
  ``Enforcer.enforce`` so the assertion is deterministic and endpoint-agnostic.

* PostgreSQL Row-Level Security bypass in ``TenantMiddleware``: a root JWT
  carries no ``tenant_id``, so ``app.user_role`` is forced to ``"admin"``,
  which the RLS policies treat as a full bypass. Proven via a cross-tenant
  HTTP read (a tenant-scoped user could only see one tenant; root sees both).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.auth import (
    create_jwt_token,
    get_casbin_enforcer,
    is_superuser,
    verify_jwt_token,
)
from services.ingestor.core.config import settings
from services.ingestor.main import app


pytestmark = pytest.mark.integration


@contextmanager
def _with_real_jwt() -> Iterator[None]:
    """Drop the shared ``client`` fixture's ``verify_jwt_token`` override.

    The ``client`` fixture overrides ``verify_jwt_token`` to return a hardcoded
    ``{"sub": "testuser"}``. The superadmin bypass is subject-based, so we let
    the *real* verifier decode the reserved root JWT instead.
    """
    saved = app.dependency_overrides.pop(verify_jwt_token, None)
    try:
        yield
    finally:
        if saved is not None:
            app.dependency_overrides[verify_jwt_token] = saved


async def _seed_cross_tenant_observations(db: AsyncSession) -> None:
    """Plant observations in two tenants so cross-tenant reads are observable."""
    await db.execute(text("DELETE FROM observations"))
    now = datetime.now(UTC).replace(tzinfo=None)
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, "
            "tenant_id, created_at, processed) "
            "VALUES ('t10_data', :now, '{}', '[]', 10, :now, false)"
        ),
        {"now": now},
    )
    await db.execute(
        text(
            "INSERT INTO observations (source, timestamp, raw_data, tags, "
            "tenant_id, created_at, processed) "
            "VALUES ('t11_data', :now, '{}', '[]', 11, :now, false)"
        ),
        {"now": now},
    )
    await db.commit()


@pytest.mark.postgresonly
async def test_superadmin_bypasses_casbin_matcher(db: AsyncSession) -> None:
    """A root subject is allowed for any role/domain with no g-rule backing it."""
    enforcer = get_casbin_enforcer()

    # Short-circuit: root needs no policies at all, in any domain or role tier.
    assert enforcer.enforce(settings.superadmin_subject, "*", "admin", "access") is True
    assert (
        enforcer.enforce(settings.superadmin_subject, "10", "admin", "access") is True
    )
    assert enforcer.enforce(settings.superadmin_subject, "*", "user", "access") is True

    # Non-root subjects still require explicit g-rules (here: absent -> denied).
    assert enforcer.enforce("regular-user", "*", "admin", "access") is False


@pytest.mark.postgresonly
async def test_superadmin_bypasses_rls_across_tenants(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A root JWT (no tenant) reads every tenant's observations via RLS bypass."""
    await _seed_cross_tenant_observations(db)
    token = create_jwt_token(settings.superadmin_subject, {"tenant_id": None})

    with _with_real_jwt():
        resp = await client.get(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    sources = {row["source"] for row in resp.json()["observations"]}
    # A tenant-scoped user could only see one tenant; root sees both.
    assert {"t10_data", "t11_data"} <= sources


def test_is_superuser_predicate() -> None:
    """The bypass is keyed on the configured subject, not any arbitrary name."""
    assert is_superuser(settings.superadmin_subject) is True
    assert is_superuser("regular-user") is False
    assert is_superuser(None) is False
    assert is_superuser("") is False


def test_casbin_model_compiles_and_g_tuple_order() -> None:
    """The Casbin model file parses and the g() matcher uses (sub, dom, obj) order.

    Regression guard: the matcher must call g(r.sub, r.dom, r.obj), NOT
    g(r.sub, r.obj, r.dom). A swapped argument silently breaks all RBAC.
    """
    import os

    from casbin import Enforcer

    model_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "services",
        "ingestor",
        "security",
        "casbin_model.conf",
    )
    model_path = os.path.normpath(model_path)

    enforcer = Enforcer(model_path)  # type: ignore[call-arg]
    # Model parsed without error — the matcher compiled.
    assert enforcer is not None

    # Verify the g() call argument order via the model's request definition.
    # Casbin stores the model text; confirm g(r.sub, r.dom, r.obj) appears.
    with open(model_path) as f:
        model_text = f.read()
    assert "g(r.sub, r.dom, r.obj)" in model_text, (
        "Casbin matcher must call g(r.sub, r.dom, r.obj) — not g(r.sub, r.obj, r.dom). "
        "Swapped arguments silently break all RBAC role resolution."
    )
