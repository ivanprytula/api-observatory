"""add_observations_archive

Revision ID: a3c67d58f9fa
Revises: 1088e092eac2
Create Date: 2026-07-23 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "a3c67d58f9fa"
down_revision: str | None = "1088e092eac2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the warm-tier archive table for retained observations."""
    op.create_table(
        "observations_archive",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_observations_archive_timestamp",
        "observations_archive",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_observations_archive_archived_at",
        "observations_archive",
        ["archived_at"],
        unique=False,
    )
    op.create_index(
        "ix_observations_archive_tenant_id",
        "observations_archive",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the warm-tier archive table."""
    op.drop_index(
        "ix_observations_archive_tenant_id", table_name="observations_archive"
    )
    op.drop_index(
        "ix_observations_archive_archived_at", table_name="observations_archive"
    )
    op.drop_index(
        "ix_observations_archive_timestamp", table_name="observations_archive"
    )
    op.drop_table("observations_archive")
