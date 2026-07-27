"""add dependency incident lifecycle

Revision ID: dependency_incidents_01
Revises: observations_rls_01
Create Date: 2026-07-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "dependency_incidents_01"
down_revision: str | None = "observations_rls_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source incident policy and tenant-scoped lifecycle storage."""
    op.add_column("source_profiles", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column(
        "source_profiles",
        sa.Column("latency_threshold_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "source_profiles",
        sa.Column(
            "incident_failure_threshold",
            sa.Integer(),
            server_default="2",
            nullable=False,
        ),
    )
    op.add_column(
        "source_profiles",
        sa.Column(
            "incident_cooldown_seconds",
            sa.Integer(),
            server_default="900",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_source_profiles_tenant_id", "source_profiles", ["tenant_id"], unique=False
    )

    op.create_table(
        "dependency_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=255), nullable=False),
        sa.Column("active_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=False),
        sa.Column("guidance", sa.String(length=2048), nullable=False),
        sa.Column("trigger_details", sa.JSON(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=128), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("last_notification_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="ck_dependency_incidents_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('availability', 'latency', 'drift')",
            name="ck_dependency_incidents_trigger_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dependency_incidents_active_key",
        "dependency_incidents",
        ["active_key"],
        unique=True,
    )
    op.create_index(
        "ix_dependency_incidents_last_seen_at",
        "dependency_incidents",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_dependency_incidents_source_status",
        "dependency_incidents",
        ["source_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_dependency_incidents_tenant_status",
        "dependency_incidents",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Remove dependency incident storage and source policy fields."""
    op.drop_index(
        "ix_dependency_incidents_tenant_status", table_name="dependency_incidents"
    )
    op.drop_index(
        "ix_dependency_incidents_source_status", table_name="dependency_incidents"
    )
    op.drop_index(
        "ix_dependency_incidents_last_seen_at", table_name="dependency_incidents"
    )
    op.drop_index(
        "ix_dependency_incidents_active_key", table_name="dependency_incidents"
    )
    op.drop_table("dependency_incidents")
    op.drop_index("ix_source_profiles_tenant_id", table_name="source_profiles")
    op.drop_column("source_profiles", "incident_cooldown_seconds")
    op.drop_column("source_profiles", "incident_failure_threshold")
    op.drop_column("source_profiles", "latency_threshold_ms")
    op.drop_column("source_profiles", "tenant_id")
