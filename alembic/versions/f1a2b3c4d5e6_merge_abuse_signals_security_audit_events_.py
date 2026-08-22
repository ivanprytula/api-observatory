"""Merge abuse_signals + security_audit_events into security_events

Revision ID: f1a2b3c4d5e6
Revises: e239a5cdd6fc
Create Date: 2026-08-22 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e239a5cdd6fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("prev_event_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=True),
        sa.Column("signal_type", sa.String(length=64), nullable=True),
        sa.Column("detection_rule", sa.String(length=128), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("action_taken", sa.String(length=128), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "category IN ('abuse', 'audit')",
            name="ck_security_events_category",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_security_events_actor_id",
        "security_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_actor_type",
        "security_events",
        ["actor_type"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_created_at",
        "security_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_event_type",
        "security_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_resolved_at",
        "security_events",
        ["resolved_at"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_signal_type",
        "security_events",
        ["signal_type"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_tenant_id",
        "security_events",
        ["tenant_id"],
        unique=False,
    )
    op.drop_table("abuse_signals")
    op.drop_table("security_audit_events")


def downgrade() -> None:
    op.drop_index("ix_security_events_tenant_id", table_name="security_events")
    op.drop_index("ix_security_events_signal_type", table_name="security_events")
    op.drop_index("ix_security_events_resolved_at", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_index("ix_security_events_created_at", table_name="security_events")
    op.drop_index("ix_security_events_actor_type", table_name="security_events")
    op.drop_index("ix_security_events_actor_id", table_name="security_events")
    op.drop_table("security_events")

    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("prev_event_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "abuse_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=True),
        sa.Column("detection_rule", sa.String(length=128), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("action_taken", sa.String(length=128), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
