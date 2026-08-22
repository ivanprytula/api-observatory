"""Add tenant_id and error-tracking columns to event tables

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-22 18:31:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "f2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processed_events",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "outbox_events",
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    op.add_column(
        "inbox_consumptions",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "notification_deliveries",
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_deliveries", "processed_at")
    op.drop_column("inbox_consumptions", "tenant_id")
    op.drop_column("outbox_events", "processed_at")
    op.drop_column("processed_events", "tenant_id")
