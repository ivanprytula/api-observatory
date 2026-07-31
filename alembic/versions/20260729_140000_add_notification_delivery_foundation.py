"""add durable notification delivery foundation

Revision ID: notification_delivery_01
Revises: contract_baselines_01
Create Date: 2026-07-29 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "notification_delivery_01"
down_revision: str | None = "contract_baselines_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add leased outbox/inbox claims and per-channel delivery state."""
    op.add_column(
        "outbox_events", sa.Column("next_attempt_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "outbox_events", sa.Column("lease_expires_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "outbox_events", sa.Column("claim_token", sa.String(length=36), nullable=True)
    )
    op.create_index(
        "ix_outbox_events_publish_due",
        "outbox_events",
        ["published_at", "next_attempt_at", "lease_expires_at"],
        unique=False,
    )

    op.add_column(
        "inbox_consumptions",
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="completed",
            nullable=False,
        ),
    )
    op.add_column(
        "inbox_consumptions",
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "inbox_consumptions",
        sa.Column("last_error_category", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "inbox_consumptions",
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "inbox_consumptions",
        sa.Column("last_error_detail", sa.String(length=512), nullable=True),
    )
    op.alter_column(
        "inbox_consumptions",
        "processed_at",
        existing_type=sa.DateTime(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_inbox_consumptions_status",
        "inbox_consumptions",
        "status IN ('processing', 'completed', "
        "'completed_with_dead_letters', 'dead_letter')",
    )
    op.create_index(
        "ix_inbox_consumptions_claim",
        "inbox_consumptions",
        ["status", "lease_expires_at"],
        unique=False,
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inbox_consumption_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("claim_token", sa.String(length=36), nullable=True),
        sa.Column("first_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(), nullable=True),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("last_error_category", sa.String(length=32), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_detail", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'retry_scheduled', "
            "'delivered', 'dead_letter')",
            name="ck_notification_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 3",
            name="ck_notification_deliveries_attempt_count",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "channel",
            name="uq_notification_deliveries_message_channel",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_incident_id",
        "notification_deliveries",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_retry_due",
        "notification_deliveries",
        ["status", "next_attempt_at", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_source_created",
        "notification_deliveries",
        ["source_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_tenant_created",
        "notification_deliveries",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove delivery state and restore the previous inbox/outbox shape."""
    op.drop_index(
        "ix_notification_deliveries_tenant_created",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_source_created",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_retry_due",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_incident_id",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")

    op.drop_index("ix_inbox_consumptions_claim", table_name="inbox_consumptions")
    op.drop_constraint(
        "ck_inbox_consumptions_status",
        "inbox_consumptions",
        type_="check",
    )
    op.execute(
        sa.text(
            "UPDATE inbox_consumptions "
            "SET processed_at = COALESCE(processed_at, created_at, CURRENT_TIMESTAMP)"
        )
    )
    op.alter_column(
        "inbox_consumptions",
        "processed_at",
        existing_type=sa.DateTime(),
        nullable=False,
    )
    op.drop_column("inbox_consumptions", "last_error_detail")
    op.drop_column("inbox_consumptions", "last_error_code")
    op.drop_column("inbox_consumptions", "last_error_category")
    op.drop_column("inbox_consumptions", "lease_expires_at")
    op.drop_column("inbox_consumptions", "status")

    op.drop_index("ix_outbox_events_publish_due", table_name="outbox_events")
    op.drop_column("outbox_events", "claim_token")
    op.drop_column("outbox_events", "lease_expires_at")
    op.drop_column("outbox_events", "next_attempt_at")
