"""Add opt-in tenant RLS policy for dependency incidents.

Revision ID: bab88abe6c35
Revises: cced5946142f
Create Date: 2026-07-29 16:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "bab88abe6c35"
down_revision: str | None = "cced5946142f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TENANT_POLICY = """
  current_setting('app.rls_enabled', true) IS DISTINCT FROM 'true'
  OR current_setting('app.user_role', true) = 'admin'
  OR tenant_id IS NULL
  OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer
"""


def upgrade() -> None:
    """Enable opt-in tenant isolation while preserving admin and global access."""
    op.execute("ALTER TABLE dependency_incidents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dependency_incidents FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY dependency_incidents_tenant_isolation
        ON dependency_incidents
        USING ({_TENANT_POLICY})
        WITH CHECK ({_TENANT_POLICY})
        """
    )


def downgrade() -> None:
    """Remove the incident policy and restore pre-RLS behavior."""
    op.execute(
        "DROP POLICY dependency_incidents_tenant_isolation ON dependency_incidents"
    )
    op.execute("ALTER TABLE dependency_incidents NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dependency_incidents DISABLE ROW LEVEL SECURITY")
