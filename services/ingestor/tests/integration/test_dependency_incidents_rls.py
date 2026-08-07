"""PostgreSQL proof for opt-in dependency-incident row-level security."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import DependencyIncident, SourceProfile


pytestmark = [pytest.mark.integration, pytest.mark.capability_rls]


async def _seed_incidents(db: AsyncSession) -> None:
    sources = [
        SourceProfile(
            name="rls-incident-a", base_url="https://a.example", tenant_id=101
        ),
        SourceProfile(
            name="rls-incident-b", base_url="https://b.example", tenant_id=202
        ),
        SourceProfile(name="rls-incident-global", base_url="https://global.example"),
    ]
    db.add_all(sources)
    await db.flush()
    for source in sources:
        db.add(
            DependencyIncident(
                source_id=source.id,
                tenant_id=source.tenant_id,
                trigger_type="availability",
                fingerprint=f"rls-{source.name}",
                active_key=f"rls-{source.name}",
                status="open",
                severity="critical",
                summary="RLS test incident.",
                guidance="Test only.",
                trigger_details={},
                occurrence_count=1,
            )
        )
    await db.commit()


async def test_incident_rls_scopes_reads_writes_and_admin_access(
    postgresql_async_session: AsyncSession,
) -> None:
    """RLS protects tenant rows independently of repository query predicates."""
    db = postgresql_async_session
    await _seed_incidents(db)

    await db.execute(text("SET ROLE test_app_api_user"))
    assert list(
        await db.scalars(text("SELECT tenant_id FROM dependency_incidents ORDER BY id"))
    ) == [101, 202, None]

    await db.commit()
    db.info.update(rls_enabled=True, tenant_id=101, user_role="viewer")
    await db.execute(text("SET ROLE test_app_api_user"))
    assert list(
        await db.scalars(text("SELECT tenant_id FROM dependency_incidents ORDER BY id"))
    ) == [101, None]
    assert (
        list(
            await db.scalars(
                text(
                    "UPDATE dependency_incidents SET status = 'acknowledged' "
                    "WHERE tenant_id = 202 RETURNING id"
                )
            )
        )
        == []
    )
    assert (
        len(
            list(
                await db.scalars(
                    text(
                        "UPDATE dependency_incidents SET status = 'acknowledged' "
                        "WHERE tenant_id = 101 RETURNING id"
                    )
                )
            )
        )
        == 1
    )

    await db.commit()
    db.info.update(tenant_id=None, user_role="viewer")
    await db.execute(text("SET ROLE test_app_api_user"))
    assert list(
        await db.scalars(text("SELECT tenant_id FROM dependency_incidents ORDER BY id"))
    ) == [None]

    await db.commit()
    db.info["user_role"] = "admin"
    await db.execute(text("SET ROLE test_app_api_user"))
    assert list(
        await db.scalars(text("SELECT tenant_id FROM dependency_incidents ORDER BY id"))
    ) == [101, 202, None]
