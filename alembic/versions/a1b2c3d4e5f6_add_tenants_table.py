"""add tenants table for auto-provisioned personal tenants

Revision ID: a1b2c3d4e5f6
Revises: b771ac41bc8f
Create Date: 2026-08-09 19:21:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "bab88abe6c35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_table("tenants")
