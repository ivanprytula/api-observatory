"""PostgreSQL proof for the opt-in observations row-level security policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import Observation


pytestmark = [pytest.mark.integration, pytest.mark.capability_rls]


async def test_rls_hides_other_tenant_rows_from_unfiltered_query(
    postgresql_async_session: AsyncSession,
) -> None:
    """Tenant A cannot see tenant B rows even through an unfiltered SQL query."""
    db = postgresql_async_session
    timestamp = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    db.add_all(
        [
            Observation(
                source="rls-tenant-a",
                timestamp=timestamp,
                raw_data={"tenant": "a"},
                tags=["rls"],
                tenant_id=101,
            ),
            Observation(
                source="rls-tenant-b",
                timestamp=timestamp + timedelta(seconds=1),
                raw_data={"tenant": "b"},
                tags=["rls"],
                tenant_id=202,
            ),
            Observation(
                source="rls-global",
                timestamp=timestamp + timedelta(seconds=2),
                raw_data={"tenant": "global"},
                tags=["rls"],
                tenant_id=None,
            ),
        ]
    )
    await db.commit()

    await db.execute(text("SET ROLE test_app_api_user"))
    visible_before_enable = list(
        (
            await db.execute(text("SELECT source FROM observations ORDER BY source"))
        ).scalars()
    )
    assert visible_before_enable == ["rls-global", "rls-tenant-a", "rls-tenant-b"]

    await db.commit()
    db.info["rls_enabled"] = True
    db.info["tenant_id"] = 101
    await db.execute(text("SET ROLE test_app_api_user"))
    context = (
        await db.execute(
            text(
                "SELECT current_setting('app.rls_enabled', true), "
                "current_setting('app.tenant_id', true)"
            )
        )
    ).one()
    assert context == ("true", "101")

    visible_sources = list(
        (
            await db.execute(text("SELECT source FROM observations ORDER BY source"))
        ).scalars()
    )

    assert visible_sources == ["rls-global", "rls-tenant-a"]
