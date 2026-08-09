"""Add opt-in tenant RLS policy for observations.

Revision ID: e60d14dbfebd
Revises: a3c67d58f9fa
Create Date: 2026-07-23 19:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "e60d14dbfebd"
down_revision: str | None = "a3c67d58f9fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TENANT_POLICY = """
  current_setting('app.rls_enabled', true) IS DISTINCT FROM 'true'
  OR tenant_id IS NULL
  OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer
"""


def upgrade() -> None:
    """Enable an opt-in tenant policy for the observations hot table."""
    op.execute("ALTER TABLE observations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE observations FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY observations_tenant_isolation
        ON observations
        USING ({_TENANT_POLICY})
        WITH CHECK ({_TENANT_POLICY})
        """
    )


def downgrade() -> None:
    """Remove the tenant policy and restore pre-RLS table behavior."""
    op.execute("DROP POLICY observations_tenant_isolation ON observations")
    op.execute("ALTER TABLE observations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE observations DISABLE ROW LEVEL SECURITY")
