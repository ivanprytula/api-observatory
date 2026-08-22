"""Add outbound auth columns to source_profiles

Revision ID: f4d5e6f7a1b2
Revises: f3c4d5e6f7a1
Create Date: 2026-08-22 18:33:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "f4d5e6f7a1b2"
down_revision: str | None = "f3c4d5e6f7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_profiles",
        sa.Column("auth_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "source_profiles",
        sa.Column("api_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "source_profiles",
        sa.Column("auth_header_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "source_profiles",
        sa.Column("auth_username", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_profiles", "auth_username")
    op.drop_column("source_profiles", "auth_header_name")
    op.drop_column("source_profiles", "api_key")
    op.drop_column("source_profiles", "auth_type")
