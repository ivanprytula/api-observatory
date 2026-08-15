"""remove_user_role_column_and_seed_casbin_policies

Revision ID: e239a5cdd6fc
Revises: d1e2f3a4b5c6
Create Date: 2026-08-15 17:04:52.483864

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e239a5cdd6fc"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_users_role"))
    conn.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS role"))

    conn.execute(
        sa.text(
            "INSERT INTO casbin_rule (ptype, v0, v1, v2, v3) VALUES "
            "('g', 'admin', 'manager', '*', NULL), "
            "('g', 'manager', 'user', '*', NULL), "
            "('p', 'user', '*', '*', 'access'), "
            "('p', 'manager', '*', '*', 'access'), "
            "('p', 'admin', '*', '*', 'access') "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM casbin_rule WHERE ptype IN ('g', 'p')"))
    conn.execute(
        sa.text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) DEFAULT 'user' NOT NULL"
        )
    )
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)"))
